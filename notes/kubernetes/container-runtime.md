# 컨테이너 런타임 — containerd와 CRI

**쿠버네티스는 컨테이너를 직접 실행하지 않는다.**
kubelet은 "이 파드를 띄워라"라고 지시만 하고, 실제 실행은 컨테이너 런타임에게 맡긴다.

## 계층

```
kubelet                     "nginx 컨테이너 하나 띄워"
   │  CRI (gRPC)
   ▼
containerd                  이미지 받고, 스냅샷 만들고, 생명주기 관리
   │  OCI 런타임 스펙
   ▼
runc                        실제로 프로세스를 격리해 생성
   │
   ▼
리눅스 커널                  namespace(격리) + cgroup(자원 제한)
```

| 계층 | 하는 일 | 성격 |
|---|---|---|
| **kubelet** | 파드 스펙을 받아 무엇을 띄울지 결정 | 노드 에이전트 |
| **containerd** | 이미지 pull·저장, 컨테이너 생성·시작·정지, 로그 | 고수준 런타임 |
| **runc** | namespace·cgroup 설정, 프로세스 격리 | 저수준 런타임 |
| **커널** | 실제 격리와 자원 제한 | — |

**컨테이너는 특별한 무엇이 아니다.** namespace로 시야를 가리고
cgroup으로 자원을 묶은 **평범한 리눅스 프로세스**다.
`ps aux`를 치면 호스트에서 그대로 보인다.

## 두 개의 규약

경계마다 표준이 있어서 구현을 갈아끼울 수 있다.

| 규약 | 사이 | 대체 구현 |
|---|---|---|
| **CRI** (Container Runtime Interface) | kubelet ↔ 고수준 런타임 | containerd, CRI-O |
| **OCI** (Open Container Initiative) | 고수준 ↔ 저수준 런타임 | runc, crun, **gVisor**, **Kata** |

OCI 쪽을 바꾸면 격리 방식 자체가 달라진다.
gVisor는 사용자 공간 커널을 두고, Kata는 컨테이너마다 경량 VM을 띄운다.
멀티테넌트 환경에서 격리를 강화할 때 쓴다. (CKS 범위)

## 왜 Docker가 아닌가

예전에는 Docker를 썼지만 **Docker가 CRI를 말할 줄 몰라서**
`dockershim`이라는 어댑터를 거쳐야 했다.

```
kubelet → dockershim → Docker → containerd → runc     ← ~v1.23
kubelet ────────────► containerd → runc               ← v1.24~
```

**Docker 내부에도 이미 containerd가 있다.** 어댑터와 Docker 데몬은 순수한 중간층이었다.

| 버전 | 변화 |
|---|---|
| v1.20 | dockershim deprecated 공지 |
| **v1.24** | **dockershim 완전 제거** |

지금 Docker를 깔면 계층이 하나 늘고 관리 지점만 많아진다. **containerd만 설치한다.**

> containerd는 원래 Docker에서 떨어져 나온 프로젝트이고 지금은 CNCF 졸업 프로젝트다.
> [`etcd`](etcd.md)와 같은 위치 — 쿠버네티스 전용이 아닌 독립 소프트웨어다.

## 설치와 설정

```bash
sudo apt-get install -y containerd
containerd --version
```

### 설정은 반드시 `config default`로 생성

```bash
sudo mkdir -p /etc/containerd
containerd config default | sudo tee /etc/containerd/config.toml >/dev/null
head -3 /etc/containerd/config.toml
```

| containerd | 설정 스키마 |
|---|---|
| 1.x | `version = 2` |
| **2.x** | **`version = 3`** |

> ⚠️ **인터넷의 옛 `config.toml` 예제를 붙여넣지 말 것.**
> 스키마가 다르고 플러그인 키 이름도 바뀌었다. 그대로 쓰면 containerd가 뜨지 않는다.
>
> 이 프로젝트의 VM은 Ubuntu 24.04인데도 **containerd 2.2.1이 백포트**되어 있다.
> OS 버전으로 짐작하지 말고 `containerd --version`으로 확인할 것.

### ⭐ `SystemdCgroup = true`

```bash
sudo sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' /etc/containerd/config.toml
grep SystemdCgroup /etc/containerd/config.toml
sudo systemctl restart containerd
```

**cgroup은 커널 기능이고, 문제는 누가 관리하느냐다.**

kubelet은 systemd 드라이버를 쓴다. containerd가 `cgroupfs`를 쓰면
**같은 자원을 두 관리자가 각자 다르게 본다.**

- 평소에는 멀쩡하다
- **메모리 압박 상황에서 예측 불가능하게 동작한다**
- kubelet이 조용히 실패하는데 에러가 명확하지 않다

systemd가 cgroup 계층의 유일한 관리자여야 한다.
**빠뜨리면 원인 찾기가 매우 어려운 종류의 장애가 난다.**

## `crictl` — CRI에 직접 말 걸기

`kubectl`이 안 될 때(apiserver가 죽었을 때) 런타임에 직접 물어본다.
**CKA Troubleshooting(배점 30%)에서 실제로 쓴다.**

```bash
sudo crictl ps -a                 # 컨테이너 목록
sudo crictl logs <컨테이너ID>
sudo crictl images
sudo crictl pods                  # 파드 단위로
sudo crictl inspect <ID>
sudo crictl rmi --prune           # 안 쓰는 이미지 정리
```

| 상황 | `kubectl` | `crictl` |
|---|---|---|
| 정상 | ✅ | ✅ |
| apiserver 다운 | ❌ | ✅ |
| kubelet 다운 | ❌ | ✅ |

`crictl`은 노드의 containerd 소켓에 직접 붙으므로 **쿠버네티스가 마비돼도 동작한다.**
control plane 파드가 왜 안 뜨는지 볼 때 이것부터 친다.

> `crictl`은 `cri-tools` 패키지에 있다. kubeadm 설치 시 함께 들어온다.
> 설정은 `/etc/crictl.yaml`에서 소켓 경로를 지정한다.

## 진단

| 증상 | 확인 |
|---|---|
| kubelet이 계속 재시작 | `journalctl -u kubelet -f` — cgroup 드라이버 불일치 의심 |
| containerd가 안 뜸 | `journalctl -u containerd -e` — 설정 스키마 버전 확인 |
| 파드가 `ContainerCreating`에서 멈춤 | `crictl ps -a`, `crictl logs` |
| 이미지 pull 실패 | `crictl pull <이미지>` 로 직접 시도 |
| 소켓 확인 | `ls -l /run/containerd/containerd.sock` |

```bash
sudo ctr version            # containerd 자체 CLI (CRI 를 안 거침)
sudo ctr namespaces ls      # k8s.io 네임스페이스에 쿠버네티스 컨테이너가 있다
```

> `ctr`과 `crictl`은 다르다.
> `ctr`은 containerd 자체 도구라 저수준이고, `crictl`은 CRI 규약을 통해 본다.
> **평소에는 `crictl`을 쓴다.**

## 관련

- 클러스터 상태 저장소 → [`etcd.md`](etcd.md)
- Stage 2 설치 절차 → [`../../docs/stages/stage-02-first-cluster.md`](../../docs/stages/stage-02-first-cluster.md)

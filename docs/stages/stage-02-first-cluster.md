# Stage 2 — 첫 클러스터 (단일 노드)

| | |
|---|---|
| 대상 | k8s-2 호스트 + VM `k2-cp1` |
| 예상 소요 | 하루 |
| 선행 | [Stage 1](stage-01-virtualization.md) |
| 기록할 곳 | `labs/stage-02-first-cluster.md` |

## 이 단계에서 하는 일

**`kubectl get nodes`가 처음으로 동작한다.** 가장 큰 이정표다.

노드 하나로 시작한다. 여기서 막히면 노드를 늘려도 똑같이 막히므로
한 대에서 완전히 이해하고 넘어간다.

## 완료 기준

- [ ] `kubectl get nodes`에 `k2-cp1`이 `Ready`로 나온다
- [ ] `kubectl run nginx --image=nginx`로 띄운 파드가 `Running`
- [ ] `kubectl logs`가 동작한다
- [ ] HAProxy를 거쳐 apiserver에 닿는다
- [ ] 스냅샷으로 되돌린 뒤에도 클러스터가 정상 동작한다

---

## 전체 그림 — 어디에 무엇을 설치하나

**계층을 헷갈리지 않는 것이 이 단계의 절반이다.**

```
k8s-2 호스트  (하이퍼바이저 — 쿠버네티스 없음)
├─ HAProxy          192.168.122.1:6443    ← 여기만 호스트에 설치
│
└─ VM k2-cp1        192.168.122.11
   ├─ containerd                          ← 컨테이너 런타임
   ├─ kubelet / kubeadm / kubectl
   └─ control plane (static pod)
      apiserver · etcd · scheduler · controller-manager
```

| 어디에 | 무엇을 |
|---|---|
| **호스트** (k8s-2) | HAProxy **하나만** |
| **VM** (k2-cp1) | containerd, kubeadm, kubelet, kubectl, 그리고 클러스터 전부 |

호스트는 끝까지 클러스터 멤버가 아니다.
→ [`notes/network/concepts/02_node-addressing.md`](../../notes/network/concepts/02_node-addressing.md)

## 확인된 환경 (2026-09-10 실측)

| 항목 | 값 |
|---|---|
| VM OS | Ubuntu 24.04.4 LTS, kernel 6.8.0-138-generic |
| VM 인터페이스 | **`enp1s0`** (호스트의 `ens3`와 다르다) |
| swap | 0B — kubeadm 요구사항 충족 |
| containerd | **2.2.1** (24.04에 백포트됨 → 설정 스키마 **version 3**) |
| 커널 모듈 | `br_netfilter`·`overlay`·`nf_conntrack` 모두 사용 가능 |
| Calico | v3.32.2 (최신) |

---

## 1. HAProxy — 호스트에 먼저 세운다

### 1-1. 왜 지금인가

control plane이 Stage 5에서 3대가 되므로 `--control-plane-endpoint`가 필요하다.
이 주소는 **클러스터의 영구 주소**가 되어 인증서 SAN과 모든 kubeconfig에 박힌다.

**나중에 바꾸려면 인증서를 전부 재발급해야 한다.**
지금 HAProxy를 거치게 잡아두면 Stage 5에서 클러스터를 다시 만들지 않아도 된다.

배경은 [`notes/infra/haproxy.md`](../../notes/infra/haproxy.md).

### 1-2. 설치와 설정

**k8s-2 호스트에서** 실행한다.

```bash
sudo apt-get install -y haproxy
```

`/etc/haproxy/haproxy.cfg` 끝에 추가한다:

```haproxy
frontend k8s-api
    bind 192.168.122.1:6443
    mode tcp
    option tcplog
    default_backend k8s-cp

backend k8s-cp
    mode tcp
    balance roundrobin
    option tcp-check
    server k2-cp1 192.168.122.11:6443 check
    # Stage 5 에서 추가:
    # server k1-cp1 192.168.121.11:6443 check
    # server k1-cp2 192.168.121.12:6443 check

listen stats
    bind 192.168.122.1:8404
    mode http
    stats enable
    stats uri /stats
    stats refresh 10s
```

> **`bind`를 `*:6443`이 아니라 `192.168.122.1:6443`으로 한다.**
> `*`로 두면 `ens3`에도 열려 VCN 전체에 노출된다. 필요한 곳에만 연다.
>
> **`mode tcp`가 핵심이다.** apiserver는 mTLS로 클라이언트를 인증하는데,
> `mode http`로 두면 HAProxy가 TLS를 풀어버려 **RBAC이 통째로 무너진다.**

```bash
sudo haproxy -c -f /etc/haproxy/haproxy.cfg     # 문법 검사 — 출력이 없으면 정상
sudo systemctl restart haproxy                  # ← enable --now 가 아니라 restart
sudo systemctl enable haproxy
systemctl status haproxy --no-pager
```

> ⚠️ **`apt install haproxy`는 설치 직후 서비스를 자동으로 시작한다.**
> 그때는 설정 파일에 우리 블록이 없으므로 **아무것도 LISTEN하지 않는다.**
> 그런데 `systemctl status`는 `Active: running`, `Status: "Ready."`로 나와서
> 잘 된 것처럼 보인다.
>
> **설정을 고친 뒤에는 반드시 `restart`(또는 `reload`)한다.**
> 클러스터가 돌기 시작한 뒤에는 기존 연결을 유지하는 `reload`를 쓰는 편이 낫다.

### 1-3. VM에서 닿을 수 있게 — 방화벽

**여기가 빠지기 쉽다.** 포트는 열렸는데 VM에서 접속이 안 되는 상태가 된다.

```bash
# VM 에서 (호스트를 거쳐)
nc -vz -w3 192.168.122.1 6443
# nc: connect to 192.168.122.1 port 6443 (tcp) failed: No route to host
```

호스트의 `INPUT` 체인 마지막이 모든 것을 거부하기 때문이다.

```bash
sudo iptables -L INPUT -n -v --line-numbers
```

```
num   pkts  target       prot  in   source      destination
1     ..... LIBVIRT_INP  all   *                              ← DHCP/DNS 만 허용
2     ..... ACCEPT       all   *    state RELATED,ESTABLISHED
3     ..... ACCEPT       icmp  *
4     ..... ACCEPT       all   lo
5     ..... ACCEPT       tcp   *    state NEW tcp dpt:22
6        44 REJECT       all   *    reject-with icmp-host-prohibited   ← 여기서 떨어진다
```

> **`No route to host`는 라우팅 문제가 아니다.**
> `icmp-host-prohibited`로 거부당했을 때 클라이언트에 그렇게 보인다.
> 진짜 라우팅 문제라면 `Network is unreachable`이 난다.

#### 왜 인터넷은 되는데 이건 안 되나 — 체인이 다르다

| 트래픽 | 체인 | Stage 1에서 |
|---|---|---|
| VM → 인터넷 (호스트를 **통과**) | `FORWARD` | ✅ 열었다 |
| VM → **호스트 자신** (`.1`) | **`INPUT`** | ❌ 손대지 않았다 |

Stage 1의 `ip_forward`와 MASQUERADE는 **지나가는 트래픽**을 다룬 것이고,
호스트에 직접 말을 거는 것은 별개다.
dnsmasq(53번)가 되는 것은 `LIBVIRT_INP`가 그것만 열어주기 때문이다.

#### 왜 VM이 호스트에 말을 거는가

`--control-plane-endpoint`를 HAProxy 주소로 잡으면,
kubeadm이 만드는 **모든 kubeconfig의 `server:` 가 그 주소**가 된다.

```
kubelet.conf · scheduler.conf · controller-manager.conf · admin.conf
  → server: https://192.168.122.1:6443
```

그래서 `k2-cp1`의 kubelet이 **같은 VM 안의 apiserver에 접속할 때도
호스트를 한 바퀴 돌아간다.**

```
[k2-cp1]  kubelet ──► [호스트] HAProxy :6443 ──► [k2-cp1] apiserver :6443
```

이상해 보이지만 그것이 단일 엔드포인트의 목적이다 —
Stage 5에서 CP를 3대로 늘려도 **각 노드는 설정을 하나도 바꾸지 않는다.**

VM → 호스트로 상시 오가는 것: kubelet, kube-proxy, scheduler,
controller-manager, kubectl, 그리고 워커의 `kubeadm join`. **거의 전부다.**
(apiserver ↔ etcd 는 같은 VM 안에서 `127.0.0.1` 로 통신하므로 예외다.)

#### 규칙 추가

```bash
sudo iptables -I INPUT 2 -i virbr1 -p tcp --dport 6443 -j ACCEPT
sudo netfilter-persistent save

sudo iptables -L INPUT -n --line-numbers | head -8
```

| 조각 | 뜻 |
|---|---|
| `-I INPUT 2` | **2번 자리에 삽입.** `-A`(맨 뒤)로 하면 REJECT 뒤라 소용없다 |
| `-i virbr1` | VM 네트워크에서 들어오는 것만 |
| `--dport 6443` | apiserver 엔드포인트만. stats(8404)는 호스트에서 보면 되므로 열지 않는다 |

**순서가 전부다.** REJECT보다 앞에 있어야 한다.

확인:

```bash
ssh ubuntu@192.168.122.11 'nc -vz -w3 192.168.122.1 6443'
# Connection to 192.168.122.1 6443 port [tcp/*] succeeded!
```

> 이 규칙이 없으면 `kubeadm init`은 성공하는데
> **kubelet이 엔드포인트에 못 붙어 노드가 이상하게 동작한다.** 원인 찾기가 어렵다.

### 1-4. 검증 — 지금은 백엔드가 DOWN인 게 정상

```bash
sudo ss -lntp | grep 6443
# LISTEN 0 ... 192.168.122.1:6443 ... users:(("haproxy",...))
```

아직 apiserver가 없으므로 백엔드는 DOWN이다. **HAProxy는 그래도 뜬다.**
apiserver가 올라오면 헬스체크가 자동으로 감지해 UP으로 바꾼다.

로그에 이런 것이 보이는데 **정상이다.**

```
[WARNING] Server k8s-cp/k2-cp1 is DOWN, reason: Layer4 connection problem
[ALERT]   backend 'k8s-cp' has no server available!
```

`[ALERT]`라 놀라기 쉽지만 "가봤더니 아무도 없더라"는 보고일 뿐이다.
`Layer4 connection problem`은 TCP 연결 자체가 안 됐다는 뜻으로,
포트에 아무도 없을 때 나온다.

```bash
curl -s 'http://192.168.122.1:8404/stats;csv' | awk -F, '/^k8s-cp,/{printf "  %-10s %s\n", $2, $18}'
#   k2-cp1     DOWN
#   BACKEND    DOWN
```

브라우저로 보고 싶다면 맥에서:

```bash
ssh -L 8404:192.168.122.1:8404 k8s-2
# localhost:8404/stats
```

---

## 2. VM 준비 — 커널 모듈과 sysctl

**여기서부터는 VM(`k2-cp1`) 안에서** 실행한다.

```bash
ssh ubuntu@192.168.122.11        # 호스트에서
```

### 2-1. swap 확인

```bash
free -h | grep Swap
# Swap:   0B   0B   0B          ← 0 이어야 한다
```

kubelet은 swap이 켜져 있으면 기본적으로 시작을 거부한다.
메모리 압박 시 swap으로 밀려나면 스케줄러의 자원 계산이 무의미해지기 때문이다.
cloud image에는 swap이 없으므로 그대로 진행한다.

### 2-2. 커널 모듈

```bash
printf 'overlay\nbr_netfilter\n' | sudo tee /etc/modules-load.d/k8s.conf
sudo modprobe overlay
sudo modprobe br_netfilter
lsmod | grep -E 'overlay|br_netfilter'
```

| 모듈 | 왜 필요한가 |
|---|---|
| `overlay` | 컨테이너 이미지의 레이어를 겹쳐 하나의 파일시스템으로 보여준다 |
| `br_netfilter` | **브리지를 지나는 패킷도 iptables를 타게** 한다. Service·NetworkPolicy가 이것에 의존한다 |

`/etc/modules-load.d/`에 적어두면 재부팅 후에도 자동 적재된다.

### 2-3. sysctl

```bash
cat <<'SYSCTL' | sudo tee /etc/sysctl.d/k8s.conf
net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
SYSCTL

sudo sysctl --system

# 확인
sysctl net.bridge.bridge-nf-call-iptables net.ipv4.ip_forward
```

| 설정 | 뜻 |
|---|---|
| `bridge-nf-call-iptables` | 브리지 트래픽을 iptables가 보게 한다. **kube-proxy가 Service를 구현하는 전제** |
| `ip_forward` | 파드 간 패킷을 노드가 전달할 수 있게 한다 |

> `br_netfilter` 모듈을 먼저 올려야 이 sysctl 키가 존재한다. 순서가 중요하다.

---

## 3. 컨테이너 런타임 — containerd

> ⚠️ **여러 줄을 한 번에 붙여넣지 말 것.**
> 주석(`#`)이 섞인 블록을 통째로 붙이면 터미널에서 **일부 줄이 유실될 수 있다.**
> 명령이 조용히 건너뛰어져 뒤에서 `command not found`나
> `No such file or directory`로 나타나는데, 원인을 짐작하기 어렵다.
> **한 줄씩, 각 단계의 확인 명령을 함께 실행한다.**

**쿠버네티스는 컨테이너를 직접 실행하지 않는다.** kubelet은 지시만 하고
실제 실행은 런타임에게 맡긴다.

```
kubelet ──CRI──► containerd ──OCI──► runc ──► 커널(namespace + cgroup)
```

Docker를 쓰지 않는 이유는 **Docker가 CRI를 말할 줄 몰라** `dockershim` 어댑터가
필요했고 그것이 v1.24에서 제거됐기 때문이다. Docker 내부에도 이미 containerd가 있다.

자세한 내용은 [`notes/kubernetes/container-runtime.md`](../../notes/kubernetes/container-runtime.md).


```bash
sudo apt-get update
sudo apt-get install -y containerd
containerd --version
```

### 3-1. 설정 생성 — 반드시 `config default`로

```bash
sudo mkdir -p /etc/containerd
containerd config default | sudo tee /etc/containerd/config.toml >/dev/null
head -3 /etc/containerd/config.toml
# version = 3                    ← containerd 2.x 는 스키마 3
```

> ⚠️ **인터넷의 옛 `config.toml` 예제를 붙여넣지 말 것.**
> containerd 1.x는 `version = 2`였고 플러그인 키 이름도 다르다.
> 그대로 쓰면 containerd가 뜨지 않는다. **반드시 `config default`로 생성한 뒤 수정한다.**

### 3-2. cgroup 드라이버 — 이 한 줄이 핵심

```bash
sudo sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' /etc/containerd/config.toml
grep SystemdCgroup /etc/containerd/config.toml
# SystemdCgroup = true

sudo systemctl restart containerd
sudo systemctl status containerd
```

**왜 필요한가.** systemd가 cgroup 계층의 유일한 관리자여야 한다.
kubelet은 systemd cgroup 드라이버를 쓰는데 containerd가 다른 드라이버(cgroupfs)를 쓰면
**같은 자원을 두 관리자가 다르게 보게 되어** 메모리 압박 상황에서 예측 불가능하게 동작한다.

빠뜨리면 kubelet이 **조용히 실패한다.** 에러가 명확하지 않아 원인 찾기가 어렵다.

### 3-3. 동작 확인

```bash
sudo ctr version                  # containerd 자체 CLI
ls -l /run/containerd/containerd.sock
```

---

## 4. kubeadm · kubelet · kubectl 설치

```bash
sudo apt-get install -y apt-transport-https ca-certificates curl gpg
sudo mkdir -p /etc/apt/keyrings

curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.35/deb/Release.key \
  | sudo gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg

echo 'deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.35/deb/ /' \
  | sudo tee /etc/apt/sources.list.d/kubernetes.list

sudo apt-get update
sudo apt-get install -y kubelet kubeadm kubectl etcd-client
sudo apt-mark hold kubelet kubeadm kubectl
```

| 명령 | 뜻 |
|---|---|
| `gpg --dearmor` | 텍스트 키를 apt가 읽는 바이너리 형식으로 변환 |
| `signed-by=` | **이 저장소는 이 키로 서명된 것만 신뢰**한다는 선언 |
| `apt-mark hold` | 버전 고정. `apt upgrade`가 마음대로 올리지 못하게 |

> **`apt-mark hold`를 꼭 걸 것.** CKA에는 클러스터 업그레이드 문제가 나온다.
> 버전을 고정해 둬야 나중에 `kubeadm upgrade`를 *의도적으로* 연습할 수 있다.

```bash
kubeadm version
kubelet --version
kubectl version --client
apt-mark showhold
```

> 💡 **apt가 유난히 느리면 IPv4를 강제해본다.**
> `pkgs.k8s.io`의 DNS는 IPv6 주소를 먼저 반환하는데 VM에는 전역 IPv6가 없다.
> ```bash
> echo 'Acquire::ForceIPv4 "true";' | sudo tee /etc/apt/apt.conf.d/99force-ipv4
> ```

---

## 5. `kubeadm init`

### 5-1. 사전 점검

```bash
sudo kubeadm init phase preflight --dry-run 2>&1 | tail -20
```

경고가 나오면 **무시하기 전에 무엇에 대한 경고인지 읽는다.** 그 습관이 시험장에서도 필요하다.

### 5-2. 실행

```bash
sudo kubeadm init \
  --control-plane-endpoint=192.168.122.1:6443 \
  --apiserver-advertise-address=192.168.122.11 \
  --pod-network-cidr=10.244.0.0/16 \
  --service-cidr=10.96.0.0/12 \
  --upload-certs
```

> 💡 **`--kubernetes-version`은 생략한다.** 지정하지 않으면 kubeadm이
> **자신의 버전**으로 control plane을 띄우므로 kubelet·kubectl과 자동으로 맞는다.
>
> 굳이 지정하면 어긋날 수 있다. 예를 들어 설치된 것이 `1.35.8`인데
> `--kubernetes-version=v1.35.0`을 주면 control plane 컴포넌트만 `1.35.0`이 된다.
> 같은 마이너라 동작은 하지만 맞춰두는 편이 깔끔하다.
> (`kubeadm version`으로 확인할 수 있다.)

| 옵션 | 뜻 |
|---|---|
| `--control-plane-endpoint` | **클러스터의 영구 주소** = HAProxy. kubeconfig와 인증서 SAN에 박힌다 |
| `--apiserver-advertise-address` | apiserver가 바인딩할 **로컬** 주소. VM의 실제 IP여야 한다 |
| `--pod-network-cidr` | 파드에 나눠줄 대역. CNI 설정과 **반드시 일치**시킬 것 |
| `--service-cidr` | Service ClusterIP 대역 (기본값이지만 명시해 둔다) |
| `--upload-certs` | 인증서를 Secret으로 올려 **Stage 5에서 CP 추가**를 쉽게 한다 |

> **두 주소의 역할이 다르다.**
> `advertise-address`는 "내가 어디에 바인딩하는가"(로컬 인터페이스에 실제로 있어야 함),
> `control-plane-endpoint`는 "남들이 나를 어떻게 부르는가"다.

### 5-3. 출력에서 확인할 것

```
[certs] apiserver serving cert is signed for DNS names [k2-cp1 kubernetes ...]
        and IPs [10.96.0.1 192.168.122.11 192.168.122.1]
```

**SAN에 `.11`(자기 자신)과 `.1`(HAProxy)이 둘 다 들어가야 한다.**
`--control-plane-endpoint`를 준 효과이고, 이래서 나중에 엔드포인트를 바꾸면
인증서를 재발급해야 한다.

```
[control-plane-check] Checking kube-apiserver at https://192.168.122.11:6443/livez
```

kubeadm 자신의 헬스체크는 **엔드포인트가 아니라 로컬 주소**를 쓴다.
그래서 HAProxy가 없거나 방화벽이 막혀 있어도 `init` 자체는 성공한다.
**문제는 그 뒤에 kubelet이 엔드포인트로 붙을 때 드러난다** — 1-3절을 건너뛰면 안 되는 이유.

### 5-4. 출력을 반드시 저장한다

성공하면 마지막에 `kubeadm join` 명령이 두 종류 나온다.

```
# control plane 추가용 (Stage 5)
kubeadm join 192.168.122.1:6443 --token ... \
  --discovery-token-ca-cert-hash sha256:... \
  --control-plane --certificate-key ...

# 워커 추가용 (Stage 3)
kubeadm join 192.168.122.1:6443 --token ... \
  --discovery-token-ca-cert-hash sha256:...
```

**`labs/`에 그대로 복사해둔다.** 토큰은 기본 24시간 뒤 만료되지만
그때는 재발급하면 되고, 명령의 형태를 기록해두는 것이 중요하다.

> ⚠️ 토큰과 certificate-key는 **클러스터 가입 자격증명**이다.
> 공개 저장소이므로 값은 `<토큰>` 같은 자리표시자로 바꿔 적는다.

---

## 6. kubectl 설정

```bash
mkdir -p ~/.kube
sudo cp /etc/kubernetes/admin.conf ~/.kube/config
sudo chown $(id -u):$(id -g) ~/.kube/config

kubectl get nodes
# NAME     STATUS     ROLES           AGE   VERSION
# k2-cp1   NotReady   control-plane   1m    v1.35.0
```

**`NotReady`가 정상이다.** CNI가 아직 없어서 네트워크가 준비되지 않았다.

```bash
kubectl get pods -A
# coredns 두 개가 Pending — 역시 CNI 대기 중
```

### HAProxy가 살아났는지 확인

호스트에서:

```bash
curl -k -o /dev/null -w '%{http_code}\n' https://192.168.122.1:6443/healthz
```

`200`이나 `401`이면 성공이다. **HTTP 응답이 왔다는 것 자체가
TCP·TLS를 지나 apiserver에 닿았다는 뜻**이다. `curl: (7)`이면 실패다.

---

## 7. CNI — Calico

### 7-1. 왜 Calico인가

**Flannel은 NetworkPolicy를 지원하지 않는다.**
CKA의 Services & Networking(배점 20%)에 NetworkPolicy가 포함되므로
그 영역이 통째로 빠진다.

### 7-2. 오퍼레이터 설치

```bash
kubectl create -f https://raw.githubusercontent.com/projectcalico/calico/v3.32.2/manifests/tigera-operator.yaml
kubectl -n tigera-operator get pods -w    # Running 될 때까지
```

### 7-3. Installation 리소스 — MTU와 인터페이스가 핵심

```bash
cat <<'CALICO' > calico-install.yaml
apiVersion: operator.tigera.io/v1
kind: Installation
metadata:
  name: default
spec:
  calicoNetwork:
    mtu: 1370
    nodeAddressAutodetectionV4:
      interface: enp1s0
    ipPools:
      - name: default-ipv4-pool
        cidr: 10.244.0.0/16
        encapsulation: VXLAN
        natOutgoing: Enabled
        nodeSelector: all()
---
apiVersion: operator.tigera.io/v1
kind: APIServer
metadata:
  name: default
spec: {}
CALICO

kubectl create -f calico-install.yaml
```

| 항목 | 값 | 이유 |
|---|---|---|
| `mtu` | **1370** | Stage 4의 이중 캡슐화 대비. `wg0` 1420 − VXLAN 50 |
| `interface` | **`enp1s0`** | VM의 인터페이스 이름. 호스트의 `ens3`가 아니다 |
| `cidr` | `10.244.0.0/16` | `--pod-network-cidr`과 일치 |
| `encapsulation` | **VXLAN** | Stage 4에서 WireGuard `AllowedIPs` 필터를 통과하려면 필수 |

> **지금은 단일 노드라 MTU 1370이 필요 없다.** 그런데도 미리 잡는 이유는,
> Stage 4에서 값을 바꾸면 모든 파드를 재시작해야 하고
> "MTU 때문인가 다른 문제인가"를 가리기 어려워지기 때문이다.
> **변수를 미리 없앤다.**

### 7-4. 확인

```bash
kubectl get tigerastatus            # 전부 Available 될 때까지 (2~5분)
kubectl get pods -n calico-system
kubectl get nodes
# NAME     STATUS   ROLES           AGE   VERSION
# k2-cp1   Ready    control-plane   10m   v1.35.0     ← Ready!
```

---

## 8. taint와 첫 파드

```bash
kubectl describe node k2-cp1 | grep -A2 Taints
# Taints:  node-role.kubernetes.io/control-plane:NoSchedule
```

이 표시가 있으면 일반 파드가 배치되지 않는다.
control plane이 워크로드 부하로 느려지면 클러스터 전체가 흔들리기 때문이다.

지금은 노드가 하나뿐이므로 잠시 지운다.

```bash
kubectl taint nodes --all node-role.kubernetes.io/control-plane-
```

> 명령 끝의 `-`가 **제거**를 뜻한다. 붙이려면 `...control-plane:NoSchedule`.
>
> ⚠️ 옛 문서의 `node-role.kubernetes.io/master-`는 **v1.24에서 제거되어 동작하지 않는다.**

```bash
kubectl run nginx --image=nginx
kubectl get pods -o wide           # Running 확인
kubectl logs nginx
kubectl exec -it nginx -- ls /
```

`logs`와 `exec`가 되면 **apiserver → kubelet 경로가 정상**이라는 뜻이다.
Stage 0에서 다룬 노드 주소 문제가 없다는 확인이기도 하다.

### 실습을 마친 뒤 taint를 다시 건다

```bash
kubectl delete pod nginx
kubectl taint nodes k2-cp1 node-role.kubernetes.io/control-plane:NoSchedule
```

Stage 3에서 워커가 생기면 control plane은 관리에만 전념해야 하고,
남겨두면 **Workloads & Scheduling(배점 15%) 실습 재료**가 된다.

---

## 9. 검증

```bash
kubectl get nodes -o wide          # Ready, INTERNAL-IP 가 192.168.122.11 인지
kubectl get pods -A                # 모두 Running
kubectl cluster-info
kubectl get --raw='/readyz?verbose' | tail -20

# 호스트에서 — HAProxy 경유 확인
curl -k -o /dev/null -w '%{http_code}\n' https://192.168.122.1:6443/healthz
sudo ss -lntp | grep 6443
```

`INTERNAL-IP`가 `192.168.122.11`인지 반드시 확인한다.
다른 값이면 Stage 4에서 문제가 된다.

---

## 10. 스냅샷

여기까지 왔으면 **되돌아올 지점**을 만들어둔다.
Stage 3에서 뭔가 잘못돼도 여기로 돌아올 수 있다.

```bash
# 호스트에서 — VM 을 정상 종료한 뒤가 안전하다
virsh shutdown k2-cp1
virsh list --all                            # shut off 확인
virsh snapshot-create-as k2-cp1 --name stage2-done --description "단일 노드 클러스터 완성"
virsh start k2-cp1
```

VM이 정지 상태면 디스크만 저장해 빠르고 용량도 작다.

---

## 완료 후

- [`labs/`](../../labs/)에 실제로 친 명령과 출력을 기록
- **`kubeadm join` 명령을 저장**해둘 것 (토큰 값은 자리표시자로)
- 막힌 것은 틀린 가설까지 포함해서
- 다음: [Stage 3 — 다중 노드](stage-03-multi-node.md)

## 자주 막히는 곳

| 증상 | 확인 |
|---|---|
| kubelet이 계속 재시작 | `sudo journalctl -u kubelet -f`, `SystemdCgroup = true` 확인 |
| `kubeadm init`이 apiserver 대기에서 멈춤 | `sudo crictl ps -a`, `/var/log/pods/` |
| 노드가 계속 `NotReady` | CNI 파드 상태 — `kubectl get pods -n calico-system` |
| `logs`·`exec` 타임아웃 | 노드 `INTERNAL-IP`가 맞는지 → [주소 문제](../../notes/network/concepts/02_node-addressing.md) |
| HAProxy 502 / 연결 거부 | 백엔드 상태 — `:8404/stats`, `mode tcp`인지 |
| coredns가 `Pending` | CNI 미설치. 정상 순서다 |

관련: [`notes/infra/haproxy.md`](../../notes/infra/haproxy.md) ·
[`notes/kubernetes/etcd.md`](../../notes/kubernetes/etcd.md) ·
[`notes/network/diagnosis/`](../../notes/network/diagnosis/)

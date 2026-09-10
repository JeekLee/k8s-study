# 학습 로드맵 — Stage 0 → 7

> 클러스터를 세우는 과정 자체를 CKA 학습 경로로 삼는다.
> 각 단계는 앞 단계가 **동작한다는 전제** 위에 서 있다. 완료 기준을 통과해야 다음으로 간다.

## 최종 목표

| 항목 | 값 |
|---|---|
| 구성 | **6노드** — control plane 3 + worker 3 |
| 호스트 | k8s-1 + k8s-2 (둘 다 하이퍼바이저 역할만, 클러스터에 미참여) |
| 노드 간 연결 | WireGuard 사이트 간 터널 + 서브넷 라우팅 |
| 버전 | Kubernetes v1.35 · containerd 2.2.2 · Calico |
| 예상 기간 | 6–10주 (병행 학습 기준) |

## 순서에 대한 판단

**네트워크 작업을 Stage 4로 미룬다.** k8s-2 안에서만 클러스터를 만들면 네트워크가 저절로 되므로,
터널 없이 Stage 3까지 갈 수 있고 **훨씬 빨리 동작하는 클러스터를 손에 넣는다.**

부수 효과로 **Stage 3까지는 단일 호스트 구성과 완전히 공통**이다.
나중에 크로스 호스트를 포기해도 Stage 1–3은 그대로 쓰인다.

## 전체 지도

| Stage | 내용 | 상태 |
|---|---|---|
| 0 | 기반 개념과 진단 도구 | ✅ 완료 |
| 1 | 가상화 기반 (libvirt, 스냅샷) | ← 다음 |
| 2 | 첫 클러스터 (단일 노드) | |
| 3 | 다중 노드 (호스트 내부) | |
| 4 | 크로스 호스트 라우팅 | |
| 5 | HA control plane (6노드 완성) | |
| 6 | CKA 영역별 실습 | |
| 7 | 시험 대비 마무리 | |

---

## Stage 0 — 기반 개념과 진단 도구 ✅

클러스터를 만들기 전에 "왜 그냥은 안 되는가"를 먼저 이해했다.
이 단계 없이 명령만 따라 쳤다면 Stage 4에서 반드시 막혔을 것이다.

- 사설 IP가 전역 고유하지 않다는 것, CIDR 중복 시 피어링이 불가능한 이유
  → [`notes/network/concepts/01_vcn-vpc.md`](../notes/network/concepts/01_vcn-vpc.md)
- **노드 주소 문제** — 포트를 다 열어도 클러스터가 성립하지 않는 구조
  → [`notes/network/concepts/02_node-addressing.md`](../notes/network/concepts/02_node-addressing.md)
- 진단 도구를 계층별로 → [`notes/network/diagnosis/`](../notes/network/diagnosis/)
- etcd와 쿼럼 → [`notes/kubernetes/etcd.md`](../notes/kubernetes/etcd.md)

**완료 확인** — 두 노드 간 사설 통신 불가, 공인 tcp/22 양방향 가능을 실측하고 문서화했다.

---

## Stage 1 — 가상화 기반

**목표** — VM을 자유롭게 만들고, 부수고, 되돌릴 수 있는 상태.
성과물은 **스냅샷으로 몇 초 만에 되돌아오는 실습 환경**이다. Troubleshooting 훈련의 기반이 여기서 만들어진다.

쿠버네티스는 아직 설치하지 않는다.

```bash
sudo apt-get install -y qemu-system-x86 qemu-utils \
  libvirt-daemon-system libvirt-clients virtinst \
  bridge-utils cloud-image-utils
sudo usermod -aG libvirt,kvm $USER   # 재로그인 필요
virsh list --all
```

- libvirt 네트워크를 **routed 모드**로 정의 (Stage 4를 위해 지금 해둔다)
- k8s-2 대역 `192.168.122.0/24`, k8s-1은 나중에 `192.168.121.0/24`
- cloud image + cloud-init으로 VM 생성 자동화
- 스냅샷 — `virsh snapshot-create-as` / `snapshot-revert`

> ⚠️ **Ubuntu 26.04에는 `qemu-kvm` 패키지가 없다.** `qemu-system-x86`으로 바뀌었다.
> 인터넷의 옛 KVM 설치 문서를 그대로 따라 하면 `Unable to locate package`가 난다.

**완료 기준** — VM이 부팅되고 SSH로 들어가지며, 스냅샷을 찍고 되돌렸을 때 변경이 사라진다.

---

## Stage 2 — 첫 클러스터 (단일 노드)

**목표** — `kubectl get nodes`가 처음으로 동작한다. 가장 큰 이정표.

노드 하나로 시작한다. 여기서 막히면 노드를 늘려도 똑같이 막히므로 한 대에서 완전히 이해하고 넘어간다.

> ⚠️ **HAProxy를 지금 세운다.** control plane이 나중에 3대가 되므로 `--control-plane-endpoint`가 필요하다.
> 나중에 바꾸려면 **인증서를 전부 재발급**해야 한다. 처음부터 HAProxy를 거치게 잡으면 Stage 5에서 재구축을 피할 수 있다.
> → [`notes/infra/haproxy.md`](../notes/infra/haproxy.md)

```bash
# 런타임 — 이 한 줄을 빠뜨리면 kubelet이 조용히 실패한다
sudo sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' /etc/containerd/config.toml

sudo kubeadm init \
  --control-plane-endpoint=192.168.122.1:6443 \
  --pod-network-cidr=10.244.0.0/16 \
  --upload-certs \
  --kubernetes-version=v1.35.0
```

- containerd 설정은 반드시 `containerd config default`로 생성 (2.x는 스키마 version 3)
- kubeadm/kubelet/kubectl 1.35 설치 후 `apt-mark hold`
- **Calico + MTU** — Stage 4를 대비해 `mtu: 1370`으로 미리 잡아둔다
- taint를 잠시 지워 파드를 띄워보고 **다시 걸어둔다** (실습 재료로 남긴다)

**완료 기준** — `kubectl run nginx --image=nginx`로 띄운 파드가 `Running`이 되고 `kubectl logs`가 나온다.

---

## Stage 3 — 다중 노드 (호스트 내부)

**목표** — 파드가 노드를 넘나드는 것을 눈으로 확인한다.

워커 VM 2대를 추가한다. 아직 k8s-2 안이라 네트워크는 저절로 된다.
**스케줄러의 동작을 관찰하는 것이 핵심**이다.

- `kubeadm join` — 토큰과 CA 해시가 무엇인지, 만료되면 어떻게 재발급하는지
- Deployment 여러 개를 replica 2~3으로 띄우고 `kubectl get pods -o wide`로 분산 관찰
- `requests`를 안 적었을 때 한쪽에 몰리는 현상 재현
- `topologySpreadConstraints`, `podAntiAffinity`로 분산 강제
- `cordon` → `drain` → `uncordon` — 파드가 옮겨가는 것 확인
- 워커 하나에서 kubelet을 죽여 `NotReady`를 만들고 복구

**완료 기준** — 3노드가 `Ready`이고, 한 워커를 `drain`했을 때 파드가 다른 노드에서 재생성된다.

---

## Stage 4 — 크로스 호스트 라우팅

**목표** — 두 호스트의 VM이 하나의 사설망처럼 통신한다. Stage 0에서 정리한 개념이 전부 쓰인다.

가장 어렵고 가장 배울 것이 많은 단계다.
**VM들은 터널의 존재를 모른다** — 호스트끼리만 연결하고 각자의 VM 대역을 서로에게 라우팅해준다.

```ini
# WireGuard peer — AllowedIPs 에 상대 VM 대역까지 넣는 것이 핵심
# k8s-1 쪽
AllowedIPs = 10.10.0.0/24, 192.168.122.0/24
# k8s-2 쪽
AllowedIPs = 10.10.0.0/24, 192.168.121.0/24
```

```bash
# 호스트를 라우터로
echo 'net.ipv4.ip_forward=1' | sudo tee /etc/sysctl.d/99-router.conf
sudo sysctl --system
sudo iptables -A FORWARD -i virbr0 -o wg0 -j ACCEPT
sudo iptables -A FORWARD -i wg0 -o virbr0 -j ACCEPT
```

- OCI 보안 목록에 UDP 51820 양방향 (소스는 상대 공인 IP `/32`)
- k8s-1에 libvirt 설치, 대역을 `192.168.121.0/24`로 분리
- VM 3대 생성 후 `kubeadm join`

> ⚠️ **MTU가 이 단계의 진짜 함정이다.**
> `ens3` 1500 → `wg0` 1420 → VXLAN −50 → **파드 MTU 1370**.
> 맞추지 않으면 작은 요청은 되는데 **큰 응답만 멈춘다.**
> 이미지 pull이나 큰 API 응답이 타임아웃되는 식이라 원인 찾기가 매우 어렵다.

**완료 기준** — `vm-cp1`(192.168.121.11)에서 `vm-w2`(192.168.122.21)로 ping이 되고,
두 호스트의 VM이 한 클러스터에서 `Ready`다. 큰 패킷 테스트(`ping -s 1400`)도 통과한다.

---

## Stage 5 — HA control plane

**목표** — control plane 3대로 쿼럼을 만들고 **직접 깨뜨려본다.**

```bash
sudo kubeadm join <endpoint>:6443 --token ... \
  --discovery-token-ca-cert-hash ... \
  --control-plane --certificate-key ...
```

- etcd 멤버 확인 — `etcdctl member list`
- **쿼럼 실험** — CP 1대 정지 → 클러스터 생존 / 2대 정지 → 정지. 직접 확인
- etcd 스냅샷 백업 → 오브젝트 삭제 → 복구. **CKA 단골 문제**
- 인증서 만료일 확인과 갱신 — `kubeadm certs check-expiration`

> ⚠️ **호스트가 2개라 HA는 절반만 된다.**
> etcd 3멤버를 2+1로 나눌 수밖에 없어, CP 2대가 있는 호스트가 죽으면 쿼럼이 깨진다.
> 진짜 HA는 장애 도메인 3개가 필요하다.
> **이 한계를 직접 겪는 것이 쿼럼을 이해하는 가장 좋은 방법이다.**

**완료 기준** — 6노드가 `Ready`이고, etcd 스냅샷에서 클러스터를 복구해봤다.

---

## Stage 6 — CKA 영역별 실습

Stage 1–5를 지나면 배점 25%인 Cluster Architecture 영역은 이미 상당 부분 몸에 남아 있다.
남은 것을 배점 순으로 채운다.

| 영역 | 배점 | 할 것 |
|---|---:|---|
| **Troubleshooting** | 30% | kubelet 정지, 인증서 만료 조작, CNI 훼손, wg0 다운, etcd 복구.<br>**스냅샷을 찍고 마음껏 부순다** — 이 단계가 스냅샷의 존재 이유 |
| Cluster Architecture, Install & Config | 25% | 대부분 Stage 1–5에서 완료. 추가로 RBAC, `kubeadm upgrade`, Helm·Kustomize, CRD·오퍼레이터 |
| Services & Networking | 20% | Calico NetworkPolicy, CoreDNS, Ingress, Gateway API |
| Workloads & Scheduling | 15% | Stage 3에서 시작한 것을 심화. taint/toleration, affinity, HPA |
| Storage | 10% | StorageClass, PV/PVC, 동적 프로비저닝 |

**완료 기준** — 각 영역의 대표 작업을 문서 없이 수행할 수 있다. 막힌 것은 `notes/`에 기록되어 있다.

---

## Stage 7 — 시험 대비 마무리

**목표** — 아는 것을 **2시간 안에** 해내는 훈련.

시험은 2시간에 17–25문항이고, 브라우저 탭 하나로 `kubernetes.io/docs`만 볼 수 있다. **속도가 곧 점수다.**

- `alias k=kubectl`, 자동완성, `--dry-run=client -o yaml` 습관화
- 공식 문서에서 원하는 YAML을 **몇 초 만에** 찾는 훈련
- `kubectl explain`으로 필드 확인 — 문서보다 빠를 때가 많다
- killer.sh 모의 시험 (실제 시험보다 어렵다. 여기서 통과하면 충분)
- 시간 재고 전 영역 순회

**완료 기준** — 모의 시험을 제한 시간 안에 통과.

---

## 진행 원칙

1. **완료 기준을 통과해야 다음 단계로.** Stage 2에서 대충 넘긴 것은 Stage 4에서 두 배로 돌아온다.
2. **명령을 붙여넣기 전에 왜 그 값인지 적는다.** 특히 IP 대역과 포트.
3. **막힌 것은 지우지 않는다.** 실패 기록이 배점 30%짜리 영역의 학습 자료다.
4. **스냅샷을 습관화한다.** Stage 1 이후로는 무엇을 하든 먼저 스냅샷을 찍는다.
   부수는 데 드는 심리적 비용이 0이 되면 학습 속도가 달라진다.
5. **Stage 3까지는 방향 확정 없이 진행 가능하다.**

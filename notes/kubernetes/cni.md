# CNI와 Calico — 파드 네트워킹

**CNI는 규약이고 Calico는 그 구현이다.**
containerd와 CRI의 관계와 정확히 같다 → [`container-runtime.md`](container-runtime.md)

## 쿠버네티스는 네트워크를 직접 만들지 않는다

지켜야 할 **규칙만** 정한다.

1. 모든 파드는 **자기만의 IP**를 갖는다
2. 파드끼리 **NAT 없이** 통신한다
3. 노드도 모든 파드와 NAT 없이 통신한다
4. **파드가 보는 자기 IP == 남이 보는 그 파드의 IP**

**어떻게 구현할지는 정하지 않는다.** CNI 플러그인에게 맡긴다.

> 4번이 [노드 주소 문제](../network/concepts/02_node-addressing.md)와 같은 원리다.
> 쿠버네티스는 "주소가 일치한다"를 여러 계층에서 전제한다.

## 파드가 뜰 때 일어나는 일

```
kubelet → containerd → /opt/cni/bin/ 의 플러그인 실행
                         │
                         ├ veth 쌍 생성 (한쪽은 파드 netns, 한쪽은 호스트)
                         ├ IP 할당 (IPAM)
                         └ 라우팅 · iptables 설정
```

`veth`는 **가상 랜선 한 가닥**이다. 한쪽 끝을 파드의 네트워크 네임스페이스에,
다른 쪽을 호스트에 꽂는다. libvirt가 VM마다 만드는 `vnet0`과 같은 발상이고,
Calico가 만드는 파드용은 호스트에서 `cali*`로 보인다.

```bash
ip addr | grep cali          # 파드 하나당 하나씩 늘어난다
```

설정 파일 위치:

| 경로 | 내용 |
|---|---|
| `/etc/cni/net.d/` | CNI 설정 (어떤 플러그인을 어떻게 쓸지) |
| `/opt/cni/bin/` | 플러그인 실행 파일 |

## CNI가 없으면 노드가 `NotReady`다

kubelet은 `/etc/cni/net.d/`가 비어 있으면 네트워크가 준비되지 않았다고 보고한다.

```bash
kubectl describe node <노드> | grep -A3 Conditions
# NetworkReady=false ... cni plugin not initialized
```

파드를 띄울 수 없으니 CoreDNS도 `Pending`에 머문다.
**고장이 아니라 순서다.** `kubeadm init` 직후에는 항상 이 상태다.

> ⚠️ **`kubernetes-cni` 패키지는 Calico가 아니다.**
> kubeadm 설치 시 함께 들어오는 이 패키지는 `bridge`, `host-local`, `loopback` 같은
> **표준 플러그인 모음**이다. Calico 같은 CNI가 이것들을 부품으로 쓴다.
> 이게 깔려 있어도 노드는 여전히 `NotReady`다.

## 구현체 비교

| 구현 | 방식 | NetworkPolicy | 비고 |
|---|---|---|---|
| **Flannel** | VXLAN | ❌ **미지원** | 가장 단순 |
| **Calico** | VXLAN / IPIP / BGP / eBPF | ✅ | 가장 널리 쓰임 |
| **Cilium** | eBPF | ✅ | L7 정책, 관측성 강함 |
| 클라우드 CNI | 파드가 VPC IP를 직접 받음 | 부분적 | AWS VPC CNI 등 |

> **Flannel을 쓰지 않는 이유가 NetworkPolicy다.**
> CKA의 Services & Networking(배점 20%)에 포함되어 있어,
> Flannel을 고르면 그 영역을 통째로 실습할 수 없다.

**NetworkPolicy**는 파드 간 통신을 제어하는 방화벽이다.
쿠버네티스 기본값은 **모두 허용**이고, 정책을 걸어야 제한된다.
그런데 쿠버네티스 자신은 이를 집행하지 않는다 — **CNI가 한다.**
그래서 지원하지 않는 CNI에서는 NetworkPolicy를 만들어도 아무 일이 일어나지 않는다.

## Calico

파드 네트워킹과 NetworkPolicy 집행을 함께 한다. Tigera가 개발하는 오픈소스.

| 구성 요소 | 역할 |
|---|---|
| `calico-node` (DaemonSet) | 각 노드에서 라우팅·정책 집행 (Felix), BGP 필요 시 BIRD |
| `calico-kube-controllers` | 클러스터 상태 감시, IPAM 정리 |
| `tigera-operator` | 위 것들을 설치·관리하는 오퍼레이터 |

### 데이터플레인 모드

| 모드 | 동작 | 특징 |
|---|---|---|
| **VXLAN** | 파드 패킷을 UDP로 감싸 노드 IP로 전송 | 언더레이 무관하게 동작 |
| **IPIP** | IP-in-IP 캡슐화 | VXLAN 보다 오버헤드가 조금 작음 |
| **None (BGP)** | 캡슐화 없이 라우터에 경로 광고 | 가장 빠름. 네트워크 장비 협조 필요 |
| **eBPF** | kube-proxy 까지 대체 | 빠름. 커널 버전 요구 |

`VXLANCrossSubnet`은 노드가 다른 서브넷일 때만 캡슐화하는 절충안이다.

### 이 프로젝트의 설정

```yaml
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
```

| 항목 | 값 | 이유 |
|---|---|---|
| `encapsulation` | **VXLAN** | Stage 8 에서 WireGuard `AllowedIPs` 필터를 통과하려면 필수 |
| `mtu` | **1370** | `wg0` 1420 − VXLAN 50 |
| `interface` | **`enp1s0`** | VM 의 인터페이스. 호스트의 `ens3`가 아니다 |
| `cidr` | `10.244.0.0/16` | `kubeadm init --pod-network-cidr`과 일치해야 한다 |

> **왜 VXLAN이 필수인가.**
> Stage 8 에서 파드 패킷이 WireGuard 터널을 지나야 하는데,
> `AllowedIPs`에 파드 대역(`10.244.0.0/16`)이 없어서
> **캡슐화하지 않으면 수신 필터에 걸려 조용히 버려진다.**
> VXLAN 으로 감싸면 바깥 헤더 출발지가 노드 IP(`192.168.12x.x`)가 되어 통과한다.
> → [`../network/reference/wireguard.md`](../network/reference/wireguard.md)

`natOutgoing: Enabled`는 파드가 클러스터 **밖으로** 나갈 때 노드 IP로 SNAT 한다는 뜻이다.
외부는 파드 대역을 모르므로 필요하다 — [Stage 1 의 MASQUERADE](../infra/nat-iptables.md)와 같은 원리다.

## 진단

```bash
kubectl get tigerastatus                    # 전부 Available 이어야 한다
kubectl get pods -n calico-system -o wide
kubectl get pods -n tigera-operator

# 노드에서
ls /etc/cni/net.d/                          # 설정 파일이 있는가
ls /opt/cni/bin/                            # calico 바이너리가 있는가
ip addr | grep -E 'cali|vxlan'              # 인터페이스가 생겼는가
sudo calicoctl node status                  # (calicoctl 설치 시)
```

| 증상 | 확인 |
|---|---|
| 노드가 계속 `NotReady` | `kubectl get pods -n calico-system` — 파드가 뜨는가 |
| `calico-node`가 `CrashLoopBackOff` | `kubectl logs -n calico-system <파드>` — 인터페이스 자동탐지 실패가 흔함 |
| 파드는 뜨는데 통신 불가 | MTU, 캡슐화 모드, 파드 CIDR 불일치 |
| **큰 패킷만 멈춤** | **MTU** → [`../network/concepts/03_interfaces.md`](../network/concepts/03_interfaces.md) |
| NetworkPolicy 가 무시됨 | CNI 가 지원하는지 확인 (Flannel 이면 미지원) |

## 관련

- 런타임과 CRI → [`container-runtime.md`](container-runtime.md)
- MTU 계층 → [`../network/concepts/03_interfaces.md`](../network/concepts/03_interfaces.md)
- WireGuard `AllowedIPs` → [`../network/reference/wireguard.md`](../network/reference/wireguard.md)

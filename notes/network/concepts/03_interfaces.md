# 네트워크 인터페이스 읽기

`ip addr`을 쳤을 때 무엇이 무엇인지. 클러스터가 커질수록 인터페이스가 늘어나므로
종류를 구분할 줄 알아야 한다.

## 출력 읽는 법

```
2: ens3: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9000 qdisc mq state UP group default qlen 1000
   link/ether 02:00:17:xx:xx:xx brd ff:ff:ff:ff:ff:ff
   altname enp0s3
   inet 10.0.0.169/24 metric 100 brd 10.0.0.255 scope global dynamic ens3
      valid_lft 47918sec preferred_lft 47918sec
   inet6 fe80::17ff:fexx:xxxx/64 scope link proto kernel_ll
```

| 항목 | 뜻 |
|---|---|
| `2:` | 인터페이스 인덱스. 커널이 부여한 순번 |
| `<UP,LOWER_UP>` | `UP` = 관리적으로 켜짐, `LOWER_UP` = **케이블이 실제로 연결됨** |
| `<NO-CARRIER>` | 켜져 있지만 연결된 것이 없음 |
| `mtu` | 한 번에 보낼 수 있는 최대 크기(바이트) |
| `state UP / DOWN` | 실제 동작 상태 |
| `link/ether` | MAC 주소. `02:`로 시작하면 **로컬 관리 주소**(클라우드·가상화가 부여) |
| `altname` | 같은 카드의 다른 이름 |
| `inet` | IPv4 주소와 프리픽스 |
| `dynamic` | **DHCP로 받은 주소.** 고정이 아님 |
| `valid_lft` | 임대 만료까지 남은 시간. 자동 갱신된다 |
| `metric` | 라우팅 우선순위. 낮을수록 우선 |
| `inet6 fe80::` | 링크 로컬 IPv6. 자동 생성, 같은 링크 안에서만 유효 |

## 인터페이스 종류

### `lo` — 루프백

물리적으로 존재하지 않는 가상 인터페이스. **자기 자신과 통신할 때** 쓴다.
`127.0.0.1`로 보낸 패킷은 절대 기계 밖으로 나가지 않는다.

쿠버네티스에서 중요하다.

- etcd가 `127.0.0.1:2379`로 로컬 클라이언트를 받는다 → `etcdctl --endpoints=https://127.0.0.1:2379`
- kubelet의 healthz, 각 컴포넌트의 메트릭 엔드포인트가 localhost에 있다
- `ss -lntp`에서 바인딩 주소가 `127.0.0.1`이면 **외부에서 접근 불가**다
  → [`../diagnosis/04_ss.md`](../diagnosis/04_ss.md)

### `ens3` — 물리(가상화된) NIC

systemd의 **예측 가능한 인터페이스 이름** 규칙을 따른다. 예전 `eth0`을 대체했다.

```
ens3
││└─ 슬롯 번호
│└── s = hotplug slot
└─── en = Ethernet
```

| 접두사 | 뜻 | 예 |
|---|---|---|
| `en` | Ethernet | `ens3`, `enp0s3` |
| `wl` | 무선 LAN | `wlp2s0` |
| `s<N>` | 핫플러그 슬롯 | `ens3` |
| `p<N>s<N>` | PCI 버스/슬롯 | `enp0s3` |
| `x<MAC>` | MAC 기반 | `enx02001701...` |

`eth0` 같은 옛 이름은 커널이 인식한 순서대로 붙어서 **재부팅하면 바뀔 수 있었다.**
버스 위치나 슬롯 기반으로 이름을 지으면 항상 같은 이름이 나온다.

> ⚠️ **클라우드 VM에는 공인 IP가 인터페이스에 없다.**
> 1:1 NAT으로 인스턴스 바깥에서 변환되기 때문이다.
> → [`02_node-addressing.md`](02_node-addressing.md)

### `virbr*` — libvirt 가상 브리지

VM들이 물리는 **가상 스위치**. `virbr0`은 libvirt의 기본 `default` 네트워크,
`virbr1`은 우리가 정의한 `k8snet`이다.

```
4: virbr1: <NO-CARRIER,BROADCAST,MULTICAST,UP> mtu 1500 ... state DOWN
   link/ether 52:54:00:xx:xx:xx
   inet 192.168.122.1/24 ...
```

- `inet 192.168.122.1` — 네트워크 XML에 적은 **게이트웨이 주소**.
  호스트가 이 가상 네트워크에서 갖는 주소다
- `52:54:00` — QEMU/KVM에 할당된 MAC 접두사
- **`NO-CARRIER` / `state DOWN`은 VM이 하나도 안 붙었을 때 정상**이다.
  스위치는 켜져 있는데 케이블이 안 꽂힌 상태. VM을 만들면 `UP`으로 바뀐다

### `vnet*` — VM 한 대당 하나

VM을 만들면 호스트 쪽에 `vnet0`, `vnet1`... 이 생기고 `virbr1`에 붙는다.
**VM의 랜선 한 가닥**에 해당한다. VM 안에서는 이것이 `ens3`로 보인다.

```bash
virsh domiflist k2-cp1     # 어느 vnet 인지 확인
ip link show master virbr1 # virbr1 에 붙은 것들
```

### `wg0` — WireGuard 터널 (Stage 8)

커널이 만드는 가상 인터페이스. 여기로 보낸 패킷은 암호화되어 UDP로 나간다.
→ [`../reference/wireguard.md`](../reference/wireguard.md)

### 앞으로 보게 될 것들 (Stage 2 이후)

CNI를 설치하면 인터페이스가 확 늘어난다.

| 이름 | 정체 |
|---|---|
| `cali*` | Calico가 파드마다 만드는 veth. 파드 하나당 하나 |
| `vxlan.calico` | Calico의 VXLAN 종단점. 노드 간 파드 트래픽이 여기로 캡슐화된다 |
| `veth*` | 가상 이더넷 쌍. 한쪽은 파드 네임스페이스, 한쪽은 호스트 |
| `flannel.1` | Flannel을 쓸 경우의 VXLAN 인터페이스 |
| `cni0` | 일부 CNI가 쓰는 브리지 |
| `kube-ipvs0` | kube-proxy를 IPVS 모드로 쓸 때 |

파드가 늘어나면 `cali*`가 수십 개 생긴다. `ip addr`이 길어져도 놀랄 것 없다.

---

## MTU — 계층이 쌓이면 줄어든다

각 캡슐화가 헤더를 붙이므로 **안쪽으로 갈수록 실을 수 있는 데이터가 줄어든다.**

| 계층 | MTU | 오버헤드 |
|---|---|---|
| `ens3` (VCN 내부) | **9000** | — 점보 프레임 |
| 공용 인터넷 경로 | 보통 1500 | — |
| `wg0` | **1420** | WireGuard 80 |
| 파드 (VXLAN) | **1370** | VXLAN 50 |

### ⚠️ `ens3`가 9000이라는 점이 함정이다

실측 결과 이 환경의 `ens3` MTU는 **9000**이다. OCI가 VCN 내부용으로 점보 프레임을 잡아뒀다.

`wg-quick`은 `MTU`를 명시하지 않으면 **엔드포인트로 가는 경로의 MTU에서 80을 빼서**
자동으로 정한다. `ens3`가 9000이므로 `wg0`에 **8920**을 잡을 수 있다.

그런데 **공용 인터넷 경로는 보통 1500**이다. 8920짜리 패킷은 중간에서 조용히 버려진다.

**해결: 자동 계산에 맡기지 말고 명시한다.**

```ini
[Interface]
MTU = 1420
```

### 증상이 고약하다

MTU 불일치는 "연결이 안 됨"이 아니라 **"작은 것은 되는데 큰 것만 멈춤"** 으로 나타난다.

| 되는 것 | 안 되는 것 |
|---|---|
| `ping` (작은 패킷) | 이미지 pull |
| `kubectl get pods` | `kubectl logs`의 긴 출력 |
| TCP 연결 수립 | 큰 API 응답, 파일 전송 |

연결은 되니까 네트워크를 의심하지 않게 되어 원인 찾기가 매우 어렵다.

```bash
# MTU 확인 — DF 비트를 세워 조각화를 막고 크기를 키워본다
ping -c3 -M do -s 1372 10.10.0.2    # 1372 + 28(헤더) = 1400
ping -c3 -M do -s 1472 10.10.0.2    # 1500 — 실패하면 경로 MTU가 더 작다
```

`-M do`는 "조각화하지 말라"는 뜻이다. 이게 없으면 커널이 알아서 쪼개서
문제가 드러나지 않는다.

## 관련

- 진단 명령 → [`../diagnosis/`](../diagnosis/)
- 주소 문제 → [`02_node-addressing.md`](02_node-addressing.md)
- WireGuard → [`../reference/wireguard.md`](../reference/wireguard.md)

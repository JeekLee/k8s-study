# Stage 4 — 크로스 호스트 라우팅

| | |
|---|---|
| 대상 | k8s-1 + k8s-2 |
| 예상 소요 | 하루 |
| 선행 | [Stage 3](stage-03-multi-node.md) |
| 기록할 곳 | `labs/stage-04-cross-host.md` |

> 📝 계획 수준. 진입 시 확장한다.

## 목표

두 호스트의 VM이 하나의 사설망처럼 통신한다.
**Stage 0에서 정리한 개념이 전부 쓰인다.** 가장 어렵고 가장 배울 것이 많다.

핵심: **VM들은 터널의 존재를 모른다.** 호스트끼리만 연결하고
각자의 VM 대역을 서로에게 라우팅해준다.

## 완료 기준

- [ ] `k1-cp1`(192.168.121.11)에서 `k2-w1`(192.168.122.21)로 ping
- [ ] 두 호스트의 VM이 한 클러스터에서 `Ready`
- [ ] 큰 패킷 테스트 통과 (`ping -s 1400`)

## 할 일

### ① Stage 0에서 이월된 검증

OCI 보안 목록에 UDP 51820 인그레스 (양쪽 VCN, 소스는 상대 공인 IP `/32`).
그리고 [`notes/network/README.md`](../../notes/network/README.md#phase-0-연결성-점검-절차) 3·4단계로 양방향 통과 확인.

### ② 호스트 간 WireGuard

`AllowedIPs`에 **상대 VM 대역까지** 넣는 것이 핵심이다.

```ini
# k8s-1 쪽 [Peer]
AllowedIPs = 10.10.0.0/24, 192.168.122.0/24
# k8s-2 쪽 [Peer]
AllowedIPs = 10.10.0.0/24, 192.168.121.0/24
```

### ③ 호스트를 라우터로

```bash
sudo iptables -A FORWARD -i virbr1 -o wg0 -j ACCEPT
sudo iptables -A FORWARD -i wg0 -o virbr1 -j ACCEPT
```

`ip_forward`와 인터넷용 MASQUERADE는 Stage 1에서 이미 걸었다.
**`wg0`로 나가는 트래픽에는 NAT을 걸지 않는다** — 출발지 주소가 보존돼야 한다.

### ④ k8s-1에 VM 구성

Stage 1과 동일하되 대역만 `192.168.121.0/24`. VM 3대 생성 후 `kubeadm join`.

## ⚠️ MTU — 이 단계의 진짜 함정

```
ens3   1500
 └ wg0  1420   (WireGuard 오버헤드 80)
    └ VXLAN 1370   ← 파드 MTU
```

맞추지 않으면 **작은 요청은 되는데 큰 응답만 멈춘다.**
이미지 pull이나 큰 API 응답이 타임아웃되는 식이라 원인 찾기가 매우 어렵다.
Stage 2에서 미리 1370으로 잡아둔 이유다.

다음: [Stage 5 — HA control plane](stage-05-ha.md)

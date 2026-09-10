# 05. `wg` — 터널 상태 확인

WireGuard 전용 진단. 터널이 한 겹 더 있으므로 **"wg 문제인가 k8s 문제인가"를 가르는 것**이 핵심이다.
이 구분을 못 하면 Phase 1 이후 모든 장애에서 헤맨다.

## 기본 명령

```bash
sudo wg show                          # 전체 상태
sudo wg show wg0 latest-handshakes    # 마지막 핸드셰이크 시각만
sudo systemctl status wg-quick@wg0    # 서비스 상태
ip addr show wg0                      # 터널 인터페이스 주소
ip route | grep wg0                   # 터널로 가는 라우팅
```

## 출력 읽는 법

```
interface: wg0
  public key: abc123...
  private key: (hidden)
  listening port: 51820

peer: xyz789...
  endpoint: 198.51.100.22:51820
  allowed ips: 10.10.0.0/24
  latest handshake: 51 seconds ago      ← 이 줄이 핵심
  transfer: 1.23 MiB received, 892 KiB sent
```

| 항목 | 판정 |
|---|---|
| `latest handshake` 있음 | ✅ 터널 정상 |
| `latest handshake` **줄 자체가 없음** | ❌ 한 번도 연결된 적 없음 |
| 오래 전 (수 분 이상) | ⚠️ 끊긴 상태 |
| `transfer: 0 received` | 상대에게서 아무것도 못 받음 |

핸드셰이크는 트래픽이 있을 때 약 2분마다 갱신된다.
`PersistentKeepalive = 25`를 주면 트래픽이 없어도 25초마다 유지된다.

## 진단 순서

```bash
# 1. 데몬이 UDP 포트를 잡았는가  ← -u 필수! (04_ss.md 참고)
sudo ss -lunp | grep 51820

# 2. 패킷이 나가는가 / 들어오는가
sudo tcpdump -ni ens3 udp port 51820

# 3. 터널 내부는 흐르는가
sudo tcpdump -ni wg0
```

| 증상 | 확인 | 의미 |
|---|---|---|
| handshake 없음 | `ss -lunp \| grep 51820` | 데몬이 포트를 잡았는가 |
| ↳ | `tcpdump -ni ens3 udp port 51820` | 나가는가 / 들어오는가 |
| ↳ 나가지만 안 들어옴 | — | **보안 목록** 또는 상대 방화벽 |
| ↳ 아예 안 나감 | `wg show`의 `endpoint` | 주소·포트 오타 |
| handshake는 되는데 핑 실패 | `allowed ips` | **수신 필터에 걸려 폐기 중** |
| 간헐적 끊김 | `PersistentKeepalive` | NAT 세션 만료 |
| 키 불일치 | 양쪽 `wg show`의 public key | 상대 공개키를 잘못 넣음 |

## ⚠️ `AllowedIPs` — 가장 많이 틀리는 부분

`AllowedIPs`는 두 가지 역할을 **동시에** 한다.

1. **송신 라우팅** — 이 대역으로 가는 패킷을 이 피어에게 보낸다
2. **수신 필터** — 이 피어에게서 온 패킷 중 출발지가 이 대역이 아니면 **버린다**

2번이 함정이다. 파드 트래픽(`10.244.0.0/16`)을 터널에 그냥 태우려 하면
`AllowedIPs`에 없어서 **조용히 폐기된다. 로그도 안 남는다.**

→ 이것이 Phase 3에서 Calico를 **VXLAN Always**로 잡아야 하는 이유다.
캡슐화하면 바깥 헤더의 출발지가 `10.10.0.x`가 되어 필터를 통과한다.

자세한 내용은 [`docs/01-network-design.md`](../../../docs/01-network-design.md) 5-3절.

## 설정 변경 후

```bash
sudo systemctl restart wg-quick@wg0     # 설정 파일 수정 후
sudo wg syncconf wg0 <(wg-quick strip wg0)   # 무중단 반영
```

`wg-quick`은 설정 파일 권한이 느슨하면 경고를 낸다. 키 생성 시 `umask 077`을 먼저 걸 것.

## 검증 체크리스트

```bash
sudo wg show                      # 1. handshake 시각이 찍히는가
ping -c3 10.10.0.2                # 2. 터널 IP로 닿는가
ping -c20 10.10.0.2 | tail -2     # 3. 지연이 실용적인가 (mdev 확인)
nc -vz -w3 10.10.0.2 6443         # 4. TCP도 통하는가 (상대에 nc -l 6443 필요)
sudo systemctl is-enabled wg-quick@wg0   # 5. 재부팅 후에도 살아나는가
```

> 3번을 그냥 넘기지 말 것. etcd는 피어 지연에 민감하다.
> 단일 control plane에서는 문제없지만 Phase 4에서 HA를 구성할 때 영향이 있다. 지금 측정해 기록해 둔다.

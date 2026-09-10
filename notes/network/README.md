# 네트워크 노트

노드 간 통신 관련 기록.

| 디렉터리 | 내용 |
|---|---|
| [`concepts/`](concepts/) | 개념 정리 — 왜 이런 상황이 벌어졌는가 |
| [`diagnosis/`](diagnosis/) | 진단 명령 사용법 |
| [`reference/`](reference/) | 검토 중인 기술 자료 (채택 확정 아님) |

## 개념

| 문서 | 내용 |
|---|---|
| [`01_vcn-vpc.md`](concepts/01_vcn-vpc.md) | VCN/VPC란 무엇인가, CIDR 겹침이 왜 치명적인가 |
| [`02_node-addressing.md`](concepts/02_node-addressing.md) | **포트를 다 열어도 안 되는 이유.** Phase 0 판단의 근거 |

## 검토 자료

| 문서 | 상태 |
|---|---|
| [`wireguard.md`](reference/wireguard.md) | 🔍 검토 중 — 주소 문제 해결 후보 |

## 진단 원칙 — 아래에서 위로 좁힌다

물리 → IP 도달 → 포트 도달 → 패킷 확인 → 애플리케이션 순으로 본다.
위에서부터 보면 원인이 아래에 있을 때 헤맨다. 번호 순서가 곧 확인 순서다.

| 계층 | 확인하는 것 | 도구 |
|---|---|---|
| L3 | 그 **호스트**에 IP가 닿는가 | [`01_ping.md`](diagnosis/01_ping.md) |
| L4 | 그 **포트**가 열려 있는가 | [`02_nc.md`](diagnosis/02_nc.md) |
| — | 패킷이 실제로 오가는가 | [`03_tcpdump.md`](diagnosis/03_tcpdump.md) |
| — | 데몬이 포트를 잡고 있는가 | [`04_ss.md`](diagnosis/04_ss.md) |
| — | 터널 상태 | [`05_wireguard.md`](diagnosis/05_wireguard.md) |

기본 정보는 언제나 먼저 본다: `ip addr`, `ip route`.

---

## Phase 0 연결성 점검 절차

터미널 두 개를 띄운다 (`ssh k8s-1`, `ssh k8s-2`).

### 1단계 — 사설 IP (실패가 정상)

```bash
# k8s-1 에서
ping -c3 -W1 10.0.0.169
```

100% loss가 정상이다. 두 노드가 서로 다른 VCN에 있고 우연히 같은 `10.0.0.0/24`를 쓰기 때문.
배경은 [`docs/01-network-design.md`](../../docs/01-network-design.md) 1절.

### 2단계 — 공인 IP 기준선

```bash
# k8s-1 에서 (22번은 이미 열려 있음)
nc -vz -w3 198.51.100.22 22
```

`succeeded`가 나와야 한다. 이게 실패하면 보안 목록 이전에 더 근본적인 문제가 있다.

> ⚠️ **공인 IP에 `ping`을 때려 판단하지 말 것.** OCI 기본 보안 목록은 ICMP를 일부 타입만 허용한다.
> **TCP는 되는데 ping은 안 되는** 상태가 흔하다. 가장 잦은 초기 오판이다.

### 3단계 — UDP 51820 통과 여부 ⭐

UDP는 연결 개념이 없어서 `nc -vzu`가 **거짓 성공**을 낸다. 받는 쪽에서 직접 확인해야 한다.

```bash
# k8s-2 (먼저 실행, 대기 상태로 둠)
sudo tcpdump -ni ens3 udp port 51820

# k8s-1
echo hello | nc -u -w2 198.51.100.22 51820
```

| k8s-2의 tcpdump | 판정 |
|---|---|
| 패킷이 찍힘 | ✅ 보안 목록 통과 |
| 아무것도 안 찍힘 | ❌ 차단 중 — 규칙 미적용 또는 잘못된 서브넷에 적용 |

정상 출력:

```
IP 203.0.113.11.54321 > 10.0.0.169.51820: UDP, length 6
```

> 💡 **목적지가 사설 IP로 보인다.** OCI가 공인 IP를 인스턴스 앞단에서 1:1 NAT로 사설 IP에 매핑하기 때문이다.
> 노드 자신은 공인 IP를 인터페이스에 갖고 있지 않다 (`ip addr`로 보면 `ens3`에 `10.0.0.155`뿐).
> → `kubeadm init`의 `--apiserver-advertise-address`에 공인 IP를 주면 안 되는 이유가 여기 있다.

### 4단계 — 반대 방향

방화벽 규칙은 방향별로 따로 걸린다. 양쪽 다 확인한다.

```bash
# k8s-1 (대기)
sudo tcpdump -ni ens3 udp port 51820

# k8s-2
echo hello | nc -u -w2 203.0.113.11 51820
```

3·4단계가 양방향 모두 통과하면 오버레이 터널을 올릴 수 있는 상태다.
다만 터널 방식 채택은 아직 확정이 아니다 → [`reference/wireguard.md`](reference/wireguard.md) 검토 메모.

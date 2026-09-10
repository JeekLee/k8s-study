# 네트워크 진단 치트시트

> 노드 간 통신을 점검할 때의 절차와 명령. Phase 0에서 만들었지만 이후 모든 Phase에서 계속 쓴다.
> CKA Troubleshooting(배점 30%)의 절반은 결국 "패킷이 어디서 죽는가"다.

## 원칙 — 아래에서 위로 좁힌다

물리 → IP 도달 → 포트 도달 → 애플리케이션 순으로 확인한다.
위에서부터 보면 원인이 아래에 있을 때 헤맨다.

| 순서 | 확인 대상 | 도구 |
|---|---|---|
| 1 | 인터페이스·주소·라우팅 | `ip addr`, `ip route` |
| 2 | IP 도달성 | `ping` |
| 3 | 특정 포트 도달성 | `nc -vz` |
| 4 | 패킷이 실제로 오가는가 | `tcpdump` |
| 5 | 데몬이 포트를 잡고 있는가 | `ss -lntp` / `ss -lunp` |

---

## 연결성 점검 절차

터미널 두 개를 띄운다 (`ssh k8s-1`, `ssh k8s-2`).

### 1단계 — 사설 IP (실패가 정상)

```bash
# k8s-1 에서
ping -c3 -W1 10.0.0.169
```

100% loss가 정상이다. 두 노드가 서로 다른 VCN에 있고 우연히 같은 `10.0.0.0/24`를 쓰기 때문.
자세한 배경은 [`docs/01-network-design.md`](../docs/01-network-design.md) 1절.

### 2단계 — 공인 IP 기준선

```bash
# k8s-1 에서 (22번은 이미 열려 있음)
nc -vz 198.51.100.22 22
```

`succeeded`가 나와야 한다. 이게 실패하면 보안 목록 이전에 더 근본적인 문제가 있다.

> ⚠️ **공인 IP에 `ping`을 때려 판단하지 말 것.**
> OCI 기본 보안 목록은 ICMP를 일부 타입만 허용한다. **TCP는 되는데 ping은 안 되는** 상태가 흔하다.
> ping 실패를 "연결 안 됨"으로 오해하는 것이 가장 흔한 초기 실수다.

### 3단계 — UDP 51820 통과 여부 ⭐

UDP는 연결 개념이 없어서 `nc -vzu`가 **거짓 성공**을 낸다. 받는 쪽에서 직접 확인해야 한다.

```bash
# k8s-2 (먼저 실행, 대기)
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
> 노드 자신은 공인 IP를 인터페이스에 갖고 있지 않다 (`ip addr`로 확인하면 `ens3`에 `10.0.0.155`뿐).
> → `kubeadm init`의 `--apiserver-advertise-address`에 공인 IP를 주면 안 되는 이유가 여기 있다.

### 4단계 — 반대 방향

방화벽 규칙은 방향별로 따로 걸린다. 양쪽 다 확인한다.

```bash
# k8s-1 (대기)
sudo tcpdump -ni ens3 udp port 51820

# k8s-2
echo hello | nc -u -w2 203.0.113.11 51820
```

---

## 명령 옵션 정리

### `ping`

`-c`가 없으면 Linux에서는 **Ctrl+C까지 무한히** 보낸다. (Windows만 기본 4개)

| 옵션 | 뜻 | 예시 |
|---|---|---|
| `-c` | count — 보낼 패킷 개수 | `-c3` = 3개 |
| `-W` | 응답 **대기 시간**(초) | `-W1` = 1초 기다리고 포기 |
| `-i` | 보내는 **간격**(초) | `-i0.2` = 0.2초마다 |
| `-s` | 패킷 **크기**(바이트) | `-s1400` = MTU 문제 확인 |

`-c3`과 `-c 3`은 동일하다. `-c`(개수)와 `-W`(대기)를 특히 헷갈리기 쉽다.

```bash
ping -c3 -W1 10.0.0.169        # 빠른 확인 — 안 되면 즉시 포기
ping -c20 10.10.0.2 | tail -2  # 품질 측정 — 손실률과 RTT 요약만
```

`tail -2`는 마지막 요약 두 줄(손실률, RTT min/avg/max/mdev)만 보겠다는 뜻.

### `nc` (netcat)

| 옵션 | 뜻 |
|---|---|
| `-v` | 결과를 말로 출력 |
| `-z` | 데이터 안 보내고 포트만 확인 (스캔 모드) |
| `-u` | UDP 사용 |
| `-l` | 리스너로 동작 |
| `-w` | 타임아웃(초) |

```bash
nc -vz 198.51.100.22 22          # TCP 포트 확인
nc -u -l 51820                   # UDP 리스너
echo hi | nc -u -w2 <IP> 51820   # UDP 한 방 쏘기
```

### `tcpdump`

| 옵션 | 뜻 |
|---|---|
| `-n` | 이름 해석 안 함 (DNS 조회로 멈추는 것 방지) |
| `-i` | 인터페이스 지정 |
| `-e` | 이더넷 헤더까지 표시 |
| `-A` | 페이로드를 ASCII로 |

```bash
sudo tcpdump -ni ens3 udp port 51820     # 특정 포트
sudo tcpdump -ni any icmp                # 모든 인터페이스의 ICMP
sudo tcpdump -ni wg0                     # 터널 내부만
```

`-n`은 거의 항상 붙인다. 없으면 DNS 역조회 때문에 출력이 느려지고, DNS 자체가 문제일 때 멈춰버린다.

### `ss`

| 명령 | 뜻 |
|---|---|
| `ss -lntp` | TCP 리스닝 포트 + 프로세스 |
| `ss -lunp` | **UDP** 리스닝 포트 + 프로세스 |
| `ss -tnp` | 연결된 TCP 세션 |

`-l`은 listening, `-n`은 숫자로, `-p`는 프로세스, `-t`/`-u`는 TCP/UDP.
`netstat`은 deprecated이므로 `ss`를 쓴다.

---

## WireGuard 전용

```bash
sudo wg show                      # handshake 시각이 찍혀야 정상
sudo wg show wg0 latest-handshakes
sudo systemctl status wg-quick@wg0
ip addr show wg0
```

| 증상 | 확인할 것 | 의미 |
|---|---|---|
| handshake 없음 | `ss -lunp \| grep 51820` | 데몬이 포트를 잡았는가 |
| ↳ | `tcpdump -ni ens3 udp port 51820` | 나가는가 / 들어오는가 |
| ↳ 나가지만 안 들어옴 | — | 보안 목록 또는 상대 방화벽 |
| handshake는 되는데 핑 실패 | `AllowedIPs` | 수신 필터에 걸려 폐기 중 |
| 간헐적 끊김 | `PersistentKeepalive` | NAT 세션 만료 |

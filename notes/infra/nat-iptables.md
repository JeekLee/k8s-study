# NAT과 iptables

Stage 1의 인터넷 접속 설정에서 시작해, Stage 8의 라우팅과 Stage 4·10의
kube-proxy 진단까지 계속 쓰이는 내용.

## NAT의 두 축

주소를 바꾸는 방향에 따라 나뉜다.

### 출발지를 바꾼다 (SNAT 계열)

| 타겟 | 하는 일 | 언제 |
|---|---|---|
| **`MASQUERADE`** | 출발지를 **나가는 인터페이스의 현재 IP**로 (자동) | IP가 바뀔 수 있을 때 |
| **`SNAT`** | 출발지를 **지정한 IP**로 고정 | IP가 고정일 때 |

```bash
# 이 프로젝트에서 쓰는 것 — ens3의 현재 IP를 자동으로
iptables -t nat -A POSTROUTING -s 192.168.122.0/24 -o ens3 -j MASQUERADE

# 같은 일을 SNAT으로
iptables -t nat -A POSTROUTING -s 192.168.122.0/24 -o ens3 -j SNAT --to-source 10.0.0.169
```

**차이 두 가지:**

- `MASQUERADE`는 패킷마다 인터페이스 IP를 조회한다. 아주 약간 느리지만
  **주소가 바뀌어도 알아서 따라간다**
- `MASQUERADE`는 **인터페이스가 다운되면 관련 conntrack 항목을 지운다.**
  재연결 시 옛 연결이 엉키지 않는다

`ens3`가 DHCP(`valid_lft` 약 13시간)이므로 `MASQUERADE`가 맞다.

### 목적지를 바꾼다 (DNAT 계열)

| 타겟 | 하는 일 |
|---|---|
| **`DNAT`** | 목적지를 다른 주소·포트로 — **포트 포워딩** |
| **`REDIRECT`** | 목적지를 로컬 호스트로 (DNAT의 특수형, 투명 프록시용) |
| **`NETMAP`** | 대역 전체를 1:1로 통째 매핑 |

```bash
# 호스트의 8080 → VM의 80
iptables -t nat -A PREROUTING -p tcp --dport 8080 -j DNAT --to-destination 192.168.122.11:80
```

---

## ⭐ 체인 — 왜 POSTROUTING이었나

| 체인 | 시점 | 주로 쓰는 것 |
|---|---|---|
| `PREROUTING` | 들어오자마자, **라우팅 결정 전** | DNAT |
| `POSTROUTING` | 나가기 직전, **라우팅 결정 후** | SNAT / MASQUERADE |
| `OUTPUT` | 로컬에서 만든 패킷 | DNAT |

이유가 명확하다.

- **목적지**를 바꾸려면 **라우팅 결정 전**에 해야 한다.
  안 그러면 옛 목적지 기준으로 경로가 정해져 엉뚱한 곳으로 간다
- **출발지**는 경로 결정에 영향이 없으므로 **마지막**에 바꾼다

그래서 `MASQUERADE`는 항상 `POSTROUTING`, `DNAT`은 항상 `PREROUTING`이다.
외울 필요 없이 이 이유만 알면 된다.

### 포워딩되는 패킷의 전체 경로

```
들어옴
 └ raw PREROUTING          conntrack 이전 처리
    └ conntrack            연결 추적 시작
       └ mangle PREROUTING 헤더 수정
          └ nat PREROUTING ← DNAT
             └ 라우팅 결정
                └ mangle FORWARD
                   └ filter FORWARD   ← 통과 허용 여부
                      └ mangle POSTROUTING
                         └ nat POSTROUTING ← SNAT / MASQUERADE
                            └ 나감
```

Stage 8에서 `FORWARD` 규칙을 넣는 것도 이 그림의 `filter FORWARD` 자리다.

## 테이블 종류

| 테이블 | 용도 |
|---|---|
| `filter` | 통과·차단 (`ACCEPT`, `DROP`, `REJECT`). **`-t`를 생략하면 이것** |
| `nat` | 주소 변환 |
| `mangle` | 헤더 수정 (TTL, TOS, MARK) |
| `raw` | conntrack 이전 처리 (`NOTRACK`) |

```bash
iptables -L -n -v            # filter 테이블 (기본)
iptables -t nat -L -n -v     # nat 테이블
```

---

## 이 프로젝트에서 쓰는 규칙

### Stage 1 — VM 인터넷 접속

```bash
# 남의 패킷을 넘겨주도록 허용
echo 'net.ipv4.ip_forward=1' | sudo tee /etc/sysctl.d/99-router.conf
sudo sysctl --system

# 인터넷(ens3)으로 나갈 때만 출발지 변환
sudo iptables -t nat -A POSTROUTING -s 192.168.122.0/24 -o ens3 -j MASQUERADE
```

### Stage 8 — 크로스 호스트 라우팅

```bash
# VM 대역과 터널 사이의 통과 허용
sudo iptables -A FORWARD -i virbr1 -o wg0 -j ACCEPT
sudo iptables -A FORWARD -i wg0 -o virbr1 -j ACCEPT
```

> **`wg0`로 나가는 트래픽에는 MASQUERADE를 걸지 않는다.**
> 출발지가 바뀌면 쿠버네티스 노드 주소와 어긋난다.
> → [`../network/concepts/02_node-addressing.md`](../network/concepts/02_node-addressing.md)

### Stage 2 — VM이 호스트에게 말을 걸게 (INPUT)

**NAT·포워딩과는 다른 문제다. 체인이 다르다.**

| 트래픽 | 체인 | 무엇이 필요한가 |
|---|---|---|
| VM → 인터넷 (호스트를 **통과**) | `FORWARD` | `ip_forward` + MASQUERADE |
| VM → **호스트 자신** | **`INPUT`** | INPUT 에 허용 규칙 |

호스트의 `INPUT` 마지막에 `REJECT --reject-with icmp-host-prohibited`가 있으면
VM에서 호스트의 서비스(HAProxy 등)에 접속할 수 없다.

```bash
# VM 에서
nc -vz -w3 192.168.122.1 6443
# failed: No route to host          ← 라우팅 문제가 아니라 REJECT 당한 것
```

```bash
# 호스트에서 — REJECT 보다 앞에 삽입
sudo iptables -I INPUT 2 -i virbr1 -p tcp --dport 6443 -j ACCEPT
sudo netfilter-persistent save
```

> **`-I`(삽입)와 `-A`(추가)를 구분할 것.**
> `-A`는 맨 뒤에 붙으므로 REJECT 뒤가 되어 아무 효과가 없다.
> 규칙은 **위에서부터 비교하다 처음 맞는 것에서 멈춘다.**

#### 왜 VM이 호스트에 말을 거는가

`--control-plane-endpoint`를 호스트의 HAProxy 주소로 잡으면,
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

이상해 보이지만 단일 엔드포인트의 목적이 그것이다 —
CP를 3대로 늘려도 각 노드는 설정을 바꾸지 않는다.

VM → 호스트로 상시 오가는 것: kubelet, kube-proxy, scheduler,
controller-manager, kubectl, 그리고 워커의 `kubeadm join`.
반대 방향(호스트 → VM)은 프록시와 헬스체크뿐이다.

> 그래서 **HAProxy가 죽으면 apiserver가 멀쩡해도 클러스터가 마비된다.**
> apiserver ↔ etcd 는 같은 VM 안에서 `127.0.0.1` 로 직접 통신하므로 예외다.

#### 오해하기 쉬운 신호

| 메시지 | 뜻 |
|---|---|
| `No route to host` | `icmp-host-prohibited` 로 **거부**당함 (방화벽 REJECT) |
| `Network is unreachable` | 진짜 라우팅이 없음 |
| `Connection refused` | 닿았지만 그 포트에 리스너가 없음 |
| 타임아웃 | DROP 당했거나 경로가 없음 |

### Stage 4 — 맥에서 서비스 열어보기

VM은 `192.168.122.x`라 맥에서 직접 안 닿는다. 두 가지 방법이 있다.

```bash
# 방법 1 — SSH 터널 (간단, 임시). 실습 중에는 이쪽이 편하다
ssh -L 8080:192.168.122.11:30080 k8s-2
# 맥 브라우저에서 localhost:8080

# 방법 2 — 호스트에 DNAT (상시). 클라우드 보안 목록도 함께 열어야 한다
sudo iptables -t nat -A PREROUTING -p tcp --dport 8080 \
  -j DNAT --to-destination 192.168.122.11:30080
```

---

## 규칙 저장 — 안 하면 재부팅 때 사라진다

**iptables 규칙은 메모리에만 있다.**

```bash
sudo apt-get install -y iptables-persistent   # 설치 중 "저장할까요?" → Yes
sudo netfilter-persistent save                # 현재 규칙을 파일로
sudo netfilter-persistent reload
```

저장 위치는 `/etc/iptables/rules.v4`, `rules.v6`.

---

## iptables vs nftables

### iptables (1998~)

- **도구가 4개로 쪼개져 있다** — `iptables`(IPv4), `ip6tables`(IPv6), `arptables`, `ebtables`.
  각각 별개 커널 모듈이라 같은 일을 네 번 해야 한다
- 테이블과 체인이 **커널에 하드코딩**되어 있다
- 규칙을 하나 추가할 때 **전체 룰셋을 읽어와 수정하고 다시 쓴다.**
  규칙이 많아지면 느려진다
- 규칙을 **위에서부터 하나씩 비교**한다. 수천 개가 되면 성능이 떨어진다

### nftables (2014, kernel 3.13~)

- **도구가 `nft` 하나**로 IPv4·IPv6·ARP·bridge를 전부 다룬다
- 테이블과 체인을 **사용자가 직접 정의**한다. 하드코딩이 없다
- **원자적 교체** — 룰셋 전체를 한 번에 바꿀 수 있다. 중간 상태가 없다
- **셋(set)과 맵(map)** 을 지원한다. 해시 조회라 IP 수천 개를 매칭해도 빠르다
- 규칙 하나에서 여러 동작을 할 수 있다

문법 비교:

```bash
# iptables
iptables -t nat -A POSTROUTING -s 192.168.122.0/24 -o ens3 -j MASQUERADE

# nftables
nft add rule ip nat postrouting ip saddr 192.168.122.0/24 oifname "ens3" masquerade
```

### 지금 우리가 쓰는 것은 사실 nftables다

Ubuntu는 오래전부터 **`iptables` 명령이 nftables 백엔드에 쓰는** 구조다(`iptables-nft`).
우리가 치는 명령은 호환 계층이고, 실제 규칙은 nftables에 들어간다.

```bash
iptables --version
# iptables v1.8.x (nf_tables)   ← nftables 백엔드
# iptables v1.8.x (legacy)      ← 옛 백엔드

sudo nft list ruleset | head -30   # 실제로 저장된 형태
```

### ⚠️ 섞어 쓰면 규칙이 안 보인다

`iptables-legacy`와 `iptables-nft`는 **서로 다른 저장소**를 본다.
한쪽으로 넣은 규칙이 다른 쪽 `-L`에는 안 나온다.

```bash
sudo update-alternatives --display iptables   # 어느 쪽을 쓰는지
sudo iptables-legacy -L -n                    # 옛 백엔드에 남은 것 확인
```

"분명히 규칙을 넣었는데 안 보인다"면 이걸 의심한다.

### 어느 쪽을 배워야 하나

**`iptables` 문법을 계속 쓰면 된다.** CKA 문서와 대부분의 자료가 `iptables` 기준이고
호환 계층이 잘 동작한다. `nft`는 규칙이 실제로 어떻게 저장돼 있는지 확인할 때만 쓴다.

---

## kube-proxy와의 연결

**Service가 동작하는 원리가 정확히 이것이다.** Service를 만들면 kube-proxy가
각 노드에 iptables 규칙을 잔뜩 쓴다.

```bash
# Stage 3 이후 노드에서
sudo iptables -t nat -L KUBE-SERVICES -n | head
sudo iptables -t nat -L -n | grep KUBE | head -20
```

ClusterIP로 온 패킷을 **DNAT으로 실제 파드 IP에 넘기는** 규칙들이다.
파드가 여러 개면 확률 기반으로 분산한다(`statistic` 모듈).

| kube-proxy 모드 | 방식 |
|---|---|
| `iptables` (기본) | 위와 같은 규칙. 서비스가 많아지면 규칙이 수천 개가 된다 |
| `ipvs` | 커널 로드밸런서 사용. 대규모에서 빠르다 |
| `nftables` | 최근 버전에 추가. 사용 중인 버전의 문서를 확인할 것 |

> "서비스에 접속이 안 된다"를 진단할 때 이 규칙들을 읽게 된다.
> Services & Networking 영역(CKA 20%)에서 그대로 쓰인다.

---

## 진단

```bash
# 규칙 보기 — -n(이름 해석 안 함) -v(패킷 카운터 포함) 는 거의 항상 붙인다
sudo iptables -t nat -L POSTROUTING -n -v
sudo iptables -L FORWARD -n -v

# 규칙 번호와 함께
sudo iptables -t nat -L POSTROUTING -n --line-numbers

# 특정 규칙 삭제
sudo iptables -t nat -D POSTROUTING 1

# 연결 추적 상태
sudo conntrack -L | head
sudo conntrack -L -s 192.168.122.11

# 포워딩 설정
sysctl net.ipv4.ip_forward
```

**패킷 카운터가 핵심 단서다.** 규칙은 있는데 카운터가 0이면
그 규칙에 트래픽이 도달하지 않는 것이다 — 조건(`-s`, `-o`, `-i`)이 안 맞거나
앞의 규칙에서 이미 처리된 것이다.

## 관련

- Stage 1 절차 → [`docs/stages/stage-01-virtualization.md`](../../docs/stages/stage-01-virtualization.md)
- 왜 wg0에는 NAT을 안 하나 → [`../network/concepts/02_node-addressing.md`](../network/concepts/02_node-addressing.md)
- 인터페이스 구분 → [`../network/concepts/03_interfaces.md`](../network/concepts/03_interfaces.md)

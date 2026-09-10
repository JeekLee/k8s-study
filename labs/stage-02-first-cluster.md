# Stage 2 — 첫 클러스터 (단일 노드)

| | |
|---|---|
| 일자 | 2026-09-10 |
| 결과 | 🔄 진행 중 — 1절(HAProxy)까지 완료 |
| 대상 | k8s-2 호스트 + VM `k2-cp1` |

> 절차: [`docs/stages/stage-02-first-cluster.md`](../docs/stages/stage-02-first-cluster.md)
> 참고: [`notes/infra/haproxy.md`](../notes/infra/haproxy.md) · [`notes/infra/nat-iptables.md`](../notes/infra/nat-iptables.md)

## 완료 기준

- [ ] `kubectl get nodes`에 `k2-cp1`이 `Ready`로 나온다
- [ ] `kubectl run nginx --image=nginx`로 띄운 파드가 `Running`
- [ ] `kubectl logs`가 동작한다
- [x] HAProxy를 거쳐 apiserver에 닿는다 — *리스너와 경로까지 확인. 백엔드는 apiserver 대기 중*
- [ ] 스냅샷으로 되돌린 뒤에도 클러스터가 정상 동작한다

---

## 수행 기록

### 1. HAProxy 설치와 설정

호스트(k8s-2)에 설치하고 `/etc/haproxy/haproxy.cfg` 끝에 frontend·backend·stats 블록을 추가했다.

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

listen stats
    bind 192.168.122.1:8404
    mode http
    stats enable
    stats uri /stats
    stats refresh 10s
```

```bash
sudo haproxy -c -f /etc/haproxy/haproxy.cfg
# (출력 없음 = 문법 정상)

sudo systemctl restart haproxy
```

재시작 후 로그:

```
[NOTICE]   Loading success.
[WARNING]  Server k8s-cp/k2-cp1 is DOWN, reason: Layer4 connection problem
[ALERT]    backend 'k8s-cp' has no server available!
```

**이 경고가 정상 신호다.** apiserver가 아직 없으니 헬스체크가 실패하는 것이고,
오히려 HAProxy가 백엔드를 제대로 인식했다는 뜻이다.

```bash
sudo ss -lntp | grep -E '6443|8404'
# LISTEN 0 4096 192.168.122.1:6443 ... users:(("haproxy",pid=6383,fd=5))
# LISTEN 0 4096 192.168.122.1:8404 ... users:(("haproxy",pid=6383,fd=6))

curl -s 'http://192.168.122.1:8404/stats;csv' | awk -F, '/k8s-cp/{print "  "$1"/"$2": "$18}'
#   k8s-cp/k2-cp1: DOWN
#   k8s-cp/BACKEND: DOWN
```

### 2. 방화벽 — VM에서 HAProxy로 가는 길 열기

호스트에서는 잘 보이는데 VM에서 접속이 안 됐다.

```bash
# VM(k2-cp1) 에서
nc -vz -w3 192.168.122.1 6443
# nc: connect to 192.168.122.1 port 6443 (tcp) failed: No route to host
```

```bash
sudo iptables -I INPUT 2 -i virbr1 -p tcp --dport 6443 -j ACCEPT
sudo netfilter-persistent save
```

`-I INPUT 2`로 **REJECT보다 앞에** 넣는 것이 핵심. `-A`는 맨 뒤라 소용없다.

---

## 막힌 것

### HAProxy가 설정 없이 떠 있었다

**증상** — `systemctl status`는 `Active: running`, `Status: "Ready."`인데
`ss -lntp | grep 6443`이 아무것도 안 나왔다.

**틀린 가설** — 설정 문법 오류를 의심했다. `haproxy -c -f`를 돌렸지만 정상이었다.

**확인한 것** — 시각을 비교하니 답이 나왔다.

```
서비스 시작 : 2026-09-10 07:41:21
설정 파일 수정: 2026-09-10 07:44:36     ← 3분 뒤
```

**원인** — `apt install haproxy`가 **설치 직후 서비스를 자동 시작**했다.
그때는 우리 블록이 없는 기본 설정이라 frontend가 없었고, 그래서
"정상 실행 중이지만 아무것도 LISTEN하지 않는" 상태가 됐다.

**해결** — `sudo systemctl restart haproxy`

**배운 것**
- **`Active: running`은 "설정대로 동작 중"을 뜻하지 않는다.**
  프로세스가 살아 있다는 것뿐이다. 실제로 원하는 포트를 잡았는지는 `ss`로 봐야 한다.
- 데비안 계열은 패키지 설치 시 서비스를 자동 시작한다.
  **설정을 고친 뒤에는 반드시 `restart` 또는 `reload`.**
- 클러스터가 돌기 시작하면 기존 연결을 유지하는 `reload`를 쓰는 편이 낫다.

### `No route to host` — 라우팅 문제가 아니었다

**증상** — VM에서 호스트의 HAProxy(`192.168.122.1:6443`)로 접속이 안 됨.

**틀린 가설** — 라우팅이 없나 의심했다. 그런데 VM은 `192.168.122.11/24`이고
호스트는 같은 서브넷의 `192.168.122.1`이라 **직접 연결**이다. 라우팅 문제일 수 없었다.

**확인한 것** — 호스트의 INPUT 체인:

```
num   pkts  target       prot  in   source      destination
1     ..... LIBVIRT_INP  all   *                              ← DHCP/DNS 만 허용
2     ..... ACCEPT       all   *    state RELATED,ESTABLISHED
3     ..... ACCEPT       icmp  *
4     ..... ACCEPT       all   lo
5     ..... ACCEPT       tcp   *    state NEW tcp dpt:22
6        44 REJECT       all   *    reject-with icmp-host-prohibited
```

**6번에서 44개 패킷이 이미 거부돼 있었다.**

**원인** — `icmp-host-prohibited`로 거부하면 클라이언트에는 `No route to host`로 보인다.
방화벽 신호를 라우팅 신호로 착각하기 딱 좋다.

**Stage 1의 NAT 설정과 무관한 이유** — 체인이 다르다.

| 트래픽 | 체인 | Stage 1에서 |
|---|---|---|
| VM → 인터넷 (호스트를 **통과**) | `FORWARD` | ✅ 열었다 |
| VM → **호스트 자신** | **`INPUT`** | ❌ 손대지 않았다 |

`ip_forward`와 MASQUERADE는 **지나가는** 트래픽을 다룬 것이었다.

**해결** — `sudo iptables -I INPUT 2 -i virbr1 -p tcp --dport 6443 -j ACCEPT`

**배운 것**
- 오류 메시지 네 가지를 구분할 것.

  | 메시지 | 뜻 |
  |---|---|
  | `No route to host` | `icmp-host-prohibited`로 **거부**됨 (방화벽 REJECT) |
  | `Network is unreachable` | 진짜 라우팅이 없음 |
  | `Connection refused` | 닿았지만 그 포트에 리스너 없음 |
  | 타임아웃 | DROP 당했거나 경로 없음 |

- **같은 서브넷인데 "route" 오류가 나면 방화벽을 의심한다.**
  라우팅이 필요 없는 거리이기 때문이다.
- `-I`(삽입)와 `-A`(추가)의 차이가 결정적이다. 규칙은 위에서부터 비교하다
  처음 맞는 것에서 멈추므로, REJECT 뒤에 붙으면 아무 효과가 없다.

### `sudo systemctl status`에서 터미널 경고

```
WARNING: terminal is not fully functional
```

terminfo를 사용자 단위로만 설치해 `sudo`(HOME=/root)에서 못 찾은 것.
→ [`incidents/2026-09-10-terminfo-xterm-ghostty.md`](incidents/2026-09-10-terminfo-xterm-ghostty.md)

`systemctl status`는 읽기 전용이라 **애초에 `sudo`가 필요 없었다.**

---

## 이해한 것 — VM이 호스트에 말을 거는 이유

처음에는 "HAProxy가 VM에 말을 거는 것"만 떠올랐는데, 실제로는 **반대 방향이 훨씬 많다.**

`--control-plane-endpoint`를 HAProxy 주소로 잡으면 kubeadm이 만드는
**모든 kubeconfig의 `server:`가 그 주소**가 된다.

```
kubelet.conf · scheduler.conf · controller-manager.conf · admin.conf
  → server: https://192.168.122.1:6443
```

그래서 `k2-cp1`의 kubelet이 **같은 VM 안의 apiserver에 접속할 때도
호스트를 한 바퀴 돌아간다.**

```
[k2-cp1]  kubelet ──► [호스트] HAProxy :6443 ──► [k2-cp1] apiserver :6443
```

단일 엔드포인트의 목적이 그것이다 — Stage 5에서 CP를 3대로 늘려도
각 노드는 설정을 하나도 바꾸지 않는다.

VM → 호스트로 상시 오가는 것: kubelet, kube-proxy, scheduler,
controller-manager, kubectl, 워커의 `kubeadm join`. **거의 전부다.**
(apiserver ↔ etcd 는 같은 VM 안에서 `127.0.0.1`로 통신하므로 예외.)

> 그래서 **HAProxy가 죽으면 apiserver가 멀쩡해도 클러스터가 마비된다.**
> `notes/infra/haproxy.md`의 "HAProxy 자체가 단일 장애점"이 실제로 뜻하는 바다.

---

## 다음

- [ ] 2절 — VM 준비 (커널 모듈, sysctl)
- [ ] 3절 — containerd + `SystemdCgroup = true`
- [ ] 4절 — kubeadm/kubelet/kubectl 설치 + `apt-mark hold`
- [ ] 5절 — `kubeadm init`
- [ ] 7절 — Calico (MTU 1370, interface `enp1s0`)

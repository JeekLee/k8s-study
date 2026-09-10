# Stage 2 — 첫 클러스터 (단일 노드)

| | |
|---|---|
| 일자 | 2026-09-10 |
| 결과 | 🔄 진행 중 — `kubeadm init` 성공, CNI 대기 |
| 대상 | k8s-2 호스트 + VM `k2-cp1` |

> 절차: [`docs/stages/stage-02-first-cluster.md`](../docs/stages/stage-02-first-cluster.md)
> 참고: [`notes/infra/haproxy.md`](../notes/infra/haproxy.md) · [`notes/infra/nat-iptables.md`](../notes/infra/nat-iptables.md)

## 완료 기준

- [ ] `kubectl get nodes`에 `k2-cp1`이 `Ready`로 나온다 — *`kubeadm init` 완료, kubeconfig·CNI 남음*
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

### 3. VM 준비 — 커널 모듈과 sysctl

```bash
free -h | grep Swap
# Swap:  0B  0B  0B                    ← cloud image 라 swap 없음

printf 'overlay\nbr_netfilter\n' | sudo tee /etc/modules-load.d/k8s.conf
sudo modprobe overlay
sudo modprobe br_netfilter

lsmod | grep -E 'overlay|br_netfilter'
# br_netfilter   32768  0
# bridge        425984  1 br_netfilter     ← br_netfilter 가 bridge 를 끌고 온다
# overlay       212992  0
```

```bash
cat <<'SYSCTL' | sudo tee /etc/sysctl.d/k8s.conf
net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
SYSCTL

sudo sysctl --system
# ...
# * Applying /etc/sysctl.d/k8s.conf ...
# net.bridge.bridge-nf-call-iptables = 1
# net.bridge.bridge-nf-call-ip6tables = 1
# net.ipv4.ip_forward = 1
```

### 4. containerd

```bash
sudo apt-get install -y containerd
# containerd 2.2.1-0ubuntu1~24.04.3
# runc 1.3.4-0ubuntu1~24.04.1            ← 의존성으로 함께 설치된다

containerd --version
# containerd github.com/containerd/containerd/v2 2.2.1
```

**Ubuntu 24.04인데 containerd 2.x다.** 백포트되어 있다.

```bash
containerd config default | sudo tee /etc/containerd/config.toml >/dev/null
head -3 /etc/containerd/config.toml
# version = 3                     ← 2.x 는 스키마 3. 옛 예제를 붙이면 안 되는 이유
# root = '/var/lib/containerd'
# state = '/run/containerd'

sudo sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' /etc/containerd/config.toml
grep SystemdCgroup /etc/containerd/config.toml
#             SystemdCgroup = true

sudo systemctl restart containerd
```

```bash
sudo ctr version
# Client: 2.2.1 / Server: 2.2.1

ls -l /run/containerd/containerd.sock
# srw-rw---- 1 root root 0 Sep 10 08:03
```

### 5. kubeadm · kubelet · kubectl

```bash
curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.35/deb/Release.key \
  | sudo gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg

echo 'deb [signed-by=...] https://pkgs.k8s.io/core:/stable:/v1.35/deb/ /' \
  | sudo tee /etc/apt/sources.list.d/kubernetes.list

sudo apt-get update
# Get:1 https://prod-cdn.packages.k8s.io/.../v1.35/deb InRelease   ← 리다이렉트된 실제 CDN

sudo apt-get install -y kubelet kubeadm kubectl etcd-client
sudo apt-mark hold kubelet kubeadm kubectl
```

설치된 버전:

```
kubeadm  v1.35.8
kubelet  v1.35.8
kubectl  v1.35.8  (Kustomize v5.7.1 포함)
kubernetes-cni  1.8.0
etcd-client     3.4.30  (Ubuntu repo)
```

`apt-mark showhold`로 셋 다 고정 확인.

### 6. `kubeadm init` ✅

```bash
sudo kubeadm init phase preflight --dry-run
# I0910 version.go:260] remote version is much newer: v1.37.0; falling back to: stable-1.35
# [preflight] Running pre-flight checks
# [preflight] Would pull the required images
```

경고 없이 통과.

```bash
sudo kubeadm init \
  --control-plane-endpoint=192.168.122.1:6443 \
  --apiserver-advertise-address=192.168.122.11 \
  --pod-network-cidr=10.244.0.0/16 \
  --service-cidr=10.96.0.0/12 \
  --upload-certs \
  --kubernetes-version=v1.35.0
```

**성공.** 눈여겨본 부분:

```
[certs] apiserver serving cert is signed for DNS names [k2-cp1 kubernetes ...]
        and IPs [10.96.0.1 192.168.122.11 192.168.122.1]
```

**인증서 SAN에 `.11`(자기 자신)과 `.1`(HAProxy)이 둘 다 들어갔다.**
`--control-plane-endpoint`를 준 효과다. 나중에 바꾸면 이 인증서를 다시 발급해야 한다.

```
[kubeconfig] Writing "admin.conf" / "super-admin.conf" / "kubelet.conf"
             "controller-manager.conf" / "scheduler.conf"
```

kubeconfig가 다섯 개 생성됐다. 이들의 `server:`가 전부 `192.168.122.1:6443`이라
**VM에서 호스트로 나가는 트래픽**이 생기는 것이다 (아래 「이해한 것」 참고).

```
[control-plane-check] Checking kube-apiserver at https://192.168.122.11:6443/livez
[control-plane-check] kube-apiserver is healthy after 1.001188472s
```

흥미로운 점 — **kubeadm 자신의 헬스체크는 엔드포인트가 아니라 로컬 주소(`.11`)를 쓴다.**
그래서 HAProxy가 없어도 `init` 자체는 진행된다.

```
[mark-control-plane] taints [node-role.kubernetes.io/control-plane:NoSchedule]
[addons] Applied essential addon: CoreDNS
[addons] Applied essential addon: kube-proxy
```

### `kubeadm join` 명령 (형태만 기록)

> ⚠️ 토큰과 certificate-key는 **클러스터 가입 자격증명**이다. 실제 값은 적지 않는다.
> 토큰은 24시간, 업로드된 인증서는 2시간 뒤 만료된다.

**control plane 추가용** (Stage 5):

```bash
kubeadm join 192.168.122.1:6443 --token <토큰> \
  --discovery-token-ca-cert-hash sha256:<해시> \
  --control-plane --certificate-key <인증서키>
```

**워커 추가용** (Stage 3):

```bash
kubeadm join 192.168.122.1:6443 --token <토큰> \
  --discovery-token-ca-cert-hash sha256:<해시>
```

만료되면 재발급한다:

```bash
kubeadm token create --print-join-command          # 워커용
kubeadm init phase upload-certs --upload-certs     # CP 용 certificate-key 재생성
```

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

### 여러 줄 붙여넣기가 중간에 먹혔다

**증상** — containerd 설정을 만들려는데 계속 실패했다.

```
ee: command not found
head: cannot open '/etc/containerd/config.toml' ... No such file or directory
sed: can't read /etc/containerd/config.toml: No such file or directory
sudo: ctr: command not found
```

**원인** — 문서의 여러 줄 블록을 한 번에 붙여넣었는데
**일부 줄이 프롬프트와 뒤섞여 잘렸다.**

```
sudo apt-get update
sudo apt-get install -y containerd     ← 이 줄이 실행되지 않았다
```

`apt-get update`만 돌고 설치는 건너뛴 채 다음 단계로 넘어갔다.
`containerd config default | sudo tee ...`도 `tee`가 잘려 `ee`로 들어갔다.

**해결** — `containerd`를 실제로 설치한 뒤 순서대로 다시 실행.

**배운 것**
- **여러 줄을 한 번에 붙여넣지 말 것.** 특히 주석(`#`)이 섞인 블록.
  터미널이 입력을 처리하는 속도와 화면 갱신이 어긋나면 줄이 유실된다.
- 각 단계 뒤에 **확인 명령**을 넣는 이유가 이것이다.
  `containerd --version`을 먼저 쳤으면 바로 알았을 것이다.
- `command not found`가 났는데 그 명령을 친 기억이 없으면 **붙여넣기 사고**를 의심한다.

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

## 관찰한 것

### 설치 버전과 `--kubernetes-version`이 다르다

| | 버전 |
|---|---|
| kubeadm · kubelet · kubectl | **1.35.8** |
| `--kubernetes-version`으로 지정 | **v1.35.0** |

control plane 컴포넌트만 1.35.0으로 뜬 셈이다.
같은 마이너 버전이라 스큐 정책 위반은 아니고 동작에도 문제가 없지만,
**맞춰두는 편이 깔끔하다.** `--kubernetes-version`을 생략하면
kubeadm 자신의 버전(1.35.8)을 쓴다.

→ 문서를 그렇게 고쳤다.

### 저장소에는 v1.37이 이미 있다

```
remote version is much newer: v1.37.0; falling back to: stable-1.35
```

우리가 `v1.35` 저장소로 고정했기 때문에 나오는 안내다.
**CKA 시험이 v1.35 기준이므로 의도한 것이다.**

### `super-admin.conf`

kubeadm이 `admin.conf` 외에 `super-admin.conf`도 만든다.
`admin.conf`의 권한을 낮추고, 비상용 최고 권한을 별도 파일로 분리한 것이다.
평소에는 `admin.conf`를 쓴다.

### `etcd-client`가 3.4인데 클러스터 etcd는 더 높다

Ubuntu 저장소의 `etcd-client`는 3.4.30이다.
Stage 5에서 스냅샷 백업·복구를 할 때 **버전이 맞는지 확인이 필요하다.**
`kubectl -n kube-system get pod etcd-k2-cp1 -o yaml | grep image`로 실제 버전을 볼 것.

---

## 다음

- [ ] 6절 — kubectl 설정 (`admin.conf` 복사)
- [ ] 7절 — Calico (MTU 1370, interface `enp1s0`)
- [ ] 8절 — CoreDNS 확인 + toleration 파드로 `logs`/`exec` 검증 (taint 는 그대로)
- [ ] 9절 — 검증 (`INTERNAL-IP`가 `192.168.122.11`인지)
- [ ] 10절 — 스냅샷 `stage2-done`

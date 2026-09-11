# HAProxy — control plane 앞단 로드밸런서

**로드밸런서**다. 여러 대의 서버 앞에 서서 들어오는 연결을 나눠준다.
2001년부터 있었고 지금도 업계 표준으로 쓰인다. 쿠버네티스 전용이 아니라 웹 서버·DB 앞에도 붙인다.

## 왜 필요한가 — 접속할 주소가 하나여야 한다

control plane이 3대가 되면 문제가 생긴다. **워커들과 `kubectl`이 어디로 접속해야 하나?**

```bash
kubeadm join <여기에 뭘 적지?>:6443
```

kubeconfig에도 서버 주소가 딱 하나 들어간다.

```yaml
clusters:
- cluster:
    server: https://<하나뿐인 주소>:6443
```

**cp1의 IP를 적으면** 동작은 한다. 그런데 cp1이 죽는 순간 cp2·cp3가 멀쩡히 살아 있어도
클러스터 관리가 마비된다. `kubectl`도 안 되고 워커의 kubelet도 apiserver에 보고를 못 한다.
**HA를 만들었는데 HA가 아닌** 상황이다.

그래서 "살아 있는 아무 CP로나 연결해주는 고정 주소"가 필요하다.

```
워커 · kubectl → HAProxy:6443 ─┬─► cp1:6443  ✅
                                ├─► cp2:6443  ✅
                                └─► cp3:6443  ❌ 죽음 → 자동 제외
```

## 설정

```haproxy
# /etc/haproxy/haproxy.cfg

frontend k8s-api
    bind *:6443              # 여기로 받아서
    mode tcp
    default_backend k8s-cp

backend k8s-cp
    mode tcp
    balance roundrobin       # 번갈아 분배
    option tcp-check         # 살아있는지 검사
    server cp1 192.168.122.11:6443 check
    server cp2 192.168.122.12:6443 check
    server cp3 192.168.122.13:6443 check

# 상태 확인용 (선택이지만 매우 유용)
listen stats
    bind *:8404
    mode http
    stats enable
    stats uri /stats
    stats refresh 10s
```

`check`가 붙은 서버는 HAProxy가 주기적으로 접속을 시도한다.
응답이 없으면 **자동으로 분배 대상에서 뺐다가**, 살아나면 다시 넣는다. 장애 대응의 핵심이다.

`listen stats` 블록을 넣으면 브라우저에서 `http://<주소>:8404/stats`로
어느 백엔드가 UP/DOWN인지 눈으로 볼 수 있다. 진단할 때 크게 도움이 된다.

## ⭐ `mode tcp` — 반드시 이것이어야 한다

HAProxy는 두 가지 방식으로 동작할 수 있다.

| 모드 | 계층 | 하는 일 |
|---|---|---|
| `mode http` | L7 | HTTP를 해석. URL·헤더 보고 라우팅, TLS 종료 |
| **`mode tcp`** | **L4** | **바이트를 그대로 전달.** 내용을 안 봄 |

**apiserver 앞에는 반드시 `tcp`를 쓴다.**

apiserver는 **mTLS**(양방향 인증서)로 클라이언트를 인증한다.
`kubectl`이 보내는 인증서로 "이 사람이 누구인가"를 판단하고 RBAC을 적용한다.

`mode http`로 두면 HAProxy가 TLS를 중간에서 풀어버린다.
그러면 apiserver 입장에서는 **모든 요청이 HAProxy에서 온 것**으로 보인다.
클라이언트 인증서가 사라지니 **RBAC이 통째로 무너진다.**

`mode tcp`는 암호화된 바이트를 그대로 넘기기만 한다.
HAProxy는 내용이 뭔지 모르고, apiserver는 원래 클라이언트의 인증서를 그대로 받는다.

## HAProxy 자체가 단일 장애점이다

HAProxy가 죽으면 CP 3대가 살아 있어도 접속을 못 한다.
**로드밸런서 앞에 또 로드밸런서가 필요한** 문제다.

실무에서는 이렇게 푼다.

| 방법 | 설명 |
|---|---|
| **keepalived + VIP** | HAProxy 2대가 가상 IP 하나를 공유. 한 대가 죽으면 다른 대가 그 IP를 넘겨받음 |
| **클라우드 LB** | AWS NLB, GCP LB 등. 클라우드가 HA를 책임짐 |
| **kube-vip** | 쿠버네티스 전용. static pod로 떠서 CP 노드들이 VIP를 나눠 가짐. 외부 LB 불필요 |

> 이 프로젝트에서는 **HAProxy 한 대로 충분하다.**
> 호스트가 2개뿐이라 완전한 HA는 애초에 불가능하고, **패턴을 익히는 것**에 의미가 있다.
>
> kube-vip이 요즘 홈랩·소규모 클러스터에서 인기가 많지만,
> CKA 학습 관점에서는 HAProxy가 **동작이 눈에 보여서** 이해하기 좋다.
> `haproxy.cfg`를 읽으면 무슨 일이 벌어지는지 그대로 드러난다.

## 이 프로젝트에서의 배치

k8s-2 호스트에 직접 올린다.

```
k8s-2 호스트
├─ HAProxy (192.168.122.1:6443)   ← virbr0 게이트웨이 주소
└─ VM들 (192.168.122.11 ~)
```

`192.168.122.1`은 `virbr0`의 주소라 모든 VM이 닿는다.
Stage 8에서 k8s-1의 VM들(`192.168.121.x`)도 라우팅으로 여기 닿게 된다.

```bash
sudo kubeadm init \
  --control-plane-endpoint=192.168.122.1:6443 \
  --pod-network-cidr=10.244.0.0/16 \
  --upload-certs \
  --kubernetes-version=v1.35.0
```

> ⚠️ **이 주소가 클러스터의 영구 주소가 된다.**
> CP를 3대로 늘려도, 한 대가 죽어도 이 주소는 그대로다.
> **Stage 2에서 미리 잡아둬야 한다** — 나중에 바꾸려면 인증서를 전부 재발급해야 한다.

## 설치와 운영

```bash
sudo apt-get install -y haproxy

# 설정 문법 검사 — 재시작 전에 반드시
sudo haproxy -c -f /etc/haproxy/haproxy.cfg

sudo systemctl enable --now haproxy
sudo systemctl status haproxy
```

### 검증

```bash
# 1. 포트가 열렸는가
sudo ss -lntp | grep 6443

# 2. 백엔드에 닿는가 (VM에서)
nc -vz -w3 192.168.122.1 6443

# 3. apiserver까지 도달하는가
curl -k -o /dev/null -w '%{http_code}\n' https://192.168.122.1:6443/healthz
```

3번은 `200`이든 `401`이든 **둘 다 성공 신호**다.
HTTP 응답 코드가 돌아왔다는 것은 TCP 연결과 TLS 핸드셰이크가 끝나고
**진짜 apiserver가 응답했다**는 뜻이기 때문이다.
연결 자체가 안 되면 `curl: (7) Failed to connect`가 난다 — 그게 실패다.

### 진단

| 증상 | 확인 | 의미 |
|---|---|---|
| 연결 거부 | `systemctl status haproxy` | 데몬이 죽었거나 설정 오류 |
| ↳ | `haproxy -c -f ...` | 설정 문법 오류 |
| 연결은 되는데 응답 없음 | `:8404/stats` | 백엔드가 전부 DOWN |
| ↳ | 백엔드에 직접 `nc -vz cp1 6443` | apiserver가 죽었는가 |
| RBAC이 이상하게 동작 | `mode` 확인 | **`http`로 되어 있으면 안 됨** |
| 로그 | `journalctl -u haproxy -f` | |

## 관련

- 왜 CP가 3대여야 하는가 (쿼럼) → [`../kubernetes/etcd.md`](../kubernetes/etcd.md)
- 포트 도달성 확인 → [`../network/diagnosis/02_nc.md`](../network/diagnosis/02_nc.md)

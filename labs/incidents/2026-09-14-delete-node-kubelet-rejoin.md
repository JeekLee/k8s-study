# 2026-09-14 — `kubectl delete node` 후 노드를 되살리기

## 증상

Stage 3 의 노드 장애 실습 중 워커를 클러스터에서 뺐다.

```bash
kubectl delete node k2-w1
```

노드가 사라지고 파드가 전부 `k2-w2` 로 옮겨갔다.

```
NAME     STATUS   ROLES           AGE     VERSION
k2-cp1   Ready    control-plane   3d21h   v1.35.8
k2-w2    Ready    worker          3d20h   v1.35.8
```

**되돌리려는데 방법이 떠오르지 않았다.**
`kubeadm reset` 후 다시 `join` 하는 것 말고 더 가벼운 방법이 있는지가 궁금했다.

## 확인한 것

VM 은 멀쩡히 살아 있고 kubelet 도 돌고 있었다.

```bash
ssh k2-w1
systemctl is-active kubelet      # → active
```

로그를 보니 계속 같은 에러를 뱉는 중이었다.

```
E0914 05:58:24 kubelet_node_status.go:474] "Error updating node status, will retry"
  err="error getting node \"k2-w1\": nodes \"k2-w1\" not found"
E0914 05:58:24 kubelet_node_status.go:461] "Unable to update node status"
  err="update node status exceeds retry count"
```

**없는 Node 를 갱신하려다 실패하고 있었다.**
재등록을 시도하는 게 아니라 갱신만 반복한다는 점이 중요하다.

자격증명은 그대로였다.

```bash
ls -la /etc/kubernetes/kubelet.conf
# -rw------- 1 root root 1946 Sep 10 09:03

sudo openssl x509 -in $(sudo readlink -f /var/lib/kubelet/pki/kubelet-client-current.pem) \
     -noout -subject -enddate
# subject=O = system:nodes, CN = system:node:k2-w1
# notAfter=Sep 10 08:58:23 2027 GMT
```

**인증서가 1년 남아 있다.** 그렇다면 `join` 으로 새로 받을 이유가 없다.

## 원인

**`kubeadm join` 은 Node 오브젝트를 만드는 명령이 아니다.**

```
kubeadm join ─┬→ 토큰으로 API 서버 인증
              └→ CSR 제출 → 클라이언트 인증서 수령 → kubelet.conf 작성
                                                        │
kubelet 기동 ─────────────────────────────────────────→ 이 자격으로
                                                        Node 오브젝트를 스스로 만든다
```

join 이 하는 일은 **자격증명을 받아오는 것**까지다.
Node 오브젝트를 만드는 것은 kubelet 이 기동할 때 하는 **자기 등록(self-registration)** 이다.

그런데 kubelet 은 등록에 성공하면 내부 플래그를 세우고 **다시는 등록을 시도하지 않는다.**
그래서 실행 중에 Node 를 지우면 스스로 복구하지 못하고 위 로그처럼 갱신만 반복한다.

`kubectl delete node` 는 **API 오브젝트만 지운다.** 노드 자체에는 아무 일도 일어나지 않는다.

## 해결

kubelet 을 재시작하면 플래그가 초기화되면서 다시 등록한다.

```bash
ssh k2-w1 "sudo systemctl restart kubelet"
```

```
NAME     STATUS   ROLES           AGE     VERSION
k2-cp1   Ready    control-plane   3d21h   v1.35.8
k2-w1    Ready    worker          79s     v1.35.8     ← 돌아왔다
k2-w2    Ready    worker          3d20h   v1.35.8
```

`reset` 도 `join` 도 필요 없었다.

### 라벨은 따로 붙여야 한다

새로 만들어진 Node 오브젝트라 **사람이 붙인 것은 전부 없다.**
kubelet 이 채우는 것은 자기가 아는 것(이름·주소·용량·OS 정보)뿐이다.

```bash
kubectl label node k2-w1 node-role.kubernetes.io/worker=
```

이걸 빼먹으면 `ROLES` 가 `<none>` 으로 나온다.
테인트·어노테이션을 걸어뒀다면 그것도 같이 사라진다.

## 결과 — 무엇이 돌아오고 무엇이 안 돌아왔나

| | |
|---|---|
| `calico-node` | ✅ DaemonSet 이라 새 노드에 자동으로 뜬다 |
| `spread` 파드 | ✅ `Pending` 이던 것 하나가 w1 으로 갔다 |
| `web` · `sized` 파드 | ❌ **w2 에 그대로 남았다** |

```
spread-69c54b8b8c-ttgmb   Running   k2-w1     ← Pending 이던 것이 배치됨
spread-69c54b8b8c-n85zl   Pending   <none>    ← 워커가 2대뿐이라 여전히 대기
web-578757666d-*  (6개)   Running   k2-w2     ← 전부 w2. 돌아오지 않는다
sized-c87855d76-* (3개)   Running   k2-w2     ← 마찬가지
```

**이미 `Running` 인 파드는 노드가 추가돼도 재배치되지 않는다.**
스케줄러는 **배치되지 않은 파드만** 다룬다. 한번 노드가 정해지면 그 파드가 죽기 전까지 그대로다.

`spread` 만 움직인 이유는 그 파드가 3일째 `Pending` 이어서다.
`podAntiAffinity` 가 노드당 하나만 허용하는데 워커가 1대로 줄어 갈 곳이 없었고,
w1 이 돌아오자 바로 배치됐다. 나머지 하나는 워커가 2대뿐이라 계속 대기한다.

> 균형을 되찾으려면 파드를 직접 지우거나(`kubectl rollout restart`),
> **descheduler** 같은 별도 도구가 필요하다. 쿠버네티스 기본 동작이 아니다.

### Calico IP 블록은 새지 않았다

노드마다 파드 IP 블록(/26)을 잡는데, 삭제·재등록 과정에서 옛 블록이 남을 수 있다.

```bash
kubectl get blockaffinities \
  -o custom-columns=NAME:.metadata.name,NODE:.spec.node,CIDR:.spec.cidr,STATE:.spec.state
```

```
k2-cp1-10-244-162-64-26   k2-cp1   10.244.162.64/26   confirmed
k2-w1-10-244-253-64-26    k2-w1    10.244.253.64/26   confirmed   ← 같은 블록을 다시 잡았다
k2-w2-10-244-28-64-26     k2-w2    10.244.28.64/26    confirmed
```

`k2-w1` 에 블록이 하나뿐이다. **삭제 전과 같은 대역(`10.244.253.64/26`)을 그대로 받았다.**
`calico-kube-controllers` 가 정리해준 것으로 보인다.

## 언제는 `reset` + `join` 이 필요한가

| 상황 | 방법 |
|---|---|
| Node 오브젝트만 지웠고 VM 은 그대로 | **kubelet 재시작** |
| 인증서가 만료됐다 | `reset` + `join` |
| `/etc/kubernetes` 를 날렸다 | `reset` + `join` |
| VM 을 새로 만들었다 | `reset` 불필요, `join` |
| 클러스터를 갈아엎었다 (CA 가 바뀜) | `reset` + `join` |

`reset` 을 할 때는 **CNI 잔재도 같이 지워야** 한다.
안 그러면 재가입 후 파드 IP 가 겹치거나 라우팅이 꼬인다.

```bash
sudo kubeadm reset -f
sudo rm -rf /etc/cni/net.d /var/lib/cni /var/lib/calico /run/calico
sudo iptables -F && sudo iptables -t nat -F && sudo iptables -t mangle -F && sudo iptables -X
```

## 배운 것

- **`kubectl delete node` 는 노드를 제거하지 않는다.** API 오브젝트만 지운다.
  kubelet 이 살아 있으면 **재시작만으로 돌아온다** — 실무에서 "분명 지웠는데 다시 생김" 의 정체다.
  진짜로 빼려면 kubelet 을 멈추거나 `reset` 해야 한다.
- **`join` 은 등록이 아니라 자격증명 발급이다.** 인증서가 살아 있으면 다시 할 이유가 없다.
  `/etc/kubernetes/kubelet.conf` 와 `kubelet-client-current.pem` 이 있는지부터 본다.
- **kubelet 은 한 번만 등록을 시도한다.** 그래서 스스로 복구하지 못하고 갱신 에러만 반복한다.
  로그의 `"Unable to update node status"` 가 이 상태의 신호다.
- **Node 오브젝트의 라벨·테인트는 재등록 시 사라진다.** kubelet 이 아는 것만 채워진다.
- **노드가 추가돼도 기존 파드는 재배치되지 않는다.** 스케줄러는 배치 전 파드만 다룬다.
  균형을 되찾으려면 사람이 개입하거나 descheduler 가 필요하다.

관련: [`docs/stages/stage-03-multi-node.md`](../../docs/stages/stage-03-multi-node.md) ·
[`notes/kubernetes/scheduler.md`](../../notes/kubernetes/scheduler.md)

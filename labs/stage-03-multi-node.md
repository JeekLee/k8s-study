# Stage 3 — 다중 노드 (호스트 내부)

| | |
|---|---|
| 일자 | 2026-09-11 ~ 09-14 |
| 결과 | ✅ **거의 완료** — 4-6 과 스냅샷 미실시 |
| 절차 | [`docs/stages/stage-03-multi-node.md`](../docs/stages/stage-03-multi-node.md) |

> ⚠️ **이 기록은 셸 히스토리와 클러스터 상태에서 복원했다.**
> 명령은 `~/.bash_history` 에 남은 실제 실행분이고,
> 결과는 이벤트·노드 상태·커널 버전 등 남아 있는 증거에서 확인한 것이다.
> **터미널 출력을 그때그때 남기지 않아 일부는 결과만 적는다.**
> → [배운 것](#배운-것) 마지막 항목

## 최종 상태

```
NAME     STATUS   ROLES           AGE     VERSION   INTERNAL-IP      KERNEL
k2-cp1   Ready    control-plane   3d22h   v1.35.8   192.168.122.11   6.8.0-138-generic
k2-w1    Ready    worker          26m     v1.35.8   192.168.122.21   6.8.0-139-generic
k2-w2    Ready    worker          3d21h   v1.35.8   192.168.122.22   6.8.0-138-generic
```

실습용 워크로드는 전부 정리했다.

---

## 1~2. 워커 준비와 join

```bash
kubeadm token list                          # 남은 시간 확인
kubeadm token create --print-join-command
```

호스트에서 `ssh k2-w1 "sudo $JOIN"` 으로 던졌다.
VM 터미널에 직접 붙여넣으면 잘리는 문제 때문 —
→ [`incidents/2026-09-10-terminfo-xterm-ghostty.md`](incidents/2026-09-10-terminfo-xterm-ghostty.md)

**role 라벨은 join 이 붙여주지 않는다.** 직접 붙였다.

```bash
kubectl label node k2-w1 node-role.kubernetes.io/worker=
kubectl label node k2-w2 node-role.kubernetes.io/worker=
```

## 4-1. Stage 2 에서 `Pending` 이던 파드가 이제 뜬다

Stage 2 에서는 toleration 을 붙여야만 떴던 파드를, 이번엔 그냥 띄워봤다.

```bash
kubectl run no-tol --image=nginx
kubectl get pod no-tol -o wide      # 워커에 배치됨
kubectl delete pod no-tol
```

Stage 2 에서 `Pending` 이던 것과 **같은 명령인데 이번엔 뜬다.**
control plane 테인트를 피할 곳이 생겼기 때문이다.

## 4-2. replica 를 늘려 분산 관찰

```bash
kubectl create deployment web --image=nginx --replicas=6
kubectl get pods -o wide
```

**w1 3개, w2 3개로 나뉘었다.** 두 워커의 스펙이 같아 점수가 같았다.

## 4-3. `requests` 와 `limits`

아무것도 선언하지 않은 `web` 파드가 6개나 도는데도 장부는 비어 있었다.

```bash
kubectl describe node k2-w1 | grep -A8 "Allocated resources"
```

```
Resource           Requests   Limits
cpu                0 (0%)     0 (0%)
memory             0 (0%)     0 (0%)
ephemeral-storage  0 (0%)     0 (0%)
hugepages-1Gi      0 (0%)     0 (0%)
hugepages-2Mi      0 (0%)     0 (0%)
```

**`requests` 를 안 쓰면 스케줄러 장부에 0으로 잡힌다.**
실제로 메모리를 쓰고 있어도 스케줄러는 모른다.

선언한 배포를 하나 만들어 비교했다.

```bash
kubectl apply -f - <<'YAML'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sized
spec:
  replicas: 3
  selector:
    matchLabels: { app: sized }
  template:
    metadata:
      labels: { app: sized }
    spec:
      containers:
        - name: nginx
          image: nginx
          resources:
            requests:
              cpu: "1"
              memory: 1Gi
YAML
```

```bash
kubectl describe node k2-w1 | grep -A6 "Allocated resources"   # cpu 1 (25%), memory 1Gi (13%)
kubectl describe node k2-w2 | grep -A6 "Allocated resources"   # cpu 2 (50%), memory 2Gi (26%)
```

**w1 에 1개, w2 에 2개**로 나뉘었다. 숫자가 처음으로 0이 아니게 됐다.

### QoS 확인

```bash
kubectl get pod -l app=web   -o jsonpath='{.items[0].status.qosClass}'   # BestEffort
kubectl get pod -l app=sized -o jsonpath='{.items[0].status.qosClass}'   # Burstable
```

`requests`·`limits` 를 어떻게 쓰느냐가 **등급을 자동으로 결정**한다.
따로 선언하는 필드가 아니다.

## 4-4. 자원이 모자라면 `Pending`

워커가 4코어인데 8코어를 요구했다.

```bash
kubectl run huge --image=nginx --overrides='
{"spec":{"containers":[{"name":"nginx","image":"nginx",
"resources":{"requests":{"cpu":"8"}}}]}}'

kubectl get pod huge                      # Pending
kubectl describe pod huge | tail -5       # Insufficient cpu
kubectl delete pod huge
```

**노드에 그만한 코어가 아예 없으니 영원히 `Pending`** 이다.
`requests` 는 "빈 자리가 이만큼 있어야 배치한다"는 뜻이므로,
실제 사용량과 무관하게 장부만 보고 거절한다.

## 4-5. `podAntiAffinity` — 배치 강제

```bash
kubectl apply -f - <<'YAML'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: spread
spec:
  replicas: 3
  selector:
    matchLabels: { app: spread }
  template:
    metadata:
      labels: { app: spread }
    spec:
      affinity:
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            - labelSelector:
                matchLabels: { app: spread }
              topologyKey: kubernetes.io/hostname
      containers:
        - name: nginx
          image: nginx
YAML

kubectl get pods -l app=spread -o wide
kubectl describe pod -l app=spread | grep -A3 Events | tail -5
```

**3개 중 2개만 뜨고 하나는 계속 `Pending`.** 워커가 2대뿐이라 갈 곳이 없다.

스케줄러 메시지가 정확했다.

```
0/3 nodes are available:
  1 node(s) had untolerated taint(s),            ← cp1, control-plane 테인트
  2 node(s) didn't match pod anti-affinity rules ← w1·w2 에 이미 하나씩
preemption: 0/3 nodes are available:
  1 Preemption is not helpful for scheduling,
  2 No preemption victims found for incoming pod.
```

**preemption 까지 시도했다가 포기한 것**도 보인다.
쫓아낼 우선순위 낮은 파드가 없으면 선점은 답이 아니다.

> `required` 라서 조건을 못 채우면 안 뜬다.
> `preferred` 였다면 같은 노드에라도 배치됐을 것이다.

## 5. `cordon` · `drain` · `uncordon`

### 5-2. `cordon` — 새로 들어오는 것만 막는다

```bash
kubectl cordon k2-w1
kubectl get nodes            # k2-w1  Ready,SchedulingDisabled
```

**이미 떠 있는 파드는 그대로다.** 그 상태에서 replica 를 늘려봤다.

```bash
kubectl scale deployment web --replicas=10
kubectl get pods -l app=web -o wide | awk '{print $7}' | sort | uniq -c
```

**늘어난 만큼 전부 w2 로 갔다.** cordon 은 "새 파드를 받지 않는다"일 뿐이다.

```bash
kubectl scale deployment web --replicas=6     # 되돌린다
```

### 5-3. `drain` — 비운다

```bash
kubectl drain k2-w1 --ignore-daemonsets
kubectl get pods -o wide
```

`--ignore-daemonsets` 가 필요한 이유는 `calico-node`, `kube-proxy` 가
**DaemonSet 이라 쫓아내도 그 노드에 다시 뜨기** 때문이다. 그래서 애초에 건드리지 않는다.

두 번째 시도에서는 `--delete-emptydir-data` 도 붙였다.

```bash
kubectl drain k2-w1 --ignore-daemonsets --delete-emptydir-data
```

`emptyDir` 을 쓰는 파드가 있으면 **데이터가 사라진다고 경고하며 멈춘다.**
지우겠다고 명시해야 진행된다.

### 5-4. `uncordon` — 다시 받는다

```bash
kubectl uncordon k2-w1
kubectl get nodes
kubectl get pods -o wide
```

**⭐ 파드가 자동으로 돌아오지 않았다.**

```bash
kubectl rollout restart deployment web    # 전부 새로 만들면 다시 분산된다
kubectl get pods -l app=web -o wide | awk '{print $7}' | sort | uniq -c
```

`uncordon` 은 "이제 받아도 된다"고 표시만 한다.
**이미 배치된 파드를 옮기는 일은 쿠버네티스가 하지 않는다.**
균형을 되찾으려면 파드를 새로 만들어야 한다.

### 5-5. 실제 시나리오 — 커널 업데이트

drain 한 상태에서 워커를 재부팅했다.

```bash
kubectl cordon k2-w1        # 더 이상 새 파드를 보내지 않는다
kubectl drain k2-w1 --ignore-daemonsets --delete-emptydir-data
ssh k2-w1 'sudo reboot'
# 올라온 뒤
kubectl uncordon k2-w1
```

커널 버전이 증거로 남았다.

```
k2-w1   6.8.0-139-generic     ← 재부팅하며 올라감
k2-w2   6.8.0-138-generic
k2-cp1  6.8.0-138-generic
```

**서비스 중단 없이 노드 하나를 점검하는 표준 절차**를 그대로 밟은 셈이다.

## 6. 노드 장애 시뮬레이션

```bash
kubectl delete node k2-w1        # 클러스터에서 제외
```

파드가 전부 w2 로 몰렸다. 되살리는 과정에서 예상 못 한 것을 배워
별도 기록으로 남겼다.

→ [`incidents/2026-09-14-delete-node-kubelet-rejoin.md`](incidents/2026-09-14-delete-node-kubelet-rejoin.md)

요지는 **`kubectl delete node` 가 노드를 제거하지 않는다**는 것.
kubelet 이 살아 있으면 `systemctl restart kubelet` 만으로 돌아온다.
`reset` 도 `join` 도 필요 없었다.

## 정리

실습용 워크로드를 전부 지웠다.

```bash
kubectl delete deployment web sized spread
```

---

## 미실시

| 항목 | 상태 |
|---|---|
| **4-6 `topologySpreadConstraints`** | 히스토리·이벤트에 흔적 없음 |
| **7. 스냅샷 `stage3-done`** | `k2-w1`·`k2-w2` 에 `fresh` 만, `k2-cp1` 은 `stage2-done` 까지 |

```
[k2-cp1] clean  stage2-done
[k2-w1]  fresh
[k2-w2]  fresh
```

`topologySpreadConstraints` 는 `podAntiAffinity` 와 비교할 때 의미가 크다.
**같은 3 replica 인데 `whenUnsatisfiable: ScheduleAnyway` 면 세 번째도 뜬다** —
"강제"와 "선호"의 차이를 한 번에 보여주는 대비다. Stage 4 진입 전에 해두면 좋다.

---

## 배운 것

- **`requests` 를 안 쓰면 스케줄러 장부는 0이다.** 실제 사용량과 무관하다.
  선언하지 않은 파드가 수십 개 떠 있어도 노드는 "비어 있다"고 판단한다.
- **QoS 는 따로 선언하는 것이 아니다.** `requests`·`limits` 조합이 등급을 자동으로 만든다.
- **`required` 는 못 채우면 안 뜬다.** `podAntiAffinity` 로 3 replica 를 2 노드에 강제하면
  하나는 영원히 `Pending` 이다. 스케줄러 메시지에 이유가 정확히 나온다.
- **스케줄러는 배치 전 파드만 다룬다.** `uncordon` 해도, 노드를 되살려도
  이미 도는 파드는 옮겨지지 않는다. `rollout restart` 하거나 descheduler 가 필요하다.
- **`drain` 의 플래그는 이유가 있다.** `--ignore-daemonsets` 는 어차피 다시 뜨기 때문,
  `--delete-emptydir-data` 는 데이터가 사라지니 명시하라는 뜻.
- **`kubectl delete node` 는 노드를 제거하지 않는다.** API 오브젝트만 지운다.
- **⚠️ 실습 중 출력을 남기지 않으면 기록이 반쪽이 된다.**
  이번엔 셸 히스토리와 클러스터 상태에서 복원해야 했고,
  `describe` 출력 같은 것은 결국 되살리지 못했다.
  다음부터는 `script -f ~/stage-N.log` 로 세션을 통째로 떠두거나,
  중요한 출력은 `| tee` 로 파일에 남긴다.

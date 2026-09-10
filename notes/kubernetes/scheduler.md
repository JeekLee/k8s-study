# kube-scheduler — 파드를 어느 노드에 놓을지

**스케줄러는 배치를 *결정*할 뿐 실행하지 않는다.**
결정 결과를 apiserver 에 기록하면(`spec.nodeName` 설정),
그 노드의 kubelet 이 그것을 보고 파드를 띄운다.

```
스케줄러 → apiserver → etcd 에 nodeName 기록
                ↓ watch
          해당 노드의 kubelet 이 감지 → containerd 에 지시
```

## 두 단계

```
파드 하나 →  [필터]   가능한 노드만 남긴다
          →  [점수]   남은 것 중 가장 높은 점수
          →  [바인딩] 그 노드로 확정
```

### ① 필터 (Filtering)

하나라도 걸리면 탈락한다.

| 플러그인 | 검사 |
|---|---|
| `NodeResourcesFit` | 남은 자원 ≥ 파드의 `requests` |
| `TaintToleration` | taint 를 견딜 수 있는가 |
| `NodeAffinity` / `nodeSelector` | 노드 라벨 조건 |
| `NodeUnschedulable` | `cordon` 된 노드 제외 |
| `PodTopologySpread` | `whenUnsatisfiable: DoNotSchedule` 인 제약 |
| `InterPodAffinity` | `requiredDuringScheduling...` |
| `NodePorts` | hostPort 충돌 |
| `VolumeBinding` | PV 가 그 노드에서 접근 가능한가 |

**`FailedScheduling` 메시지가 이 단계의 탈락 사유다.**

```
0/3 nodes are available: 1 node(s) had untolerated taint(s), 2 Insufficient cpu
                          └ control plane 탈락        └ 워커 둘 탈락
```

노드별로 왜 떨어졌는지 알려주므로 **끝까지 읽어야 한다.**

### ② 점수 (Scoring)

살아남은 노드마다 플러그인이 0~100 점을 매기고, **가중치를 곱해 합산**한다.

| 플러그인 | 기본 가중치 | 선호하는 것 |
|---|---:|---|
| `TaintToleration` | 3 | taint 가 적은 노드 |
| `PodTopologySpread` | 2 | **치우침이 덜해지는** 노드 |
| `InterPodAffinity` | 2 | affinity 선호 조건 만족 |
| `NodeAffinity` | 2 | 노드 라벨 선호 조건 |
| `NodeResourcesFit` | 1 | **여유 자원이 많은** 노드 (LeastAllocated) |
| `NodeResourcesBalancedAllocation` | 1 | CPU·메모리 사용률이 **고른** 노드 |
| `ImageLocality` | 1 | **이미지를 이미 가진** 노드 |

합계 최고점이 이긴다. **동점이면 그중 무작위**로 고른다.

가중치와 플러그인 구성은 `KubeSchedulerConfiguration` 으로 바꿀 수 있다.

#### `LeastAllocated` 계산

```
점수 = (allocatable − 이미 요청된 양) / allocatable × 100
       (CPU 와 메모리 각각 계산해 평균)
```

**"이미 요청된 양"은 `requests` 의 합이다.** 실제 사용량이 아니다.

#### `BalancedAllocation`

CPU 는 90% 인데 메모리는 10% 인 노드보다,
둘 다 50% 인 노드를 선호한다. **한쪽만 남아 쓸모없어지는 것을 피한다.**

---

## ⭐ 한 번에 하나씩 결정한다

replica 6개를 놓고 "3개씩 나누자"고 **계획하지 않는다.**
파드 하나를 배치하고, **바뀐 상태에서** 다음 파드를 다시 계산한다.

### `requests` 없는 파드 6개, 워커 2대

| 파드 | 자원 점수 | 분산 점수 | 이미지 점수 | 결과 |
|---|---|---|---|---|
| 1 | 동점 (requests=0) | 동점 (0:0) | 동점 (이미지 없음) | **무작위** → w1 |
| 2 | 동점 | **w2 우세** (1:0) | w1 우세 (이미지 보유) | 2 > 1 → **w2** |
| 3 | 동점 | 동점 (1:1) | 동점 | **무작위** |
| 4~6 | 동점 | 치우친 쪽 회피 | 동점 | 대체로 균형 |

**`requests` 가 0이면 자원 점수가 무의미해진다.**
실제 분산을 만드는 것은 대부분 `PodTopologySpread` 다.

> 재미있는 긴장 — **`ImageLocality` 는 반대로 당긴다.**
> 첫 파드가 이미지를 받은 노드는 다음 파드에게 더 매력적이다.
> 가중치가 1 대 2 라 분산이 이기지만, **완벽히 균등하지 않은 이유** 중 하나다.

### `requests` 를 준 경우 (워커 4 vCPU, 파드 1 vCPU)

| 파드 | w1 여유 | w2 여유 | 결과 |
|---|---:|---:|---|
| 1 | 4 | 4 | 무작위 → w1 |
| 2 | 3 | 4 | **w2** |
| 3 | 3 | 3 | 무작위 |
| 4 | 2 | 3 | **w2** |
| … | | | 8개까지 배치, 9번째부터 `Pending` |

**`requests` 가 있으면 자원 점수가 실제로 작동해 훨씬 예측 가능해진다.**

---

## 기본 topology spread 제약

쿠버네티스는 명시하지 않아도 이 제약을 **점수 단계에** 적용한다.

```yaml
defaultConstraints:
  - maxSkew: 3
    topologyKey: kubernetes.io/hostname
    whenUnsatisfiable: ScheduleAnyway
  - maxSkew: 5
    topologyKey: topology.kubernetes.io/zone
    whenUnsatisfiable: ScheduleAnyway
```

**`ScheduleAnyway` 이므로 권고이지 강제가 아니다.**
그래서 6개가 정확히 3:3 이 되지 않을 수 있다.

강제하려면 파드에 직접 적는다.

```yaml
topologySpreadConstraints:
  - maxSkew: 1
    topologyKey: kubernetes.io/hostname
    whenUnsatisfiable: DoNotSchedule       # ← 필터 단계로 올라간다
    labelSelector:
      matchLabels: { app: web }
```

| 값 | 언제 작동 |
|---|---|
| `DoNotSchedule` | **필터** — 어기면 `Pending` |
| `ScheduleAnyway` | **점수** — 어겨도 배치는 된다 |

`podAntiAffinity` 도 같은 구조다.

| | 단계 |
|---|---|
| `requiredDuringSchedulingIgnoredDuringExecution` | 필터 |
| `preferredDuringSchedulingIgnoredDuringExecution` | 점수 |

> `IgnoredDuringExecution` 은 **이미 뜬 파드는 건드리지 않는다**는 뜻이다.
> 나중에 조건이 깨져도 쫓아내지 않는다.

---

## 재배치는 하지 않는다

**스케줄러는 한 번 정한 것을 바꾸지 않는다.**
나중에 노드가 한가해져도 이미 배치된 파드는 움직이지 않는다.

- `uncordon` 해도 옮겨간 파드가 돌아오지 않는 이유
- 노드를 추가해도 기존 파드가 재분배되지 않는 이유

재배치가 필요하면 **Descheduler** 라는 별도 애드온을 쓴다.
기본 쿠버네티스에는 없다.

파드를 옮기고 싶으면 지우면 된다. ReplicaSet 이 새로 만들면서 다시 스케줄링된다.

```bash
kubectl rollout restart deployment web     # 롤링으로 전부 재배치
```

---

## 배치를 제어하는 방법

| 방법 | 성격 | 쓰임 |
|---|---|---|
| `nodeName` | **스케줄러를 건너뛴다** | 디버깅용. 실무에서는 쓰지 않는다 |
| `nodeSelector` | 필터 | 라벨이 맞는 노드에만 |
| `nodeAffinity` | 필터 또는 점수 | `nodeSelector` 의 확장. `In`, `NotIn`, `Exists` 등 |
| `taint` + `toleration` | 필터 | **노드가 거부**하는 방식 (반대 방향) |
| `podAffinity` | 필터 또는 점수 | 특정 파드 **곁에** |
| `podAntiAffinity` | 필터 또는 점수 | 특정 파드와 **떨어져서** |
| `topologySpreadConstraints` | 필터 또는 점수 | 치우침 정도를 수치로 |
| `priorityClassName` | 선점 | 자원이 없으면 낮은 우선순위 파드를 **쫓아낸다** |

> **taint/toleration 과 affinity 는 방향이 반대다.**
> taint 는 **노드가** "오지 마"라고 하는 것이고,
> affinity 는 **파드가** "저기로 갈래"라고 하는 것이다.

---

## 진단

```bash
kubectl describe pod <파드> | grep -A10 Events
# FailedScheduling 메시지를 끝까지 읽는다

kubectl describe node <노드> | grep -A8 "Allocated resources"
# requests 합계. 실제 사용량이 아니다

kubectl get pods -o wide --sort-by=.spec.nodeName
kubectl get events --sort-by=.lastTimestamp | grep -i schedul

# 스케줄러 자체
kubectl -n kube-system logs kube-scheduler-<노드명> | tail -30
```

| 증상 | 확인 |
|---|---|
| 계속 `Pending` | `describe pod` 의 `FailedScheduling` — 노드별 탈락 사유 |
| 한 노드에만 몰림 | `requests` 가 있는가. 없으면 자원 점수가 작동하지 않는다 |
| `Insufficient cpu/memory` | `describe node` 의 Allocated 와 파드 `requests` 비교 |
| `untolerated taint` | `describe node \| grep Taints` |
| 노드는 한가한데 배치 안 됨 | `cordon` 상태인지 — `kubectl get nodes` 의 `SchedulingDisabled` |

## 관련

- 상태가 저장되는 곳 → [`etcd.md`](etcd.md)
- 배치 이후 실행 → [`container-runtime.md`](container-runtime.md)
- Stage 3 실습 → [`../../docs/stages/stage-03-multi-node.md`](../../docs/stages/stage-03-multi-node.md)

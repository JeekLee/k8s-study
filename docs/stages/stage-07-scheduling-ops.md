# Stage 7 — 스케줄링과 운영

| | |
|---|---|
| 예상 소요 | 2~3일 |
| 선행 | [Stage 6](stage-06-event-driven.md) |
| 대상 | 앞 단계에서 올린 전체 스택 |
| 기록할 곳 | `labs/stage-07-scheduling-ops.md` |

> 📝 계획 수준. 진입할 때 실행 절차로 확장한다.

## 이 단계에서 하는 일

**구성은 그대로다. 돌아가는 앱에 운영 관점을 입힌다.**

Stage 3 에서 빈 클러스터로 스케줄러를 관찰했다면,
여기서는 **실제 워크로드에 적용**한다 — 티어마다 요구가 다르기 때문이다.

| 티어 | 요구 |
|---|---|
| `web`·`order` | 부하에 따라 늘어나야 (HPA) |
| `mysql` | 한 노드에 묶임, 절대 축출되면 안 됨 (priorityClass) |
| `kafka` | 브로커가 서로 다른 노드에 (anti-affinity) |
| 배치 | 남는 자원으로, 밀려도 됨 (낮은 priority) |

## 완료 기준

- [ ] 부하를 걸어 HPA 가 replica 를 늘리는 것을 확인
- [ ] `drain` 중에도 **서비스가 끊기지 않는다** (PDB)
- [ ] Kafka 브로커가 서로 다른 노드에 배치된다
- [ ] 자원이 부족할 때 배치 파드가 **선점당한다**
- [ ] QoS 클래스별로 OOM 시 축출 순서가 다른 것을 확인

## 다룰 것

### QoS 클래스 — `requests` 와 `limits` 의 조합

| 클래스 | 조건 | 메모리 부족 시 |
|---|---|---|
| **Guaranteed** | requests == limits (전부) | **가장 나중에** 축출 |
| **Burstable** | requests < limits | 중간 |
| **BestEffort** | 아무것도 없음 | **가장 먼저** 축출 |

```bash
kubectl get pod <파드> -o jsonpath='{.status.qosClass}'
```

**DB 는 Guaranteed, 배치는 BestEffort** 로 두는 것이 기본 전략이다.

### HPA

```bash
kubectl autoscale deployment order --cpu-percent=70 --min=2 --max=10
```

`metrics-server` 가 필요하다. 부하는 `hey` 나 `k6` 로 건다.

> **`requests` 가 없으면 HPA 가 동작하지 않는다.** 백분율의 기준이 `requests` 이기 때문이다.
> Stage 3 에서 확인한 "requests 가 없으면 스케줄러가 자원을 0 으로 본다"와 같은 뿌리다.

### PodDisruptionBudget

```yaml
spec:
  minAvailable: 2        # 또는 maxUnavailable: 1
  selector:
    matchLabels: { app: order }
```

**`drain` 이 PDB 를 존중한다.** 최소 개수를 못 지키면 축출을 멈추고 기다린다.

Stage 3 에서 `drain` 했을 때는 순식간에 비워졌다.
PDB 를 걸고 다시 해보면 **한 번에 하나씩만** 빠지는 것을 볼 수 있다.

### priorityClass 와 선점

```yaml
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata: { name: critical }
value: 1000000
```

자원이 없을 때 스케줄러가 **낮은 우선순위 파드를 쫓아내고** 높은 것을 넣는다.
배치 작업을 낮게 두고, 일부러 자원을 채운 뒤 DB 파드를 띄워 확인한다.

### affinity 실전 적용

| 대상 | 규칙 |
|---|---|
| Kafka 브로커 | `podAntiAffinity` required — 서로 다른 노드 |
| `order` replica | `topologySpreadConstraints` maxSkew 1 |
| `mysql` | PVC 때문에 자동으로 노드에 묶임 |

Stage 3 에서 빈 파드로 해본 것을 **실제 의존성이 있는 워크로드**에 건다.

## 자주 막히는 곳

| 증상 | 확인 |
|---|---|
| HPA 가 `<unknown>` | metrics-server, `requests` 유무 |
| `drain` 이 멈춤 | PDB 때문이다 — 의도한 동작 |
| 파드가 자꾸 축출됨 | QoS 가 BestEffort 인가 |
| 선점이 안 일어남 | `preemptionPolicy`, priority 값 차이 |

관련: [`notes/kubernetes/resources.md`](../../notes/kubernetes/resources.md) · [`notes/kubernetes/scheduler.md`](../../notes/kubernetes/scheduler.md)

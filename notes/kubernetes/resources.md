# 자원 — `requests` · `limits` · QoS

**둘 다 측정값이 아니라 선언값이다.** 안 적으면 0이고,
0은 "측정해보니 0"이 아니라 "선언하지 않았다"는 뜻이다.

## 역할이 다르다

| | 뜻 | 누가 쓰나 | 언제 |
|---|---|---|---|
| **`requests`** | "이만큼은 **확보해줘**" | **스케줄러** | 배치를 정할 때 |
| **`limits`** | "이 이상은 **못 쓴다**" | **kubelet / 커널 cgroup** | 실행 중 계속 |

`requests` 는 **예약 장부**다. 스케줄러는 노드의 `Allocatable` 에서
이미 배치된 파드들의 `requests` 합을 뺀 값을 "남은 자리"로 본다.
**실제 사용량은 보지 않는다.**

→ [`scheduler.md`](scheduler.md)

## 실측 — 장부와 현실의 차이

`kubectl create deployment` 로 만든 nginx 3개가 도는 노드 (2026-09-11, `k2-w1`):

```
스케줄러 장부 :  cpu 0 (0%)   memory 0 (0%)
실제 사용     :  339 MiB
memory.max    :  max              ← 상한 없음
```

**스케줄러는 이 노드가 텅 빈 줄 안다.**
파드를 계속 밀어넣다가 실제 메모리가 바닥나면 그때 OOM 이 터진다.

`kubectl top` 은 metrics-server 가 있어야 한다. 없으면 노드에서 직접 본다.

```bash
for f in /sys/fs/cgroup/kubepods.slice/kubepods-besteffort.slice/kubepods-besteffort-pod*/memory.current; do
  echo "$(( $(cat $f) / 1024 / 1024 )) MiB"
done

sudo crictl stats          # CRI 로도 볼 수 있다
```

## CPU 와 메모리는 초과했을 때가 다르다

| | 초과 시 | 성격 |
|---|---|---|
| **CPU** | **스로틀링** — 느려질 뿐 죽지 않는다 | 압축 가능 (compressible) |
| **메모리** | **OOMKilled** — 즉시 강제 종료 | 압축 불가능 (incompressible) |

메모리는 "조금만 쓰게 하기"가 불가능하다.
이미 할당된 것을 뺏을 수 없으니 죽이는 수밖에 없다.

> **`limits.memory` 는 걸고, `limits.cpu` 는 신중하게.**
> CPU 제한은 노드에 여유가 있는데도 인위적으로 느리게 만든다.
> 지연에 민감한 서비스에서는 CPU limit 이 오히려 장애 원인이 되기도 한다.

## 자원 종류

| 자원 | 단위 | 초과 시 |
|---|---|---|
| `cpu` | `1` = 1 코어, `100m` = 0.1 코어 | 스로틀링 |
| `memory` | `Mi`, `Gi` (2진) / `M`, `G` (10진) | **OOMKilled** — 컨테이너 재시작 |
| `ephemeral-storage` | `Mi`, `Gi` | **파드 축출** (Evicted) |
| `hugepages-2Mi` · `hugepages-1Gi` | `Mi`, `Gi` | — |

> **`Mi` 와 `M` 은 다르다.** `1Gi` = 1073741824, `1G` = 1000000000.
> 메모리는 관례적으로 `Mi`/`Gi` 를 쓴다.

### `ephemeral-storage`

노드 루트 디스크를 컨테이너가 쓰는 몫. **PV 와 달리 파드가 죽으면 함께 사라진다.**

| 여기 쌓이는 것 | 위치 |
|---|---|
| 컨테이너 쓰기 레이어 | 오버레이 상위 레이어 |
| `emptyDir` 볼륨 | `/var/lib/kubelet/pods/...` |
| **컨테이너 로그** | `/var/log/pods/...` |

> ⚠️ **흔한 사고** — 앱이 로그를 **파일로** 쌓다가 노드 디스크가 차고,
> kubelet 이 `DiskPressure` 를 선언해 **그 노드의 파드를 무더기로 축출**한다.
> 한 파드의 실수가 노드 전체를 망가뜨린다.
> **로그는 `stdout` 으로 내보낸다** — 그래야 로그 수집기가 회전·보존을 관리한다.

### `hugepages`

리눅스 기본 페이지는 **4 KiB** 다. 수십 GB 를 쓰는 프로그램이면 페이지가 수백만 개가 되어
주소 변환 캐시(TLB)가 계속 미스를 낸다. hugepage 는 그 단위를 **2 MiB 또는 1 GiB** 로 키운다.

| 쓰는 곳 | 이유 |
|---|---|
| DPDK 등 고성능 네트워킹 | 패킷 처리 지연 최소화 |
| 대형 DB (Oracle, PostgreSQL) | 버퍼 풀이 거대함 |
| JVM `-XX:+UseLargePages` | 큰 힙 |

**노드에서 미리 떼어놔야 한다.** 커널 부팅 옵션이나 `vm.nr_hugepages` 로 예약하는데,
**예약하는 순간 일반 메모리에서 빠진다.** 안 쓰면 낭비이므로 기본은 0이다.

```bash
grep -i huge /proc/meminfo
# HugePages_Total:  0        ← 예약된 것이 없다
# Hugepagesize:  2048 kB     ← 이 노드가 지원하는 크기
```

`Capacity` 부터 0이면 **선언 문제가 아니라 노드에 자원이 없는 것**이다.
`requests` 와 `limits` 가 **같아야 한다** — 고정 예약이라 오버커밋이 성립하지 않는다.

## `Capacity` 와 `Allocatable`

```
Capacity:     memory: 8130776Ki
Allocatable:  memory: 8028376Ki      ← 약 100 MiB 적다
```

차이만큼이 **kubelet 과 시스템 몫으로 예약**된 것이다.
파드가 쓸 수 있는 것은 `Allocatable` 까지다.

| kubelet 플래그 | 뜻 |
|---|---|
| `--system-reserved` | OS·sshd 등 시스템 몫 |
| `--kube-reserved` | kubelet·런타임 몫 |
| `--eviction-hard` | 이 선을 넘으면 파드를 축출 |

## QoS 클래스 — 축출 순서를 정하는 등급

### 왜 등급이 필요한가

배치가 끝난 뒤 **노드에서 실제로 메모리가 바닥나면** 누군가는 죽어야 한다.
CPU 는 나눠 쓰면 그만이지만 메모리는 이미 할당한 것을 뺏을 수 없다.

kubelet 은 노드를 감시하다 위험선(`--eviction-hard`)을 넘으면
`MemoryPressure` 를 선언하고 **파드를 골라 쫓아낸다.**
이것이 **축출(Eviction)** 이다 — 컨테이너 재시작이 아니라 파드가 노드에서 나간다.

```bash
kubectl get node <노드> -o jsonpath='{range .status.conditions[*]}{.type}{"="}{.status}{"\n"}{end}'
```

**문제는 순서다.** 그 순서를 정하는 것이 QoS 클래스다.

### 등급은 자동으로 정해진다

**직접 지정하지 않는다.** `requests` 와 `limits` 의 관계로 자동 결정된다.

| 클래스 | 조건 | 메모리 부족 시 |
|---|---|---|
| **`Guaranteed`** | 모든 컨테이너가 requests == limits (cpu·memory 둘 다) | **가장 나중에** 축출 |
| **`Burstable`** | requests 가 있고 limits 와 다름 | 중간 |
| **`BestEffort`** | **아무것도 없음** | **가장 먼저** 축출 |

```bash
kubectl get pod <파드> -o jsonpath='{.status.qosClass}'
```

**내가 지정하는 필드가 아니다.** API 서버가 계산해 `status.qosClass` 에 넣는다.

### 실측으로 확인한 규칙

파드를 만들어 직접 확인한 결과 (2026-09-11):

| 설정 | QoS | |
|---|---|---|
| `limits` **만** 지정 | **`Guaranteed`** | ← 의외 |
| `requests` == `limits` 명시 | `Guaranteed` | |
| 컨테이너 2개 중 **하나만** 설정 | `Burstable` | |
| cpu 만 같고 memory 는 다름 | `Burstable` | |
| **`ephemeral-storage` 만** 선언 | **`BestEffort`** | ← 의외 |

#### `limits` 만 줘도 `Guaranteed` 가 된다

```yaml
resources:
  limits: { cpu: 100m, memory: 64Mi }    # requests 를 안 적었다
```

```bash
kubectl get pod <파드> -o jsonpath='{.spec.containers[0].resources}'
```
```json
{"limits":{"cpu":"100m","memory":"64Mi"},
 "requests":{"cpu":"100m","memory":"64Mi"}}    ← 채워져 있다
```

**API 서버가 `requests` 를 `limits` 값으로 자동으로 채운다.**
결과적으로 같아지므로 `Guaranteed` 가 된다.

**반대는 성립하지 않는다.** `requests` 만 주면 `limits` 는 비어 있어 `Burstable` 이다.

#### `ephemeral-storage` 는 QoS 에 영향이 없다

`requests` 를 분명히 선언했는데도 `BestEffort` 였다.

**QoS 계산은 `cpu` 와 `memory` 만 본다.**
`ephemeral-storage` 와 `hugepages` 는 자원으로 관리되지만 등급에는 반영되지 않는다.

#### 파드 단위다 — 컨테이너 하나가 전체를 떨어뜨린다

```yaml
containers:
  - name: app                                  # requests == limits
    resources: { requests: {...}, limits: {...} }
  - name: sidecar                              # 아무것도 없음
```
→ 파드 전체가 **`Burstable`**

> **사이드카를 붙일 때 자주 걸린다.** 앱 컨테이너는 잘 맞춰놓고
> 사이드카에 아무것도 안 적어서 `Guaranteed` 가 깨지는 식이다.
> 로그 수집기·프록시를 주입하는 메시 환경에서 특히 그렇다.

`initContainer` 도 계산에 들어간다 —
파드의 유효 requests 는 `max(일반 컨테이너 합, initContainer 최댓값)` 이다.

#### 바꿀 수 없다

파드 생성 시점에 정해져 `status.qosClass` 에 박힌다.
등급을 바꾸려면 **파드를 다시 만들어야 한다.**

### cgroup 경로에도 드러난다

```
/sys/fs/cgroup/kubepods.slice/kubepods-besteffort.slice/...
/sys/fs/cgroup/kubepods.slice/kubepods-burstable.slice/...
/sys/fs/cgroup/kubepods.slice/...                        ← Guaranteed
```

**순서에 이유가 있다.**

- `Guaranteed` 는 "정확히 이만큼만 쓰겠다"고 선언하고 지키는 파드다.
  노드가 부족해진 것이 이 파드 탓이 아니므로 **보호한다.**
- `BestEffort` 는 아무 약속도 하지 않았다. 얼마든지 써도 되는 대신
  **문제가 생기면 먼저 정리된다.**

> 선언하지 않는다는 것은 자유를 얻는 대신 보호를 포기하는 것이다.

**DB 는 `Guaranteed`, 배치는 `BestEffort`** 로 두는 것이 기본 전략이다.

## 실무에서

```yaml
resources:
  requests:            # 스케줄러가 자리를 잡는 기준
    cpu: 100m
    memory: 128Mi
  limits:              # 폭주를 막는 안전장치
    memory: 256Mi
```

**`requests` 를 안 적는 것은 사실상 버그**로 취급한다.

| 강제하는 방법 | 하는 일 |
|---|---|
| `LimitRange` | 네임스페이스에 **기본값**을 넣어준다. 안 적으면 자동 주입 |
| `ResourceQuota` | 네임스페이스 총량 제한. **requests 없는 파드를 거부**할 수도 있다 |

```bash
kubectl describe limitrange -n <네임스페이스>
kubectl describe resourcequota -n <네임스페이스>
```

> **HPA 도 `requests` 가 있어야 동작한다.** `--cpu-percent=70` 의 기준이
> 실제 코어 수가 아니라 **`requests` 대비 백분율**이기 때문이다.
> `requests` 가 없으면 `<unknown>` 만 나온다.

## 진단

| 증상 | 확인 |
|---|---|
| 파드가 `Pending` | `describe pod` 의 `Insufficient cpu/memory` |
| `OOMKilled` | `limits.memory` 가 너무 작거나 앱이 새는 것 |
| 파드가 `Evicted` | 노드 `DiskPressure`/`MemoryPressure`. QoS 가 BestEffort 인가 |
| 앱이 느린데 CPU 여유 있음 | **`limits.cpu` 스로틀링** — `container_cpu_cfs_throttled_seconds` |
| 노드는 한가한데 배치 안 됨 | `requests` 합이 이미 `Allocatable` 을 채운 것 |

```bash
kubectl describe node <노드> | grep -A8 "Allocated resources"
kubectl get pods -A -o custom-columns=\
'NS:.metadata.namespace,POD:.metadata.name,QOS:.status.qosClass,CPU:.spec.containers[*].resources.requests.cpu'
```

## 관련

- 스케줄러가 `requests` 를 어떻게 쓰나 → [`scheduler.md`](scheduler.md)
- cgroup 을 누가 관리하나 → [`container-runtime.md`](container-runtime.md)
- 실습 → [Stage 3](../../docs/stages/stage-03-multi-node.md) · [Stage 7](../../docs/stages/stage-07-scheduling-ops.md)

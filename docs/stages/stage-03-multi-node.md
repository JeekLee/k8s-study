# Stage 3 — 다중 노드 (호스트 내부)

| | |
|---|---|
| 대상 | VM `k2-cp1` + `k2-w1` + `k2-w2` (전부 k8s-2 안) |
| 예상 소요 | 하루 |
| 선행 | [Stage 2](stage-02-first-cluster.md) |
| 기록할 곳 | `labs/stage-03-multi-node.md` |

## 이 단계에서 하는 일

**파드가 노드를 넘나드는 것을 눈으로 확인한다.**

아직 k8s-2 안이라 네트워크는 저절로 된다.
**스케줄러가 어떻게 배치를 결정하는지 관찰하는 것이 핵심**이고,
이것이 CKA Workloads & Scheduling(배점 15%)의 실습이 된다.

## 완료 기준

- [ ] 3노드가 모두 `Ready`
- [ ] 파드가 워커에 배치된다 (Stage 2에서 `Pending`이던 것이 이제 뜬다)
- [ ] `requests`의 유무가 스케줄링에 미치는 영향을 확인했다
- [ ] `podAntiAffinity`로 배치를 강제해봤다
- [ ] `drain`했을 때 파드가 다른 노드에서 재생성된다
- [ ] kubelet을 죽여 `NotReady`를 만들고 복구했다

## 전제

- 워커 VM `k2-w1`(192.168.122.21), `k2-w2`(192.168.122.22)가 부팅되어 있다
- 세 VM 모두 `virsh list --all`에서 `running`

```bash
# 호스트에서
virsh list --all
```

---

## 1. 워커 노드 준비

워커에도 control plane과 **똑같은 준비**가 필요하다 —
커널 모듈, sysctl, containerd, kubeadm.

Stage 2에서 손으로 한 번 해봤으므로, 이번에는 스크립트로 묶는다.

> **왜 스크립트인가.** 두 번째부터는 학습이 아니라 노동이고 실수만 는다.
> 여러 줄을 터미널에 붙여넣다 명령이 유실되는 사고를 이미 겪었다.
> `curl`로 받아 실행하면 그 위험이 없다.
>
> **실행 전에 읽어볼 것.** 무엇을 하는지 모르고 돌리면
> Stage 2에서 익힌 의미가 사라진다.

각 워커에서:

```bash
ssh ubuntu@192.168.122.21          # 호스트에서

curl -sL https://raw.githubusercontent.com/JeekLee/k8s-study/main/scripts/prep-node.sh -o prep-node.sh
less prep-node.sh                  # 읽어본다
sudo bash prep-node.sh
```

`k2-w2`(192.168.122.22)에도 동일하게.

스크립트가 하는 일은 [`scripts/prep-node.sh`](../../scripts/prep-node.sh) 참고.
Stage 2의 2~4절과 같다. 다만 **워커에는 `kubectl`을 설치하지 않는다** —
관리 명령은 control plane이나 맥에서 친다.

### 확인

```bash
containerd --version
grep SystemdCgroup /etc/containerd/config.toml
kubeadm version -o short
systemctl is-active containerd
```

---

## 2. join 토큰

`kubeadm init`이 출력한 토큰은 **기본 24시간 뒤 만료**된다.
지났다면 재발급한다 — 어차피 CKA에 나오는 명령이다.

**control plane(`k2-cp1`)에서:**

```bash
kubeadm token list                          # 남은 시간 확인

kubeadm token create --print-join-command
# kubeadm join 192.168.122.1:6443 --token <토큰> \
#   --discovery-token-ca-cert-hash sha256:<해시>
```

`--print-join-command`가 편하다. 토큰 생성과 CA 해시 계산을 한 번에 해준다.

> 해시를 직접 구하려면:
> ```bash
> openssl x509 -pubkey -in /etc/kubernetes/pki/ca.crt \
>   | openssl rsa -pubin -outform der 2>/dev/null \
>   | openssl dgst -sha256 -hex | sed 's/^.* //'
> ```
> **CA 해시는 왜 필요한가.** 워커가 엔드포인트에 접속했을 때
> **그것이 진짜 우리 클러스터인지** 확인하기 위해서다.
> 토큰은 "내가 들어갈 자격이 있다"를, 해시는 "네가 맞는 상대다"를 증명한다.
> 양방향 인증이다.

---

## 3. `kubeadm join`

**각 워커에서** 실행한다.

```bash
sudo kubeadm join 192.168.122.1:6443 --token <토큰> \
  --discovery-token-ca-cert-hash sha256:<해시>
```

출력에서 볼 것:

```
[preflight] Running pre-flight checks
[preflight] Reading configuration from the "kubeadm-config" ConfigMap
[kubelet-start] Starting the kubelet
[kubelet-check] The kubelet is healthy after ...
This node has joined the cluster
```

**설정을 클러스터에서 받아온다.** `kubeadm-config` ConfigMap과
`kubelet-config`를 읽으므로, 워커에서 파드 CIDR 같은 값을 다시 줄 필요가 없다.

> 여기서 워커는 **엔드포인트(`192.168.122.1:6443`)로 접속**한다.
> Stage 2의 [INPUT 방화벽 규칙](stage-02-first-cluster.md)이 없으면 이 단계에서 막힌다.

### 확인

```bash
# control plane 에서
kubectl get nodes
# NAME     STATUS   ROLES           AGE   VERSION
# k2-cp1   Ready    control-plane   1h    v1.35.8
# k2-w1    Ready    <none>          1m    v1.35.8
# k2-w2    Ready    <none>          1m    v1.35.8
```

`Ready`가 되기까지 30초~1분 걸린다. **Calico가 새 노드에 자동으로 배포**되기 때문이다.

```bash
kubectl get pods -n calico-system -o wide
# calico-node 가 노드마다 하나씩 (DaemonSet)
```

`ROLES`가 `<none>`인 것은 정상이다. 워커 역할 라벨은 kubeadm이 붙이지 않는다.
보기 좋게 하려면:

```bash
kubectl label node k2-w1 node-role.kubernetes.io/worker=
kubectl label node k2-w2 node-role.kubernetes.io/worker=
```

---

## 4. 스케줄러 관찰 — 이 단계의 핵심

### 4-1. Stage 2에서 `Pending`이던 파드가 이제 뜬다

```bash
kubectl run no-tol --image=nginx
kubectl get pod no-tol -o wide
# NAME     READY   STATUS    NODE
# no-tol   1/1     Running   k2-w1        ← 워커에 배치됐다
```

control plane의 taint는 그대로인데 **이제 갈 곳이 생겼다.**
Stage 2에서 `untolerated taint`로 `Pending`이던 그 파드다.

```bash
kubectl delete pod no-tol
```

### 4-2. replica를 늘려 분산 관찰

```bash
kubectl create deployment web --image=nginx --replicas=6
kubectl get pods -o wide
```

`NODE` 열을 본다. 두 워커에 나뉘어 배치될 것이다.

> 쿠버네티스에는 **기본 topology spread 제약**이 있어서
> 같은 Deployment 의 파드를 노드에 어느 정도 흩뿌린다
> (`maxSkew: 3`, `whenUnsatisfiable: ScheduleAnyway`).
> 완벽히 균등하지는 않다 — **권고이지 강제가 아니기 때문**이다.

### 4-3. `requests`가 하는 일

```bash
kubectl describe node k2-w1 | grep -A8 "Allocated resources"
```

```
Resource   Requests    Limits
cpu        150m (3%)   0 (0%)
memory     50Mi (0%)   0 (0%)
```

**`requests` 합계만 나온다.** 실제 사용량이 아니다.

`kubectl create deployment`로 만든 파드에는 `requests`가 없으므로
**스케줄러 입장에서 이 파드들은 자원을 0 쓰는 것으로 보인다.**
노드가 실제로 꽉 차도 계속 배치한다.

`requests`를 준 파드로 확인:

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

kubectl describe node k2-w1 | grep -A8 "Allocated resources"   # 숫자가 올라간다
```

### 4-4. 자원이 모자라면 `Pending`

워커는 4 vCPU 다. 감당 못 할 요청을 해본다.

```bash
kubectl run huge --image=nginx --overrides='
{"spec":{"containers":[{"name":"nginx","image":"nginx",
"resources":{"requests":{"cpu":"8"}}}]}}'

kubectl get pod huge
# NAME   READY   STATUS    AGE
# huge   0/1     Pending

kubectl describe pod huge | tail -5
# Warning  FailedScheduling  0/3 nodes are available:
#          1 node(s) had untolerated taint(s),
#          2 Insufficient cpu
```

**메시지가 노드별 탈락 이유를 알려준다.** control plane 은 taint 로,
워커 둘은 CPU 부족으로 탈락했다. 진단할 때 이 메시지를 읽는 습관이 중요하다.

```bash
kubectl delete pod huge
```

### 4-5. `podAntiAffinity` — 배치 강제

같은 앱의 파드를 **같은 노드에 두지 않도록** 강제한다.

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
```

**워커가 2대인데 replica 가 3이므로 하나는 `Pending`이 된다.**

```bash
kubectl describe pod -l app=spread | grep -A3 Events | tail -5
# didn't match pod anti-affinity rules
```

| 옵션 | 뜻 |
|---|---|
| `requiredDuringScheduling...` | **강제.** 만족 못 하면 `Pending` |
| `preferredDuringScheduling...` | 권고. 만족 못 해도 배치는 된다 |
| `topologyKey` | 무엇을 "같은 곳"으로 볼지. `hostname`이면 노드 단위 |

`required`를 `preferred`로 바꿔 다시 해보면 세 번째도 배치된다. **직접 확인해볼 것.**

### 4-6. `topologySpreadConstraints`

anti-affinity 보다 세밀하게 "얼마나 치우쳐도 되는가"를 정한다.

```yaml
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: kubernetes.io/hostname
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels: { app: spread }
```

`maxSkew: 1`은 노드 간 파드 수 차이가 1을 넘지 않게 한다.
`DoNotSchedule`이면 강제, `ScheduleAnyway`면 권고다.

---

## 5. `cordon` · `drain` · `uncordon`

노드를 점검하거나 업그레이드할 때 쓴다. **CKA 단골이다.**

```bash
kubectl create deployment web --image=nginx --replicas=4    # 없으면 만들고
kubectl get pods -o wide
```

### cordon — 새 파드만 막는다

```bash
kubectl cordon k2-w1
kubectl get nodes
# k2-w1   Ready,SchedulingDisabled   <none>
```

**기존 파드는 그대로 있다.** 새로 배치되는 것만 피해간다.

### drain — 파드를 비운다

```bash
kubectl drain k2-w1 --ignore-daemonsets
```

| 옵션 | 왜 필요한가 |
|---|---|
| `--ignore-daemonsets` | `calico-node`, `kube-proxy` 는 DaemonSet 이라 옮길 수 없다. 없으면 오류 |
| `--delete-emptydir-data` | `emptyDir` 볼륨을 쓰는 파드가 있으면 필요 |
| `--force` | ReplicaSet 등에 속하지 않은 단독 파드가 있으면 필요 (지워진다) |

```bash
kubectl get pods -o wide          # k2-w1 의 파드가 k2-w2 로 옮겨갔다
kubectl get nodes                 # k2-w1 은 SchedulingDisabled 유지
```

> **`drain`은 `cordon`을 포함한다.** 비우기만 하고 다시 받으면 의미가 없으니까.

### uncordon — 되돌린다

```bash
kubectl uncordon k2-w1
kubectl get nodes                 # Ready 로 복귀
```

**이미 옮겨간 파드는 돌아오지 않는다.** 스케줄러는 되돌리지 않는다.
새로 만들어지는 파드부터 다시 배치된다.

---

## 6. 노드 장애 시뮬레이션

**Stage 6 고장 훈련의 예고편이다.** 스냅샷을 먼저 찍어두면 마음이 편하다.

```bash
# 워커에서
sudo systemctl stop kubelet
```

```bash
# control plane 에서 관찰
kubectl get nodes -w
```

| 경과 | 일어나는 일 |
|---|---|
| ~40초 | 노드가 `NotReady` (`node-monitor-grace-period`) |
| 그 즉시 | 노드에 `node.kubernetes.io/unreachable:NoExecute` taint |
| ~5분 뒤 | 파드가 축출된다 (기본 `tolerationSeconds: 300`) |

```bash
kubectl describe node k2-w1 | grep -A3 Taints
kubectl get pods -o wide -w
```

**파드는 바로 옮겨가지 않는다.** 일시적인 네트워크 문제일 수도 있으므로
5분을 기다린다. 이 지연이 `tolerationSeconds`고, 파드마다 조정할 수 있다.

복구:

```bash
# 워커에서
sudo systemctl start kubelet
```

```bash
kubectl get nodes                 # 다시 Ready
```

> **`NotReady`를 봤을 때 확인 순서**
> 1. 노드에서 `systemctl status kubelet`
> 2. `journalctl -u kubelet -e --no-pager | tail -30`
> 3. `systemctl status containerd`
> 4. 엔드포인트에 닿는가 — `nc -vz -w3 192.168.122.1 6443`

---

## 7. 검증과 스냅샷

```bash
kubectl get nodes -o wide         # 3노드 Ready, INTERNAL-IP 가 .11/.21/.22
kubectl get pods -A -o wide       # calico-node 가 노드마다 하나씩
kubectl top nodes                 # metrics-server 가 있다면
```

정리:

```bash
kubectl delete deployment web sized spread --ignore-not-found
```

스냅샷 — **세 VM 모두, 한 줄씩**:

```bash
# 호스트에서
for vm in k2-cp1 k2-w1 k2-w2; do virsh shutdown $vm; done

virsh list --all          # ← 셋 다 "shut off" 가 될 때까지 기다린다

for vm in k2-cp1 k2-w1 k2-w2; do
  virsh snapshot-create-as $vm --name stage3-done --description "3노드 클러스터"
done

for vm in k2-cp1 k2-w1 k2-w2; do virsh start $vm; done
```

> ⚠️ **`virsh shutdown`은 비동기다.** `shut off` 확인 없이 다음 줄로 가면
> 실행 중 스냅샷이 찍히고 `start`가 `already active`로 실패한다.
>
> ⚠️ **클러스터 스냅샷은 세 VM 을 함께 찍어야 의미가 있다.**
> 하나만 되돌리면 etcd 의 상태와 노드의 실제 상태가 어긋난다.

---

## 완료 후

- [`labs/`](../../labs/)에 기록
- 다음: [Stage 4 — 크로스 호스트 라우팅](stage-04-cross-host.md)
  여기서 처음으로 **k8s-1이 등장**하고, Stage 0에서 이월된 UDP 51820 검증을 한다

## 자주 막히는 곳

| 증상 | 확인 |
|---|---|
| `kubeadm join`이 타임아웃 | 엔드포인트 도달 확인 — `nc -vz -w3 192.168.122.1 6443` |
| 토큰 만료 | `kubeadm token create --print-join-command` |
| join 후 노드가 `NotReady` | `kubectl get pods -n calico-system -o wide` — 그 노드의 `calico-node` 상태 |
| `drain`이 거부됨 | `--ignore-daemonsets`, `--delete-emptydir-data` |
| 파드가 계속 `Pending` | `kubectl describe pod` 의 `FailedScheduling` 메시지를 끝까지 읽을 것 |
| 노드 이름이 IP 로 나옴 | cloud-init 의 `hostname` 설정 확인 |

관련: [`notes/kubernetes/cni.md`](../../notes/kubernetes/cni.md) ·
[`notes/network/diagnosis/`](../../notes/network/diagnosis/)

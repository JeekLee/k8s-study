# Stage 3 — 다중 노드 (호스트 내부)

| | |
|---|---|
| 대상 | k8s-2의 VM 3대 |
| 예상 소요 | 하루 |
| 선행 | [Stage 2](stage-02-first-cluster.md) |
| 기록할 곳 | `labs/stage-03-multi-node.md` |

> 📝 계획 수준. 진입 시 확장한다.

## 목표

파드가 노드를 넘나드는 것을 눈으로 확인한다.
아직 k8s-2 안이라 네트워크는 저절로 된다 — **스케줄러 관찰이 핵심.**

## 완료 기준

- [ ] 3노드가 `Ready`
- [ ] 한 워커를 `drain`했을 때 파드가 다른 노드에서 재생성된다

## 할 일

- `kubeadm join` — 토큰과 CA 해시가 무엇인지, 만료되면 재발급하는 법
- Deployment 여러 개를 replica 2~3으로 띄우고 `kubectl get pods -o wide`로 분산 관찰
- **`requests`를 안 적었을 때 한쪽에 몰리는 현상 재현** — 실무에서 가장 흔한 사고
- `topologySpreadConstraints`, `podAntiAffinity`로 분산 강제
- `cordon` → `drain` → `uncordon`
- 워커에서 kubelet을 죽여 `NotReady`를 만들고 복구

다음: [Stage 4 — 크로스 호스트 라우팅](stage-04-cross-host.md)

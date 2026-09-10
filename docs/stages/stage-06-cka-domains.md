# Stage 6 — CKA 영역별 실습

| | |
|---|---|
| 예상 소요 | 3–5주 |
| 선행 | [Stage 5](stage-05-ha.md) |
| 기록할 곳 | [`labs/drills/`](../../labs/drills/) |

> 📝 계획 수준. 진입 시 확장한다.

## 목표

시험 범위를 클러스터 위에서 전부 손으로 해본다.

Stage 1–5를 지나면 Cluster Architecture 영역(25%)은 이미 상당 부분 몸에 남아 있다.
남은 것을 **배점 순**으로 채운다.

| 영역 | 배점 | 할 것 |
|---|---:|---|
| **Troubleshooting** | 30% | kubelet 정지, 인증서 만료 조작, CNI 훼손, wg0 다운, etcd 복구.<br>**스냅샷을 찍고 마음껏 부순다** — Stage 1의 존재 이유 |
| Cluster Architecture, Install & Config | 25% | 대부분 완료. 추가로 RBAC, `kubeadm upgrade`, Helm·Kustomize, CRD·오퍼레이터 |
| Services & Networking | 20% | Calico NetworkPolicy, CoreDNS, Ingress, Gateway API |
| Workloads & Scheduling | 15% | Stage 3에서 시작한 것을 심화. taint/toleration, affinity, HPA |
| Storage | 10% | StorageClass, PV/PVC, 동적 프로비저닝 |

훈련 목록은 [`labs/drills/README.md`](../../labs/drills/README.md)에 20여 개 준비해뒀다.
**시간을 재고** 기록한다.

## 완료 기준

- [ ] 각 영역의 대표 작업을 문서 없이 수행할 수 있다
- [ ] 막힌 것이 `labs/`에 기록되어 있다

다음: [Stage 7 — 시험 대비 마무리](stage-07-exam-prep.md)

# k8s-study

CKA 대비용 kubeadm 클러스터를 직접 설계·구축하며 학습하는 저장소.

## 진행 현황

| Stage | 내용 | 상태 |
|---|---|---|
| 0 | [기반 개념과 진단 도구](docs/stages/stage-00-baseline.md) | ✅ 완료 |
| 1 | [가상화 기반](docs/stages/stage-01-virtualization.md) — libvirt, VM 3대, 스냅샷 | ✅ 완료 |
| 2 | [첫 클러스터](docs/stages/stage-02-first-cluster.md) — 단일 노드 + HAProxy | ✅ 완료 |
| 3 | [다중 노드](docs/stages/stage-03-multi-node.md) — 호스트 내부 | 🔄 진행 중 |
| 4 | [워크로드와 서비스](docs/stages/stage-04-workloads.md) — 이미지·Deployment·Service·Ingress | ⬜ |
| 5 | [데이터 계층](docs/stages/stage-05-data-layer.md) — StatefulSet·PVC·NetworkPolicy | ⬜ |
| 6 | [이벤트 기반 MSA](docs/stages/stage-06-event-driven.md) — Kafka·saga·보상 | ⬜ |
| 7 | [스케줄링과 운영](docs/stages/stage-07-scheduling-ops.md) — HPA·PDB·priority | ⬜ |
| 8 | [크로스 호스트 라우팅](docs/stages/stage-08-cross-host.md) — WireGuard | ⬜ |
| 9 | [HA control plane](docs/stages/stage-09-ha.md) — 6노드 완성 | ⬜ |
| 10 | [CKA 영역별 실습](docs/stages/stage-10-cka-domains.md) | ⬜ |
| 11 | [시험 대비 마무리](docs/stages/stage-11-exam-prep.md) | ⬜ |

전체 계획: [docs/02-roadmap.md](docs/02-roadmap.md)

**목표 구성** — 6노드 (control plane 3 + worker 3), Kubernetes v1.35 · containerd 2.2 · Calico.
호스트 2대는 하이퍼바이저 역할만 하고 클러스터에 참여하지 않는다.

## 디렉토리 구성

성격이 다른 셋으로 나눈다. **`docs/`는 앞으로 할 것, `notes/`는 항상 참인 것, `labs/`는 실제로 한 것.**

```
docs/                        설계와 계획
  00-plan.md                   사전 점검 결과와 설계 결정
  01-network-design.md         네트워크 설계
  02-roadmap.md                학습 로드맵 개요
  stages/                      단계별 실행 절차 (stage-00 ~ 11)

notes/                       개념과 참고 자료
  network/
    concepts/                  VCN, 노드 주소 문제, 인터페이스
    diagnosis/                 ping · nc · tcpdump · ss · wg
    reference/                 WireGuard, 중첩 VM
  kubernetes/                  etcd
  infra/                       libvirt/KVM, HAProxy, NAT·iptables

labs/                        실습 결과
  stage-NN-주제.md             Stage별 수행 기록
  incidents/                   예기치 않게 겪은 문제
  drills/                      의도적 고장 → 복구 훈련

apps/                        데모 애플리케이션 — 주문 사가
  README.md                    도메인 설계와 이벤트 계약
  inventory/                   FastAPI · 재고
  manifests/                   쿠버네티스 매니페스트

scripts/                     반복 작업 스크립트
  prep-node.sh                 노드 준비 (모듈·sysctl·containerd·kubeadm)
```

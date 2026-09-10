# k8s-study

CKA 대비용 kubeadm 클러스터를 직접 설계·구축하며 학습하는 저장소.

## 진행 현황

| Stage | 내용 | 상태 |
|---|---|---|
| 0 | [기반 개념과 진단 도구](docs/stages/stage-00-baseline.md) | ✅ 완료 |
| 1 | [가상화 기반](docs/stages/stage-01-virtualization.md) — libvirt, VM 3대, 스냅샷 | ✅ 완료 |
| 2 | [첫 클러스터](docs/stages/stage-02-first-cluster.md) — 단일 노드 + HAProxy | ⬜ **진행 예정** |
| 3 | [다중 노드](docs/stages/stage-03-multi-node.md) — 호스트 내부 | ⬜ |
| 4 | [크로스 호스트 라우팅](docs/stages/stage-04-cross-host.md) — WireGuard | ⬜ |
| 5 | [HA control plane](docs/stages/stage-05-ha.md) — 6노드 완성 | ⬜ |
| 6 | [CKA 영역별 실습](docs/stages/stage-06-cka-domains.md) | ⬜ |
| 7 | [시험 대비 마무리](docs/stages/stage-07-exam-prep.md) | ⬜ |

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
  stages/                      단계별 실행 절차 (stage-00 ~ 07)

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
```

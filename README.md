# k8s-study

CKA(Certified Kubernetes Administrator) 대비용 kubeadm 클러스터를 **직접 설계하고 구축하며** 학습하는 저장소.

단순히 설치 명령을 따라치는 것이 목적이 아니다. 네트워크 설계부터 스스로 판단하고, 그 판단의 근거를 문서로 남긴다.

> 📎 **문서의 공인 IP는 실제 값이 아니다.** [RFC 5737](https://datatracker.ietf.org/doc/html/rfc5737)
> 문서화 전용 대역(`203.0.113.11`, `198.51.100.22`)으로 치환해 두었다.
> 실제 주소는 `docs/hosts.local.md`에 두고 `.gitignore`로 제외한다.
> 사설 대역(`10.0.0.0/24`)은 VCN 밖에서 의미가 없고 이 저장소의 핵심 학습 소재라 그대로 둔다.

## 목표

- **1차** — 2노드 kubeadm 클러스터를 스스로 설계·구축한다
- **2차** — CKA 시험 5개 영역을 이 클러스터에서 실습한다
- **3차** — 고장 → 진단 → 복구를 반복해 Troubleshooting(배점 30%) 근육을 만든다

## 대상 환경

| | k8s-1 | k8s-2 |
|---|---|---|
| 역할 | 하이퍼바이저 (VM 3대) | 하이퍼바이저 (VM 3대) |
| CPU / RAM | 16 vCPU / 125 GiB | 32 vCPU / 251 GiB |
| 디스크 | 3.8 TB | 3.8 TB |
| OS / 커널 | Ubuntu 26.04 LTS / 7.0.0-1009-oracle | 동일 |
| 클라우드 | OCI (KVM) | OCI (KVM) |

최종 구성: **6노드** (control plane 3 + worker 3). 두 호스트는 클러스터에 참여하지 않고 VM만 띄운다.
버전 고정: **Kubernetes v1.35** (CKA 시험 기준) · containerd 2.2.2 · Calico

## 진행 상황

전체 계획은 [docs/02-roadmap.md](docs/02-roadmap.md).

- [x] **Stage 0** — 기반 개념과 진단 도구
- [ ] **Stage 1** — 가상화 기반 (libvirt, 스냅샷) ← **다음**
- [ ] **Stage 2** — 첫 클러스터 (단일 노드)
- [ ] **Stage 3** — 다중 노드 (호스트 내부)
- [ ] **Stage 4** — 크로스 호스트 라우팅 (WireGuard)
- [ ] **Stage 5** — HA control plane (6노드 완성)
- [ ] **Stage 6** — CKA 영역별 실습
- [ ] **Stage 7** — 시험 대비 마무리

## 구조

```
docs/     설계 문서 — 판단과 근거를 남기는 곳
  00-plan.md            사전 점검 결과와 설계 결정
  01-network-design.md  네트워크 설계
  02-roadmap.md         학습 로드맵 Stage 0~7
notes/    실습 기록과 참고 자료
  network/    VCN·주소 문제·진단 명령
  kubernetes/ 컴포넌트 (etcd)
  infra/      HAProxy, libvirt/KVM
```

## 원칙

1. **명령을 붙여넣기 전에 왜 그 값인지 적는다.** 특히 IP 대역과 포트.
2. **막힌 것은 지우지 않는다.** 실패 기록이 Troubleshooting 학습 자료다.
3. **자격증명은 커밋하지 않는다.** `.gitignore`를 먼저 확인할 것.
4. **공개 저장소다.** 실제 IP·호스트명·키는 문서화 전용 값으로 바꿔 적는다.

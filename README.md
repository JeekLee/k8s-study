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
| 역할 | control plane | worker |
| CPU / RAM | 16 vCPU / 125 GiB | 32 vCPU / 251 GiB |
| 디스크 | 3.8 TB | 3.8 TB |
| OS / 커널 | Ubuntu 26.04 LTS / 7.0.0-1009-oracle | 동일 |
| 클라우드 | OCI (KVM) | OCI (KVM) |

버전 고정: **Kubernetes v1.35** (CKA 시험 기준) · containerd 2.2.2 · Calico

## 진행 상황

- [ ] **Phase 0** — 네트워크 설계 및 노드 간 연결 → [docs/01-network-design.md](docs/01-network-design.md)
  - 🔍 연결 방식 **검토 중** (WireGuard / VCN 재생성 / 단일 노드+VM) → [검토 메모](notes/network/reference/wireguard.md#검토-메모)
- [ ] **Phase 1** — 컨테이너 런타임 · kubeadm 설치
- [ ] **Phase 2** — 클러스터 초기화 (`kubeadm init` / `join`)
- [ ] **Phase 3** — CNI 구성 (Calico) 및 통신 검증
- [ ] **Phase 4** — 실습 환경 확장 (중첩 VM으로 3노드 HA)
- [ ] **Phase 5** — CKA 영역별 실습 및 고장/복구 훈련

## 구조

```
docs/     설계 문서 — 판단과 근거를 남기는 곳
notes/    실습 기록 — 겪은 문제와 해결 과정
```

## 원칙

1. **명령을 붙여넣기 전에 왜 그 값인지 적는다.** 특히 IP 대역과 포트.
2. **막힌 것은 지우지 않는다.** 실패 기록이 Troubleshooting 학습 자료다.
3. **자격증명은 커밋하지 않는다.** `.gitignore`를 먼저 확인할 것.
4. **공개 저장소다.** 실제 IP·호스트명·키는 문서화 전용 값으로 바꿔 적는다.

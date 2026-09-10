# 전체 계획

## 사전 점검 결과 (2026-09-10 실측)

| 항목 | 상태 | 내용 |
|---|---|---|
| 노드 간 통신 | 🛑 **불가** | 양쪽 사설 대역이 모두 `10.0.0.0/24` — 서로 다른 VCN |
| 공인 IP 간 포트 | 🛑 22번만 | OCI 보안 목록이 나머지 차단 (`udp/51820` 테스트 결과 BLOCKED) |
| swap | ✅ | 0B — kubeadm 요구사항 충족 |
| 커널 모듈 | ✅ | `br_netfilter` · `overlay` · `nf_conntrack` 모두 사용 가능 |
| 패키지 | ✅ | containerd 2.2.2, wireguard 1.0.20250521 (Ubuntu repo) |
| kubeadm | ✅ | `1.35.0-1.1` — CKA 시험 버전과 일치 |
| 중첩 가상화 | ✅ | `/dev/kvm` 존재 → k8s-2 위에 VM 클러스터 구성 가능 |
| sudo | ✅ | 양쪽 NOPASSWD |
| OS 조합 | ⚠️ | Ubuntu 26.04 / kernel 7.0 은 kubeadm 검증 대상 밖 |

## 단계

| Phase | 내용 | 산출물 |
|---|---|---|
| 0 | 네트워크 설계 — 노드 간 통신 확보 🔍 *방식 검토 중* | `01-network-design.md` |
| 1 | containerd + kubeadm 설치 (양쪽 공통) | |
| 2 | `kubeadm init` / `join` | |
| 3 | Calico 구성 및 파드 간 통신 검증 | |
| 4 | 중첩 VM으로 3노드 HA 실습 환경 | |
| 5 | CKA 영역별 실습 · 고장/복구 훈련 | `notes/` |

## CKA 배점과 학습 시간 배분

배점이 곧 시간 배분이다. Troubleshooting이 단일 최대 영역인데, 이건 읽어서 늘지 않고 직접 망가뜨려야 는다.

| 영역 | 배점 | 이 클러스터에서 할 것 |
|---|---|---|
| Troubleshooting | **30%** | kubelet 정지, 인증서 만료 조작, CNI 훼손, wg0 다운, etcd 스냅샷 복구 |
| Cluster Architecture, Installation & Config | 25% | Phase 0–3 자체 + RBAC, `kubeadm upgrade`, Helm/Kustomize, CRD·오퍼레이터 |
| Services & Networking | 20% | NetworkPolicy, CoreDNS, Ingress, Gateway API |
| Workloads & Scheduling | 15% | taint/toleration, affinity, HPA |
| Storage | 10% | StorageClass, PV/PVC, 동적 프로비저닝 |

## 설계 결정 요약

| 결정 | 값 | 근거 |
|---|---|---|
| control plane | k8s-1 (16C/125G) | 워크로드는 워커가 진다. control plane은 노드/오브젝트 수에 비례할 뿐 |
| worker | k8s-2 (32C/251G) | 큰 쪽을 워커로 |
| control plane 수 | **1대** | etcd 쿼럼 `(N/2)+1` — 2대는 장애 허용 0. 단일보다 나쁘다. HA는 3대부터 |
| control plane taint | **유지** | 제거하면 편하지만, 남겨둬야 toleration·affinity 실습 재료가 된다 |
| CNI | **Calico** | Flannel은 NetworkPolicy 미지원. CKA 20% 영역이 통째로 빠진다 |
| 노드 간 연결 | 🔍 **미결** | WireGuard / 한쪽 VCN 재생성 / k8s-2 단독+VM 중 검토 중.<br>포트 전체 개방은 [주소 문제](../notes/network/concepts/02_node-addressing.md)로 제외됨 |
| 버전 | v1.35 고정 + `apt-mark hold` | 나중에 `kubeadm upgrade`를 *의도적으로* 연습하기 위해 |

## 미리 알고 갈 함정

- **`--node-ip` 누락** — 노드는 `Ready`로 붙는데 `logs`·`exec`·메트릭만 죽는다. apiserver가 잘못된 주소로 kubelet에 접속하기 때문.
- **containerd 2.x 설정 스키마는 version 3** — 인터넷의 옛날 `config.toml` 예제를 붙이면 런타임이 안 뜬다. 반드시 `containerd config default`로 생성 후 수정.
- **`SystemdCgroup = true`** — 빠뜨리면 kubelet이 조용히 실패한다.
- **6443을 `0.0.0.0/0`에 열지 말 것** — 스캐너에 즉시 잡힌다.
- **노드 시계** — 인증서 검증은 시간에 민감. `timedatectl` 동기화를 초기에 확인.
- **preflight 경고를 읽을 것** — Ubuntu 26.04는 검증 대상 밖이라 경고가 날 수 있다. 무시하기 전에 무엇에 대한 경고인지 확인하는 습관이 시험장에서도 필요하다.

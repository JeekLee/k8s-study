# 쿠버네티스 컴포넌트

클러스터 구성 요소별 정리.

| 문서 | 내용 |
|---|---|
| [`etcd.md`](etcd.md) | 클러스터의 유일한 데이터베이스. 쿼럼, 백업/복구, 크기 제한 |
| [`container-runtime.md`](container-runtime.md) | containerd와 CRI. 계층 구조, cgroup 드라이버, `crictl` |
| [`cni.md`](cni.md) | CNI 규약과 Calico. 파드 네트워킹, VXLAN이 필수인 이유, NetworkPolicy |
| [`scheduler.md`](scheduler.md) | 필터·점수 두 단계, 가중치, `requests`가 없을 때 무엇이 분산을 만드는가 |
| [`resources.md`](resources.md) | `requests`·`limits`의 차이, 자원 네 종류, QoS 클래스, `Allocatable` |

## 앞으로 채울 것

- `apiserver.md` — 인증·인가·어드미션, 모든 요청의 관문
- `kubelet.md` — 노드 에이전트, static pod, 노드 등록
- `controller-manager.md` — 조정 루프
- `kube-proxy.md` — Service 구현, iptables/IPVS

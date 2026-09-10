# 쿠버네티스 컴포넌트

클러스터 구성 요소별 정리.

| 문서 | 내용 |
|---|---|
| [`etcd.md`](etcd.md) | 클러스터의 유일한 데이터베이스. 쿼럼, 백업/복구, 크기 제한 |
| [`container-runtime.md`](container-runtime.md) | containerd와 CRI. 계층 구조, cgroup 드라이버, `crictl` |

## 앞으로 채울 것

- `apiserver.md` — 인증·인가·어드미션, 모든 요청의 관문
- `kubelet.md` — 노드 에이전트, static pod, 노드 등록
- `scheduler.md` — 배치 결정, affinity와 taint
- `controller-manager.md` — 조정 루프
- `kube-proxy.md` — Service 구현, iptables/IPVS

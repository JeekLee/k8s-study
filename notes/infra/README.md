# 인프라

쿠버네티스 자체는 아니지만 클러스터를 세우는 데 필요한 것들.

| 문서 | 내용 |
|---|---|
| [`libvirt-kvm.md`](libvirt-kvm.md) | VM 생성·관리. routed 네트워크가 필요한 이유, cloud-init, 스냅샷 |
| [`nat-iptables.md`](nat-iptables.md) | NAT 종류와 체인, iptables vs nftables, kube-proxy와의 연결 |
| [`haproxy.md`](haproxy.md) | control plane 앞단 로드밸런서. 단일 엔드포인트가 필요한 이유, `mode tcp` |

## 앞으로 채울 것

- `wireguard-setup.md` — 호스트 간 터널 실제 구성 (Stage 8)

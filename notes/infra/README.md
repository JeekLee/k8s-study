# 인프라

쿠버네티스 자체는 아니지만 클러스터를 세우는 데 필요한 것들.

| 문서 | 내용 |
|---|---|
| [`haproxy.md`](haproxy.md) | control plane 앞단 로드밸런서. 단일 엔드포인트가 필요한 이유, `mode tcp` |

## 앞으로 채울 것

- `libvirt-kvm.md` — VM 생성·관리, routed 네트워크, 스냅샷 (Stage 1)
- `cloud-init.md` — VM 초기 설정 자동화 (Stage 1)
- `wireguard-setup.md` — 호스트 간 터널 실제 구성 기록 (Stage 4)

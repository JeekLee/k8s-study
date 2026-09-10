# Stage 1 — 가상화 기반

| | |
|---|---|
| 일자 | (미시작) |
| 소요 | |
| 결과 | ⬜ 진행 전 |
| 대상 | k8s-2 (32 vCPU / 251 GiB) |

> 절차: [`docs/stages/stage-01-virtualization.md`](../docs/stages/stage-01-virtualization.md)
> 참고: [`notes/infra/libvirt-kvm.md`](../notes/infra/libvirt-kvm.md)

## 완료 기준

- [ ] `virsh list --all`이 동작한다
- [ ] VM이 부팅되고 SSH로 들어가진다
- [ ] libvirt 네트워크가 **routed 모드**, 대역은 `192.168.122.0/24`
- [ ] 스냅샷을 찍고 되돌렸을 때 변경이 사라진다

## 수행 기록

<!-- 실제로 친 명령과 출력을 여기에 -->

## 막힌 것

<!-- 증상 → 확인 → 원인 → 해결 -->

## 결과 확인

<!-- 완료 기준을 충족했다는 증거 -->

## 배운 것 / 다음에 다르게 할 것

---

## 미리 알고 있는 함정

- **`qemu-kvm` 패키지가 없다.** Ubuntu 26.04에서는 `qemu-system-x86`으로 바뀌었다
- `usermod -aG libvirt,kvm` 후 **재로그인**해야 그룹이 적용된다
- 기본 `default` 네트워크가 이미 `192.168.122.0/24`를 쓰고 있다. **먼저 치워야 한다**
- NAT이 아니라 **routed 모드**여야 한다. NAT은 출발지를 호스트 IP로 바꿔서
  Stage 0에서 겪은 주소 불일치가 재발한다
- routed만으로는 **VM이 인터넷에 못 나간다.** `ens3`로 나가는 트래픽에만 MASQUERADE를 건다
- VM OS는 **24.04 LTS**를 권한다. 호스트(26.04)와 달라도 되고 kubeadm 검증 범위 안이다

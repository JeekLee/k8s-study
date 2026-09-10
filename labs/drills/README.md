# 고장 복구 훈련

의도적으로 클러스터를 망가뜨리고 복구하는 기록.
**CKA Troubleshooting은 배점 30%로 단일 최대 영역**이고, 이건 읽어서 늘지 않는다.

## 전제 — 스냅샷

훈련 전에 반드시 스냅샷을 찍는다. 복구에 실패해도 몇 초면 돌아온다.
부수는 데 드는 심리적 비용이 0이 되어야 훈련이 반복된다.

```bash
virsh snapshot-create-as vm-cp1 before-drill
virsh snapshot-revert  vm-cp1 before-drill
```

## 훈련 목록

Stage 5 이후 하나씩 채운다. 각 항목은 **시간을 재고** 기록한다.

### 노드 레벨

- [ ] kubelet 정지 → `NotReady` 진단
- [ ] containerd 정지 → 파드가 안 뜨는 상황
- [ ] `SystemdCgroup = false`로 되돌리기 → kubelet이 조용히 실패하는 증상
- [ ] 디스크 가득 채우기 → `DiskPressure` taint
- [ ] 노드 시계 틀어놓기 → 인증서 검증 실패

### control plane

- [ ] apiserver static pod 매니페스트 훼손
- [ ] etcd 정지 → 쿼럼 상실
- [ ] **인증서 만료 조작** → `kubeadm certs check-expiration` → 갱신
- [ ] etcd 스냅샷에서 복구 (오브젝트를 지운 뒤)

### 네트워크

- [ ] `wg0` 다운 → 노드 간 분리
- [ ] MTU를 1500으로 되돌리기 → **큰 패킷만 멈추는** 증상 재현
- [ ] CoreDNS 정지 → 이름 해석 실패
- [ ] Calico 설정 훼손 → 파드 간 통신 두절
- [ ] NetworkPolicy로 실수로 전부 차단

### 워크로드

- [ ] `requests`를 과하게 잡아 스케줄 불가 → `Pending` 진단
- [ ] 잘못된 이미지명 → `ImagePullBackOff`
- [ ] taint를 걸어놓고 toleration 없이 배포
- [ ] PVC가 바인딩 안 되는 상황

## 기록 형식

[`../README.md`](../README.md#템플릿--고장-복구-훈련-drills)의 템플릿을 쓴다.
**틀린 가설과 헛짚은 것을 반드시 포함**한다 — 그게 다음번의 지름길이다.

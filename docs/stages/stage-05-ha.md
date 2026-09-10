# Stage 5 — HA control plane

| | |
|---|---|
| 대상 | 6노드 완성 |
| 예상 소요 | 하루 |
| 선행 | [Stage 4](stage-04-cross-host.md) |
| 기록할 곳 | `labs/stage-05-ha.md` |

> 📝 계획 수준. 진입 시 확장한다.

## 목표

control plane 3대로 쿼럼을 만들고 **직접 깨뜨려본다.**

## 완료 기준

- [ ] 6노드가 `Ready`
- [ ] 쿼럼 실험 완료 (CP 1대 정지 → 생존 / 2대 정지 → 정지)
- [ ] etcd 스냅샷에서 클러스터를 복구해봤다

## 할 일

```bash
sudo kubeadm join <endpoint>:6443 --token ... \
  --discovery-token-ca-cert-hash ... \
  --control-plane --certificate-key ...
```

- etcd 멤버 확인 — `etcdctl member list`
- **쿼럼 실험** — 직접 죽여보고 확인
- etcd 스냅샷 백업 → 오브젝트 삭제 → 복구. **CKA 단골 문제**
- 인증서 만료일 확인과 갱신 — `kubeadm certs check-expiration`

## ⚠️ HA는 절반만 된다

호스트가 2개라 etcd 3멤버를 2+1로 나눌 수밖에 없다.

| 죽는 쪽 | 남는 멤버 | 쿼럼(2 필요) | 결과 |
|---|---|---|---|
| CP 1대가 있는 호스트 | 2 | ✅ | 생존 |
| CP 2대가 있는 호스트 | 1 | ❌ | **정지** |

진짜 HA는 장애 도메인이 3개여야 한다.
**이 한계를 직접 겪는 것이 쿼럼을 이해하는 가장 좋은 방법이다.**

다음: [Stage 6 — CKA 영역별 실습](stage-06-cka-domains.md)

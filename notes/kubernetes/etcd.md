# etcd — 클러스터의 유일한 데이터베이스

클러스터의 모든 상태가 저장되는 곳. `kubectl`로 만든 모든 것이 여기 들어간다.

## 정체 — 독립 소프트웨어다

- Go로 작성, 2013년 **CoreOS**가 개발 (쿠버네티스보다 먼저 나왔다)
- 현재 **CNCF 졸업 프로젝트**로 쿠버네티스와 별개로 운영된다
- MySQL·Postgres 같은 DBMS 위에 얹힌 것이 **아니다.** 합의 알고리즘부터 저장까지 자체 구현
- **쿠버네티스 전용도 아니다.** Cloud Foundry, Rook, M3 등에서도 쓴다

내부 저장 엔진으로 **bbolt**(Go로 된 임베디드 B+tree 라이브러리)를 쓴다.
다만 이건 DBMS가 아니라 SQLite처럼 프로세스에 링크되는 저장 라이브러리다.
클라이언트-서버 구조도, SQL도 없다.

> 실질적으로는 압도적으로 큰 사용처가 쿠버네티스라, etcd 개발 방향이
> 쿠버네티스 요구사항에 많이 끌려가는 것은 사실이다.

## 무엇이 저장되나

```
/registry/pods/default/nginx-7d8f...
/registry/secrets/default/db-password
/registry/minions/k8s-2              ← 노드 주소가 여기 저장됨
```

**etcd를 지우면 클러스터가 사라진다.** 노드도 컨테이너도 그대로 살아 있지만
쿠버네티스는 아무것도 기억하지 못한다.
반대로 스냅샷만 있으면 클러스터를 통째로 되살릴 수 있다.

## 접근 경로 — apiserver만 통한다

```
kubectl  ─┐
kubelet  ─┼─► apiserver ─► etcd
scheduler ┘
```

**etcd에 직접 말을 거는 것은 apiserver 하나뿐이다.**
kubelet도 scheduler도 controller-manager도 전부 apiserver를 거친다.

중요한 설계다. 인증·인가(RBAC), 유효성 검증, 어드미션 컨트롤이 apiserver 한 곳에서 걸린다.
각 컴포넌트가 etcd에 직접 쓴다면 그 검증을 전부 우회할 수 있다.

## 어디서 도나

kubeadm 클러스터에서는 control plane 노드의 **static pod**로 뜬다.

```bash
sudo ls /etc/kubernetes/manifests/     # etcd.yaml
kubectl -n kube-system get pods | grep etcd
```

static pod라 apiserver 없이 kubelet이 직접 띄운다.
당연하다 — etcd가 있어야 apiserver가 뜬다.

## 쿼럼 — control plane을 2대로 만들면 안 되는 이유

**Raft 합의 알고리즘**을 쓴다. 쓰기가 성공하려면 과반 `(N/2)+1`이 동의해야 한다.

| 멤버 수 | 쿼럼 | 견딜 수 있는 장애 |
|---|---|---|
| 1 | 1 | **0대** |
| **2** | **2** | **0대** ← 의미 없음 |
| 3 | 2 | 1대 |
| 4 | 3 | 1대 ← 3대와 같은데 비용만 증가 |
| 5 | 3 | 2대 |

**2대는 1대와 장애 허용이 같은데 고장날 지점만 두 배**다. 오히려 나빠진다.
짝수는 항상 손해라 3, 5처럼 홀수로 간다.

→ 이 프로젝트에서 control plane을 1대로 두고 HA는 Phase 4에서 VM으로 실습하는 이유.

## 디스크와 지연에 민감하다

쓰기를 확정할 때마다 **디스크에 fsync**한다. CPU·메모리보다 **디스크 지연**에 민감하다.
느린 디스크에서는 클러스터 전체가 느려진다.

HA 구성 시에는 **피어 간 네트워크 지연**도 같은 이유로 영향을 준다.
→ `ping`의 `mdev`(지연 흔들림)를 미리 측정해 둘 것. [`../network/diagnosis/01_ping.md`](../network/diagnosis/01_ping.md)

## 크기 제한이 만든 실제 제약

```
기본 DB 크기 한도      : 2 GiB (최대 8 GiB 권장)
단일 요청 크기 한도    : 1.5 MiB
→ ConfigMap / Secret  : 약 1 MiB
```

ConfigMap에 큰 파일을 못 넣는 이유가 여기 있다.
쿠버네티스의 임의 제한이 아니라 **etcd의 물리적 한계**다.
큰 데이터는 PV나 오브젝트 스토리지로 빼야 한다.

## ⚠️ Secret은 암호화되지 않는다

기본 설정에서 Secret은 etcd에 **base64 인코딩**으로만 들어간다.
인코딩은 암호화가 아니다 — 누구나 디코딩할 수 있다.

**etcd 파일에 접근할 수 있으면 클러스터의 모든 비밀을 갖게 된다.** 백업 파일도 마찬가지다.
→ `.gitignore`에 `*.db`를 넣어둔 이유.

운영에서는 EncryptionConfiguration으로 저장 시 암호화를 켠다. (CKS 시험 범위)

## 백업 / 복구 — CKA 단골 문제

```bash
sudo apt-get install -y etcd-client

# 백업
sudo ETCDCTL_API=3 etcdctl \
  --endpoints=https://127.0.0.1:2379 \
  --cacert=/etc/kubernetes/pki/etcd/ca.crt \
  --cert=/etc/kubernetes/pki/etcd/server.crt \
  --key=/etc/kubernetes/pki/etcd/server.key \
  snapshot save /opt/backup.db

# 확인
sudo ETCDCTL_API=3 etcdctl snapshot status /opt/backup.db --write-out=table

# 복구 (새 데이터 디렉터리로)
sudo ETCDCTL_API=3 etcdctl snapshot restore /opt/backup.db \
  --data-dir=/var/lib/etcd-restored
# 이후 /etc/kubernetes/manifests/etcd.yaml 의 hostPath를 바꾸고 kubelet이 재시작하도록 둔다
```

인증서 경로 세 개를 매번 주는 것이 번거롭다. **시험에서는 이걸 빠르게 치는 것도 점수다.**
Phase 2 이후 반복 연습할 항목.

## 대체할 수 있나 — 있다

apiserver는 저장소를 인터페이스 뒤에 추상화해뒀다. 그래서 갈아끼울 수 있다.

실제 사례가 **k3s**다. Rancher가 만든 **kine**이라는 shim이 etcd API를
SQLite·MySQL·Postgres로 번역한다.

```
apiserver ─► kine ─► SQLite / Postgres / MySQL
```

즉 **etcd는 필수가 아니라 기본값**이다.
다만 kubeadm 표준 클러스터는 etcd를 쓰고 **CKA도 etcd 기준**이라 이 프로젝트는 그대로 간다.

## 왜 하필 etcd였나

쿠버네티스가 저장소에 요구하는 것은 일반 DB와 상당히 다르다.

| 필요한 것 | 이유 |
|---|---|
| **강한 일관성** | 스케줄러가 오래된 값을 읽으면 같은 파드를 두 노드에 배치할 수 있다 |
| **Watch API** ⭐ | "이 키가 바뀌면 알려줘" — 컨트롤러 패턴의 핵심 |
| **CAS (조건부 쓰기)** | `resourceVersion` 기반 낙관적 동시성 제어 |
| **Lease / TTL** | 리더 선출, 노드 하트비트 |

**Watch가 결정적이다.** 모든 컨트롤러는 "현재 상태를 감시하다 원하는 상태와 다르면 조정"하는
루프로 돈다. Deployment의 replica를 바꾸면 즉시 반응하는 것이 폴링이 아니라 watch 덕분이다.

일반 RDBMS로는 이걸 못 한다. 폴링이나 트리거를 써야 하는데
수천 개 컨트롤러가 초당 폴링하면 감당이 안 된다.

반대로 쿠버네티스가 **필요로 하지 않는 것**도 많다 — 조인, 복잡한 쿼리, 대용량 저장.
RDBMS 기능 대부분이 낭비다.

| | etcd | RDBMS | Redis |
|---|---|---|---|
| 데이터 모델 | 키-값 (계층적 경로) | 관계형 테이블 | 키-값 + 자료구조 |
| 일관성 | 강함 (Raft) | 강함 (단일 노드) | 기본 최종 일관성 |
| Watch | ✅ 내장 | ❌ | 부분적 (Pub/Sub) |
| 용도 | **설정·메타데이터** | 업무 데이터 | 캐시 |
| 적정 크기 | 수 GB | TB급 | 메모리 크기 |

> etcd는 "많은 데이터를 담는 DB"가 아니라
> **"적은 데이터를 절대 잃지 않고, 변경을 즉시 알려주는 저장소"**다.

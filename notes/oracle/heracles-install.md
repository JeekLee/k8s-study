# HEracles 설치 — 무엇을 어디에 놓는가

[공식 Quick Start](https://cryptolab.gitbook.io/heracles/quick-start/oracle.md) 의
설치 스크립트를 분해하고, **쿠버네티스에 맞는 형태로 옮기는** 방법.

## 1. 스크립트가 실제로 하는 일

```bash
curl -fsSL https://heracles.heaan.land/artifacts/heracles/install.sh | \
  TARGET_CONTAINER=<컨테이너명> bash
```

`docker exec`·`docker cp`·`docker logs` 로 컨테이너 안에 작업한다.
작업을 성격별로 가르면 이렇게 된다.

| 작업 | root | 결과가 남는 곳 | k8s 에서 |
|---|---|---|---|
| `/opt/heracles` 디렉토리 생성 | ✅ | 파일시스템 | **이미지** |
| `libheracles.so` 배치 | ✅ | 파일시스템 | **이미지** |
| keygen 실행 → `secret.key`, `aes256.key` | ✅ | 파일시스템 | **Secret 주입** |
| `chown oracle:oinstall`, `chmod 640` | ✅ | 파일시스템 | **이미지** |
| OL7 용 yum 패키지 | ✅ | 파일시스템 | 이미지 (**OL8 이면 불필요**) |
| `extproc.ora` 작성 + `lsnrctl reload` | ❌ | 파일시스템 | **이미지** (리로드 불필요) |
| app user 생성 (`sqlplus as sysdba`) | ❌ | **DB = PVC** | **Job** |
| `install.sql` 실행 | ❌ | **DB = PVC** | **Job** |

### ⭐ docker 는 필수가 아니다

`docker exec -u 0` 이 7번 나오는데 **전부 `/opt/heracles` 준비 작업**이다.
Dockerfile 안에서는 기본이 root 라 그냥 된다.

`lsnrctl reload` 도 필요 없어진다 — `extproc.ora` 가 이미지에 들어 있으면
**리스너가 기동할 때 읽는다.**

런타임에 docker 가 필요한 지점은 없다. 이미지를 만들 때 OCI 빌더가 필요할 뿐이고,
그것도 podman·buildah·Actions 무엇이든 된다.

---

## 2. podman 으로 가는 이유

| | |
|---|---|
| **데몬이 없다** | 호스트에 상주 프로세스가 생기지 않는다 |
| **클러스터를 안 건드린다** | VM 의 containerd 와 완전히 별개다 |
| `podman-docker` | `docker` 명령을 제공해 **벤더 스크립트를 수정 없이** 쓸 수 있다 |
| **`podman commit`** | ⭐ 아래 참고 |

### ⭐ `commit` 이 경계를 대신 그어준다

```
podman commit  ──┬─▶ /opt/heracles (.so, extproc.ora)   ✅ 이미지에 들어감
                 └─▶ /opt/oracle/oradata (DB 객체)       ❌ 볼륨이라 제외
```

**commit 은 볼륨을 제외한다.** Oracle 이미지가 `oradata` 를 `VOLUME` 으로
선언해 두었으므로, 1절의 "파일시스템 / DB" 분리가 **저절로 이뤄진다.**

벤더 스크립트를 그대로 돌리고 commit 하면 우리가 원하는 이미지가 나온다.
**맨땅에서 Dockerfile 을 쓰면 무엇이 빠졌는지 알 방법이 없다.**

> commit 으로 만든 이미지는 레이어가 지저분하다.
> **동작을 확인하는 용도로 쓰고**, 내용물이 파악되면 Dockerfile 로 정리한다.

---

## 3. 절차 — k8s-2 호스트에서

호스트를 쓰는 이유: **amd64 네이티브** (맥은 arm64 라 에뮬레이션),
디스크 3.8 TB (VM 루트는 38 GB), 클러스터 VM 을 안 건드린다.

### 3-1. podman 설치

```bash
# 📍 k8s-2 호스트
sudo apt-get install -y podman podman-docker
sudo touch /etc/containers/nodocker      # "Emulate Docker CLI" 경고 끄기

podman --version
docker --version                         # podman-docker 가 제공하는 것
```

### 3-2. Oracle 이미지

```bash
# 📍 k8s-2 호스트
podman login container-registry.oracle.com
podman pull container-registry.oracle.com/database/enterprise:23.26.1.0
```

| 이미지 | 기반 OS | 비고 |
|---|---|---|
| `enterprise:23.26.1.0` (26ai) | **OL8** | 추가 패키지 불필요. **권장** |
| `enterprise:21.3.0.0` | OL7 | `openssl11-libs`, `libquadmath` 필요, 다른 `.so` |
| `enterprise:19.3.0.0` | OL7 | 위와 같음 |
| `free:23.26.2.0` / `free:23.9.0.0` | OL8 | 2 CPU / 2 GB 제한 |

> ⚠️ **`-lite` 변종은 안 된다.** `libagtsh.so` 가 없어 extproc 이 못 뜨고
> 모든 HEracles 호출이 `ORA-28575` 로 실패한다.

### 3-3. 컨테이너 기동

```bash
# 📍 k8s-2 호스트
podman run -d --name heracles-ora \
  --network host \
  -e ORACLE_PWD='<비밀번호>' \
  -e ORACLE_PDB=ORCLPDB1 \
  -v oradata:/opt/oracle/oradata \
  container-registry.oracle.com/database/enterprise:23.26.1.0

podman logs -f heracles-ora      # "DATABASE IS READY TO USE" 까지 — 수 분 걸린다
```

> **`--network host` 를 쓰는 이유.** podman 이 브리지를 만들면 nftables 규칙이 생기는데,
> 이 호스트에는 **libvirt 의 routed 네트워크 규칙이 이미 있다.**
> 검증용 컨테이너 하나 때문에 건드릴 이유가 없다.
> 대신 호스트의 1521 을 쓰므로 **컨테이너를 여러 개 못 띄운다.**

> ⚠️ **EE 는 `ORACLE_PDB=ORCLPDB1` 을 줘야 한다.**
> 스크립트 기본값은 `FREEPDB1` 이라 Free 이미지 기준이다.

### 3-4. HEracles 설치 — 벤더 스크립트 그대로

```bash
# 📍 k8s-2 호스트
curl -fsSL https://heracles.heaan.land/artifacts/heracles/install.sh | \
  TARGET_CONTAINER=heracles-ora \
  ORACLE_PWD='<비밀번호>' \
  ORACLE_PDB=ORCLPDB1 \
  bash
```

`docker` 는 `podman-docker` 가 제공한다. **스크립트를 고칠 필요가 없다.**

### 3-5. 동작 확인

```bash
# 📍 k8s-2 호스트
podman exec -it heracles-ora bash -lc \
  "sqlplus -S heracles_app/HeraclesApp1@//localhost:1521/ORCLPDB1"
```

```sql
-- 확장이 로드됐는가
SELECT object_name, object_type, status FROM user_objects
 WHERE object_name LIKE 'HERACLES%';
```

**여기까지 되면 HEracles 자체는 문제가 없다.** 이후 k8s 에서 안 되면 k8s 쪽 문제다.

---

## 4. 이미지로 굽기

### 4-1. ⚠️ 키를 먼저 빼낸다

설치 과정에서 컨테이너 안에 키가 생성됐다. **이미지에 굽지 않는다.**

```bash
# 📍 k8s-2 호스트 — 키를 꺼낸다
mkdir -p ~/heracles-keys && chmod 700 ~/heracles-keys
podman exec heracles-ora cat /opt/heracles/keys/secret.key  > ~/heracles-keys/secret.key
podman exec heracles-ora cat /opt/heracles/keys/aes256.key  > ~/heracles-keys/aes256.key
chmod 600 ~/heracles-keys/*
```

> ⚠️ **이 저장소에 커밋하지 않는다.** 공개 저장소다.
> 키는 호스트에만 두고, 클러스터에는 `Secret` 으로 넣는다.

```bash
# 📍 k8s-2 호스트 — 이미지에서 제거
podman exec -u 0 heracles-ora rm -f \
  /opt/heracles/keys/secret.key /opt/heracles/keys/aes256.key
```

### 4-2. commit 과 push

```bash
# 📍 k8s-2 호스트
podman commit heracles-ora ghcr.io/jeeklee/k8s-study-oracle-heracles:0.1.0
podman login ghcr.io -u jeeklee
podman push ghcr.io/jeeklee/k8s-study-oracle-heracles:0.1.0
```

**`oradata` 는 볼륨이라 이미지에 안 들어간다.** app user 와 `install.sql` 결과는
클러스터에서 다시 만들어야 한다 — 그것이 5절의 Job 이다.

---

## 5. 쿠버네티스로 옮기기

```
이미지    Oracle base + libheracles.so + extproc.ora + /opt/heracles 권한
Secret    secret.key, aes256.key          ← 전 인스턴스가 공유한다
Job       app user 생성 + install.sql      ← PVC 에 남으므로 인스턴스당 1회
```

### 5-1. 키를 Secret 으로

```bash
# 📍 k2-cp1 — 키 파일을 옮겨온 뒤
kubectl create secret generic heracles-keys \
  --from-file=secret.key --from-file=aes256.key
```

```yaml
      securityContext:
        fsGroup: <oinstall GID>          # oracle 유저가 읽을 수 있어야 한다
      volumes:
        - name: heracles-keys
          secret:
            secretName: heracles-keys
            defaultMode: 0640
      containers:
        - name: oracle
          volumeMounts:
            - { name: heracles-keys, mountPath: /opt/heracles/keys, readOnly: true }
```

GID 는 직접 확인한다.

```bash
# 📍 k8s-2 호스트
podman exec heracles-ora id oracle       # uid=…(oracle) gid=…(oinstall)
```

### 5-2. ⭐ 키를 공유해야 하는 이유

> secret.key 가 없으면 컨테이너 안에서 **생성한다.**

**[Stage 5](../../docs/stages/stage-05-db-scaling.md) 의 샤딩이 여기 걸린다.**
샤드마다 키가 따로 생기면 **같은 데이터를 나눠 담을 수 없다.**
복제본도 마찬가지다. 하나를 만들어 전부에 주입해야 한다.

KMS 모드(`HERACLES_KMS_ADDR` / `HERACLES_KMS_SOCKET`)를 쓰면
**DB 호스트에 키를 두지 않을 수 있다.** 운영이라면 그쪽이 맞다.

### 5-3. DB 쪽 설치는 Job 으로

`install.sql` 은 데이터파일에 객체를 만든다. **PVC 에 남으므로 인스턴스당 한 번**이다.

- 파드가 `Ready` 가 된 뒤 실행돼야 한다 (`initContainer` 로는 안 된다 — DB 가 아직 없다)
- 이미 설치됐으면 건너뛰어야 한다 (`SKIP_APP_USER=1`)
- 샤드가 여러 개면 각각에 실행한다

---

## 자주 막히는 곳

| 증상 | 원인 |
|---|---|
| `ORA-28575` | extproc 이 못 떴다. **`-lite` 이미지를 썼다** |
| `ORA-06520` | `.so` 와 glibc 가 안 맞는다. OL7/OL8 판을 확인 |
| `container ... is not running` | `podman ps` 로 확인. 기동에 수 분 걸린다 |
| `docker not found` | `podman-docker` 를 안 깔았다 |
| 설치는 됐는데 검색이 빈 결과 | **키가 다르다.** 암호화한 키와 검색하는 키가 같은지 |
| 파드 재시작 후 `.so` 가 사라짐 | 컨테이너 파일시스템은 휘발성이다. **이미지에 구워야 한다** |
| Secret 을 마운트했는데 못 읽음 | `fsGroup` 이 `oinstall` GID 와 맞는가 |

---

관련: [`container-registry.md`](container-registry.md) ·
[Stage 4](../../docs/stages/stage-04-workloads.md) ·
[Stage 5](../../docs/stages/stage-05-db-scaling.md)

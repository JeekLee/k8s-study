# Oracle Container Registry — 접근과 사용

`container-registry.oracle.com` 에서 Oracle 이미지를 받아
**클러스터에서 쓰기까지.** [Stage 4](../../docs/stages/stage-04-workloads.md) 의 전제다.

## 0. 도달 확인 — 로그인보다 먼저

계정 문제인지 네트워크 문제인지부터 가른다.

```bash
# 📍 어디서든 — 맥·호스트·VM 각각 해본다
curl -sS -o /dev/null -w "HTTP %{http_code}\n" https://container-registry.oracle.com/v2/
```

### ⭐ `401` 이 정상이다

```
HTTP 401
www-authenticate: Bearer realm="https://container-registry.oracle.com/auth",service="Oracle Registry"
```

`200` 을 기대하면 안 된다. **401 은 "레지스트리가 살아 있고 인증을 요구한다"** 는 뜻이다.
`WWW-Authenticate` 헤더가 오면 도달은 확실하다.

| 응답 | 뜻 |
|---|---|
| **401** | ✅ 정상. 인증만 하면 된다 |
| `000` · 타임아웃 | 네트워크가 막혔다. 방화벽·프록시 |
| `403` | 프록시가 가로챘을 가능성 |
| `200` | 레지스트리가 아닌 무언가가 응답하고 있다 |

### 측정 (2026-09-14)

| 위치 | 결과 | 컨테이너 도구 |
|---|---|---|
| 맥 | `401` ✅ | `docker` |
| k8s-2 호스트 | `401` ✅ | **없음** — containerd 는 VM 안에 있다 |
| VM `k2-cp1` | `401` ✅ | `ctr` (`crictl` 없음) |

**세 곳 모두 도달한다.** 남은 것은 계정과 라이선스뿐이다.

---

## 1. 라이선스 동의 — 진짜 관문은 여기다

**`docker login` 이 성공해도 라이선스에 동의하지 않으면 pull 이 거부된다.**
이걸 모르면 "로그인은 되는데 왜 안 받아지지"로 한참 헤맨다.

1. [oracle.com](https://www.oracle.com) SSO 계정 (무료로 만들 수 있다)
2. https://container-registry.oracle.com 접속 → 우상단 **Sign In**
3. **Database** → 받을 리포지토리 선택 (예: `enterprise`)
4. 우측 언어 선택 → **Continue** → 라이선스 **동의**

> ⚠️ **리포지토리마다 따로 동의해야 한다.**
> `database/enterprise` 에 동의해도 `database/free` 는 별개다.

> ⚠️ **동의는 계정에 붙는다.** 팀원이 각자 자기 계정으로 동의해야 한다.
> CI 에서 쓸 계정도 그 계정으로 한 번 동의해둬야 한다.

---

## 2. 로그인 확인 — 맥에서

```bash
# 📍 맥 — 계정·라이선스 확인용. 클러스터와 무관하다
docker login container-registry.oracle.com
# Username: <Oracle SSO 이메일>
# Password: <SSO 비밀번호>
```

> ⚠️ **MFA 를 켜두면 비밀번호로 실패할 수 있다.** 그 경우 CI 전용 계정을 따로 두는 편이 낫다.

### ⭐ 작은 이미지로 먼저 시험한다 — 문제를 둘로 가른다

`os/oraclelinux` 는 **라이선스 동의가 필요 없고** 100 MB 대다.

```bash
# 📍 맥
docker pull container-registry.oracle.com/os/oraclelinux:9-slim
```

| 결과 | 해석 |
|---|---|
| 성공 | **로그인은 정상.** `database/*` 가 안 되면 **라이선스 동의 문제**다 |
| 실패 | 계정·비밀번호·네트워크 문제 |

수 GB 짜리 EE 이미지로 시험하면 **실패를 확인하는 데만 몇 분**이 걸린다.

---

## 3. 이미지와 태그 고르기

| 리포지토리 | 내용 |
|---|---|
| `database/enterprise` | **Enterprise Edition** — 사내 라이선스 대상 |
| `database/free` | Free 23ai — 2 CPU / 2 GB / 12 GB 제한, RAC·Data Guard 없음 |
| `database/express` | XE (구세대) |
| `os/oraclelinux` | 베이스 OS. 라이선스 동의 불필요 |

**태그는 웹 UI 의 `Tags` 탭에서 확인한다.** `latest` 가 있다고 가정하지 않는다.

API 로 확인하려면 토큰을 먼저 받는다.

```bash
# 📍 맥
USER='<이메일>'; read -rs PASS
REPO='database/enterprise'

TOKEN=$(curl -sS -u "$USER:$PASS" \
  "https://container-registry.oracle.com/auth?service=Oracle%20Registry&scope=repository:${REPO}:pull" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])')

curl -sS -H "Authorization: Bearer $TOKEN" \
  "https://container-registry.oracle.com/v2/${REPO}/tags/list" | python3 -m json.tool
```

> 안 되면 웹 UI 를 본다. 인증 엔드포인트 형식은 바뀔 수 있다.

> ⚠️ **태그를 고정한다.** `latest` 를 쓰면 어제와 오늘이 다른 이미지가 되고,
> [Stage 5](../../docs/stages/stage-05-db-scaling.md) 의 측정 결과를 비교할 수 없게 된다.

---

## 4. 클러스터에서 쓰기

### ⭐ 노드에 로그인하지 않는다

**이미지를 받아오는 것은 kubelet 이다.** `imagePullSecret` 을 주면 된다.
노드에서 `docker login` 할 필요가 없고, 애초에 이 환경의 VM 에는 docker 가 없다.

```bash
# 📍 k2-cp1
kubectl create secret docker-registry oracle-registry \
  --docker-server=container-registry.oracle.com \
  --docker-username='<이메일>' \
  --docker-password='<비밀번호>'
```

```yaml
spec:
  imagePullSecrets:
    - name: oracle-registry
  containers:
    - name: oracle
      image: container-registry.oracle.com/database/enterprise:<태그>
```

> ⚠️ **Secret 은 네임스페이스 단위다.** 다른 네임스페이스에 배포하면 거기에도 만든다.
> ServiceAccount 에 붙이면 그 SA 를 쓰는 모든 파드에 자동 적용된다.

> ⚠️ **비밀번호가 etcd 에 base64 로 들어간다. 암호화가 아니다.**
> → [`../kubernetes/etcd.md`](../kubernetes/etcd.md)

### 미리 받아두기 — 큰 이미지일 때

EE 이미지는 수 GB 다. 파드를 띄우면서 받으면 **`ImagePullBackOff` 로 보이는 타임아웃**이 날 수 있다.
노드에서 미리 받아두면 기동이 즉시 시작된다.

이 환경의 VM 에는 `crictl` 이 없고 `ctr` 만 있다.

```bash
# 📍 워커 VM 안 (Oracle 이 뜰 노드)
sudo ctr -n k8s.io images pull \
  --user '<이메일>:<비밀번호>' \
  container-registry.oracle.com/database/enterprise:<태그>

sudo ctr -n k8s.io images ls | grep oracle
```

### ⚠️ `-n k8s.io` 를 빠뜨리면 안 된다

containerd 는 네임스페이스로 이미지를 나눈다.
**kubelet 은 `k8s.io` 네임스페이스만 본다.**

```bash
# 📍 워커 VM 안
sudo ctr images pull ...            # ❌ default 네임스페이스 → kubelet 이 못 본다
sudo ctr -n k8s.io images pull ...  # ✅
```

받아놓고도 다시 받는 것처럼 보이면 이걸 의심한다.

> `crictl` 을 쓰고 싶으면 `cri-tools` 를 설치한다. `crictl` 은 CRI 를 통해
> 말하므로 네임스페이스를 신경 쓸 필요가 없다.
> → [`../kubernetes/container-runtime.md`](../kubernetes/container-runtime.md)

---

## 5. GitHub Actions 에서 쓰기

HEracles 를 얹은 **커스텀 이미지를 빌드**하려면 Actions 가 베이스 이미지를 받아야 한다.

```yaml
      - uses: docker/login-action@v3
        with:
          registry: container-registry.oracle.com
          username: ${{ secrets.ORACLE_REGISTRY_USER }}
          password: ${{ secrets.ORACLE_REGISTRY_PASSWORD }}
```

`Settings → Secrets and variables → Actions` 에 넣는다.

> ⚠️ **그 계정으로도 웹에서 라이선스 동의를 해둬야 한다.** 동의는 계정에 붙는다.

> ⚠️ **러너 디스크가 부족할 수 있다.** `ubuntu-latest` 의 여유 공간은 10 GB 대다.
> EE 베이스 + 빌드 레이어 + 푸시할 이미지가 한꺼번에 올라가면 빠듯하다.
> 불필요한 사전 설치물을 지우거나, **사내에서 빌드하고 태그만 참조**하는 편이 안전하다.

> ⚠️ **HEracles 설치 파일을 이 저장소에 커밋하지 않는다.** 공개 저장소다.
> 빌드 시점에 사내 경로에서 받아오거나, 이미지를 사내에서 만든다.

---

## 6. 막혔을 때 — 직접 빌드

Oracle 이 **Dockerfile 을 공개**한다. 바이너리는 직접 받아 넣는 방식이다.

```
https://github.com/oracle/docker-images  →  OracleDatabase/
```

사내 정책으로 레지스트리 접근이 막혔거나 커스터마이징이 많이 필요할 때 이 길이 있다.
받은 설치 파일을 `dockerfiles/<버전>/` 에 놓고 `buildContainerImage.sh` 를 돌린다.

사내 미러가 있다면 **그쪽이 가장 빠르다.** 이미지가 크기 때문에 체감 차이가 크다.

---

## 자주 막히는 곳

| 증상 | 원인 |
|---|---|
| `unauthorized` — 로그인은 됐는데 pull 실패 | **라이선스 미동의.** 웹에서 해당 리포지토리에 동의 |
| `docker login` 자체가 실패 | 계정·비밀번호. **MFA** 를 켜뒀는지 확인 |
| `manifest unknown` | 태그가 없다. 웹 UI 의 `Tags` 탭 확인 |
| 파드가 `ImagePullBackOff` | `imagePullSecret` 이 그 네임스페이스에 있는가. 이미지 경로 전체를 적었는가 |
| `ErrImagePull` 이 한참 뒤에 | 타임아웃. 미리 받아두는 편이 낫다 |
| 미리 받았는데 또 받음 | `ctr` 에 **`-n k8s.io`** 를 빠뜨렸다 |
| Actions 가 디스크 부족 | 러너 여유 공간 부족. 사내 빌드 고려 |
| `exec format error` | 맥(arm64)에서 빌드했다. **Oracle 이미지는 amd64 뿐이다** |

---

관련: [Stage 4 — 데이터 계층 워크로드](../../docs/stages/stage-04-workloads.md) ·
[`../kubernetes/container-runtime.md`](../kubernetes/container-runtime.md) ·
[`../kubernetes/etcd.md`](../kubernetes/etcd.md)

# HEracles on PostgreSQL (pgHEaaN) — Oracle판과 비교

> 측정 2026-09-28. **10만 행, 동일한 데이터·패턴**으로 양쪽을 나란히 쟀다.
> Oracle 26ai EE + HEracles 0.1.0 / PostgreSQL 16.15 + pgHEaaN 0.1.0, 같은 호스트(32코어).

## 한 줄

**검색 성능은 거의 같다. 다른 것은 "SQL 에 어떻게 녹아드는가" 다.**

Oracle 은 **도메인 인덱스 연산자**라 `WHERE` 절에 자연스럽게 들어가고,
Postgres 는 **함수**라 `WHERE id IN (SELECT …)` 로 감싸야 한다.
그 차이가 **히트가 많을 때 2배 성능 차이**로 나타난다.

---

## 1. 기능 비교

| | **Oracle (HEracles)** | **PostgreSQL (pgHEaaN)** |
|---|---|---|
| 지원 버전 | 19.3 / 21.3 / 23.26 EE, Free 23·26 | **16 전용** |
| 질의 문법 | `WHERE HERACLES_MATCH(col, val) = 1` | `WHERE id IN (SELECT pgheaan_search_*(…))` |
| **옵티마이저 통합** | **ODCI 도메인 인덱스 + 통계 타입** | **없음** — 일반 C 함수 |
| 실행계획 | `DOMAIN INDEX` 노드로 표시 | 함수 호출 + semi-join |
| ID 컬럼 타입 | `VARCHAR2` (UUID 문자열) | **`uuid` 전용** (`RETURNS SETOF uuid`) |
| LIKE 패턴 | `'XX%'` · `'%XX%'` **자동 라우팅** | **함수를 직접 고른다** (`_prefix` / `_substring`) |
| `encoding` 지정 | `allowedSearchTypes` 에서 추론 | **명시 필요** — `"encoding":"RANGE"` |
| 검색 타입 | Exact · Prefix · Substring · Range | **동일** |
| 동기화 트리거 | INSERT · DELETE | **동일** (UPDATE 없음) |
| 병렬 | (단일 스레드) | `PARALLEL UNSAFE` 선언 |
| 설치 | **docker 필수** (스크립트가 요구) | **네이티브 설치도 지원** |
| 설치 스크립트 | 347줄 | 204줄 |

### ⚠️ 걸린 것 둘

**① `encoding` 을 명시해야 한다.**
Oracle 과 같은 스키마를 그대로 넣으면 숫자 컬럼이 `ROOTS` 로 잡혀 범위 검색이 실패한다.

```
ERROR: SearchType::Equal is not supported by EncodeType::ROOTS
```

```json
{"column":"score","encoding":"RANGE",
 "allowedSearchTypes":["Equal","NotEqual","LessThan","GreaterThan","LessEqual","GreaterEqual"],
 "rangeMin":0,"rangeMax":100000,"rangeDecimalPlaces":0}
```

**② 설치 스크립트가 기본 DB 에만 확장을 만든다.**
`psql -U postgres` 를 `-d` 없이 부르므로 **`postgres` 데이터베이스에만** `CREATE EXTENSION` 이 실행된다.
다른 DB 를 쓰려면 직접 실행해야 한다.

```sql
CREATE EXTENSION pgheaan;   -- 원하는 DB 에서
```

---

## 2. 성능 — 10만 행, 동일 데이터

인덱스 내용도 같다 (`phone` 문자열 + `score` 숫자 유일값 1~100,000).

| 검색 | 히트 | **Oracle** | **Postgres** | 비율 |
|---|---|---|---|---|
| exact | 1 | 9 ms | **8 ms** | 0.9× |
| prefix (전체 길이) | 1 | 8 ms | **8 ms** | 1.0× |
| **substring** | 10,009 | **101 ms** | **207 ms** | **2.0×** |
| range `=` | 1 | 27 ms | **24 ms** | 0.9× |
| range `>=99000` | 1,001 | 32 ms | **29 ms** | 0.9× |
| **range `>=50000`** | 50,001 | **297 ms** | **580 ms** | **2.0×** |
| **range `a..b`** | 1 | **402 ms** | **1,029 ms** | **2.6×** |

### ⭐ 히트가 적으면 동등, 많으면 Postgres 가 2배 느리다

```
Oracle     도메인 인덱스가 rowid 를 스트리밍으로 넘긴다
Postgres   SETOF uuid 를 통째로 만든 뒤  id IN (...) 세미조인
```

5만 건이 걸리면 Postgres 는 **UUID 5만 개를 만들어 테이블과 조인**한다.
Oracle 은 그 단계가 없다. 그것이 2배다.

> **폐구간 `a..b` 는 히트 1건인데도 2.6배 느리다.**
> 이건 세미조인 때문이 아니라 구현 자체 차이로 보인다.

### 적재·구축은 Postgres 가 빠르다

| | Oracle | Postgres |
|---|---|---|
| 10만 행 암호화 적재 | ~9 초 (PL/SQL 루프) | **0.79 초** (`INSERT … SELECT`) |
| 인덱스 구축 (`reindex`) | 4.82 초 | **3.57 초** |
| 인덱스 크기 | 248 MB | 253 MB |

> ⚠️ 적재 차이는 **집합 연산 대 행 루프**의 차이가 크다. FHE 자체의 차이로 읽으면 안 된다.
> 인덱스 크기가 거의 같은 것이 그 근거다 — 같은 엔진이다.

---

## 3. 쓰기 경로 — 문제가 똑같다

| | Oracle | Postgres |
|---|---|---|
| INSERT (FHE 인덱스 없음) | 0.2 ms/행 | **0.06 ms/행** |
| **INSERT (FHE 인덱스 있음)** | **154 ms/행** | **158.67 ms/행** |
| DELETE | 1.57 ms/행 | ~0 ms/행 |
| UPDATE 후 **새 값**으로 검색 | **0건** | **0건** |
| UPDATE 후 **옛 값**으로 검색 | **1건 (유령)** | **1건 (유령)** |

**INSERT 비용이 거의 같다** (154 vs 159 ms/행).
FHE 인덱스 갱신이 지배적이고 **DB 종류는 상관이 없다**는 뜻이다.

**UPDATE 유령 결과도 양쪽 동일하다.** 트리거가 INSERT·DELETE 뿐인 것이 같다.
→ [`heracles-query-model.md`](heracles-query-model.md) §10-2

---

## 4. 어느 쪽을 고를 것인가

| 상황 | 선택 |
|---|---|
| **검색 결과가 대체로 적다** (특정 건 조회) | **어느 쪽이든** — 성능 차이가 없다 |
| **검색 결과가 많다** (수만 건) | **Oracle** — 세미조인 비용이 없다 |
| 쿼리를 SQL 에 자연스럽게 녹이고 싶다 | **Oracle** — `WHERE` 절에 그대로 |
| 기존 스택이 Postgres 다 | **Postgres** — 성능 손해가 크지 않다 |
| 라이선스 비용을 피하고 싶다 | **Postgres** |
| 쓰기가 많다 | **둘 다 부적합** — 154~159 ms/행 |

> **핵심은 DB 선택이 아니라 워크로드 모양이다.**
> 인덱스 크기도, INSERT 비용도, UPDATE 문제도 같다.
> 갈리는 것은 **히트 수가 많을 때의 세미조인 비용**뿐이다.

---

## 5. 재현 절차

```bash
# 📍 호스트 — Postgres 16 + pgHEaaN
podman run -d --name pgh --hostname pgh -e POSTGRES_PASSWORD='<pw>' docker.io/library/postgres:16
curl -fsSL https://heracles.heaan.land/artifacts/pgheaan/install.sh | TARGET_CONTAINER=pgh bash
```

`podman-docker` 가 `docker` 명령을 제공하므로 스크립트를 고칠 필요가 없다
(Oracle 판과 같다 → [`heracles-install.md`](heracles-install.md)).

```sql
-- 📍 psql -U postgres  (기본 DB 에만 설치된다)
SELECT pgheaan_encrypt('hello');
SELECT pgheaan_create_index('pb','pbench', '[…]'::jsonb, 'id', true);
SELECT pgheaan_reindex('pb');
SELECT count(*) FROM pbench WHERE id IN (SELECT pgheaan_search_exact('pb','phone','010-0000-0001'));
```

## 아직 확인하지 않은 것

- **평문 조건과 함께 쓸 때** Postgres 옵티마이저가 순서를 바꿀 수 있는가
  (Oracle 은 불가 → §6. Postgres 는 `IN (SELECT …)` 라 다를 여지가 있다)
- 샤딩·동시성 — Oracle 에서 측정한 것(4샤드 4.27배, 8세션 92%)이 Postgres 에서도 같은가
- "Prefix/Substring 은 single-token 컬럼만" 이라는 문서 기술의 실제 제약

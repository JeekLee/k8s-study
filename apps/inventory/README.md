# inventory — 재고 서비스 (FastAPI)

| | |
|---|---|
| 스택 | FastAPI · Python 3.13 |
| 저장소 | Stage 4: 메모리 / Stage 5: MySQL |
| 포트 | 8000 |
| 이미지 | `ghcr.io/jeeklee/k8s-study-inventory` |

## 엔드포인트

| 메서드 | 경로 | 용도 |
|---|---|---|
| GET | `/` | 서비스 정보 + **응답한 파드 이름** (로드밸런싱 확인) |
| GET | `/healthz` | livenessProbe — 프로세스가 살아 있는가 |
| GET | `/readyz` | readinessProbe — 트래픽을 받을 준비가 됐는가 |
| GET | `/stock` | 재고 조회 |
| POST | `/reserve` | 재고 예약 — `{"sku":"SKU-001","qty":2}` |
| POST | `/release` | 재고 복원 (보상 트랜잭션) |

## 환경변수

| 변수 | 없을 때 | 있을 때 |
|---|---|---|
| `APP_VERSION` | `dev` | 응답에 표시 — 롤링 업데이트 확인용 |
| `GREETING` | 기본 문구 | ConfigMap 주입 확인용 |
| `DATABASE_URL` | **메모리** (Stage 4) | **MySQL** (Stage 5~) |

`DATABASE_URL` 예시:

```
mysql+pymysql://inventory:<비밀번호>@mysql:3306/inventory
```

**이미지는 그대로 두고 환경변수만 바꿔 저장소를 전환한다.**
Stage 5 에서 "설정만 바꿔 배포한다"가 무슨 뜻인지 직접 확인하게 된다.

## 로컬 실행

```bash
pip install -r requirements.txt
uvicorn main:app --reload
curl localhost:8000/stock
```

## 이미지 빌드

```bash
docker build -t ghcr.io/jeeklee/k8s-study-inventory:$(git rev-parse --short HEAD) .
```

## 왜 이렇게 작은가

**쿠버네티스 패턴을 꺼내는 것이 목적**이라 앱은 최소로 유지한다.
`/healthz` 와 `/readyz` 를 나눈 것, 파드 이름을 응답에 넣은 것,
`GREETING` 을 환경변수로 받는 것 모두 **쿠버네티스 기능을 확인하기 위한 장치**다.

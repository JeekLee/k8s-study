# Oracle

[Stage 4](../../docs/stages/stage-04-workloads.md) · [Stage 5](../../docs/stages/stage-05-db-scaling.md) 에서 쓰는
Oracle 관련 참고 자료.

| 문서 | 내용 |
|---|---|
| [`container-registry.md`](container-registry.md) | 이미지 받기 — 라이선스 동의, `imagePullSecret`, 미리 받아두기 |
| [`heracles-install.md`](heracles-install.md) | **HEracles 설치** — 스크립트 분해, podman 경로, k8s 로 옮기기 |
| [`heracles-scaling.md`](heracles-scaling.md) | ⭐ **확장성 실측** — 샤딩 4.27배, 단일 스레드, 카디널리티 |

## 왜 Oracle 인가

[HEracles](https://cryptolab.gitbook.io/heracles) 는 동형암호(FHE)로
**암호문을 복호화하지 않고 검색**하는 DBMS 확장이고, Oracle 을 지원한다.

```sql
SELECT id FROM docs WHERE HERACLES_MATCH(enc_col, :q) = 1;
```

`HERACLES_MATCH` 는 **ODCI 도메인 인덱스 연산자**이고, HEracles 가 자체 FHE 인덱스를 관리한다.

**실측 결과 샤딩이 유효하다 — 4샤드에서 4.27배.**
검색 비용이 인덱스 크기에 선형이고 단일 검색이 1코어만 쓰기 때문이다.
→ [`heracles-scaling.md`](heracles-scaling.md)

## 쓸 예정

- Parallel Query 와 `limits.cpu` 의 관계
- 샤딩 · Active Data Guard · 애플리케이션 레벨 분산
- 컨테이너 환경의 라이선스 계산

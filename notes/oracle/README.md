# Oracle

[Stage 4](../../docs/stages/stage-04-workloads.md) · [Stage 5](../../docs/stages/stage-05-db-scaling.md) 에서 쓰는
Oracle 관련 참고 자료.

| 문서 | 내용 |
|---|---|
| [`container-registry.md`](container-registry.md) | 이미지 받기 — 라이선스 동의, `imagePullSecret`, 미리 받아두기 |

## 왜 Oracle 인가

[HEracles](https://cryptolab.gitbook.io/heracles) 는 동형암호(FHE)로
**암호문을 복호화하지 않고 검색**하는 DBMS 확장이고, Oracle 을 지원한다.

```sql
SELECT id FROM docs WHERE HERACLES_MATCH(enc_col, :q) = 1;
```

`HERACLES_MATCH` 는 **행마다 독립적으로** 동작하고 **매칭된 row ID 만** 돌려준다.
정렬·조인·집계는 평문 SQL 이 맡는다.

이 모양이라 **병렬화에 제약이 없다.** 수평 확장 실험 대상으로 적합하고,
그것이 [Stage 5](../../docs/stages/stage-05-db-scaling.md) 의 주제다.

## 쓸 예정

- Parallel Query 와 `limits.cpu` 의 관계
- 샤딩 · Active Data Guard · 애플리케이션 레벨 분산
- 컨테이너 환경의 라이선스 계산

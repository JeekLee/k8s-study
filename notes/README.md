# 개념과 참고 자료

**어떻게 동작하는가.** 한 번 이해하면 계속 참이고, 반복해서 찾아보게 되는 것들.

실제로 겪은 일과 실습 결과는 [`labs/`](../labs/)에 있다.

## 구조

```
notes/
├── network/      노드 간 통신
│   ├── concepts/   왜 이런 상황인가
│   ├── diagnosis/  진단 명령 (번호 = 확인 순서)
│   └── reference/  채택한 기술과 판단 근거
├── kubernetes/   컴포넌트별 정리
└── infra/        쿠버네티스는 아니지만 필요한 것들
```

| 영역 | 내용 |
|---|---|
| [`network/`](network/) | VCN, 노드 주소 문제, 진단 명령, WireGuard |
| [`kubernetes/`](kubernetes/) | etcd 등 컴포넌트 |
| [`infra/`](infra/) | HAProxy, libvirt/KVM, cloud-init |

## 지금 읽어야 할 것

전체 계획은 [`docs/02-roadmap.md`](../docs/02-roadmap.md). Stage 0에서 정리한 개념은 이 순서로:

1. [`network/concepts/01_vcn-vpc.md`](network/concepts/01_vcn-vpc.md) — 두 노드가 왜 못 만나는가
2. [`network/concepts/02_node-addressing.md`](network/concepts/02_node-addressing.md) — **포트를 다 열어도 안 되는 이유**
3. [`network/reference/`](network/reference/) — 채택한 방식과 그 근거

## 쓰는 기준

- **개념·원리·명령 사용법**이면 여기
- **실제로 한 것, 겪은 것**이면 [`labs/`](../labs/)
- **앞으로 할 계획**이면 [`docs/`](../docs/)

같은 주제가 세 곳에 나타날 수 있고, 그게 맞다.

# 실습 기록

겪은 문제와 해결 과정을 남긴다. **실패한 시도도 지우지 않는다** — CKA Troubleshooting(배점 30%)은 결국 이 기록의 양에 비례한다.

## 구조

```
notes/
├── YYYY-MM-DD-주제.md      그날 겪은 문제 하나 (사건 기록)
├── network/                 노드 간 통신
│   ├── concepts/            개념 — 왜 이런 상황인가
│   ├── diagnosis/           진단 명령 (번호 = 확인 순서)
│   └── reference/           채택한 기술과 판단 근거
├── kubernetes/              컴포넌트별 정리
└── infra/                   쿠버네티스는 아니지만 필요한 것들
```

| 영역 | 내용 |
|---|---|
| [`network/`](network/) | VCN, 노드 주소 문제, 진단 명령, 터널 후보 검토 |
| [`kubernetes/`](kubernetes/) | etcd 등 컴포넌트 |
| [`infra/`](infra/) | HAProxy, libvirt/KVM, cloud-init |

## 지금 읽어야 할 것

전체 계획은 [`docs/02-roadmap.md`](../docs/02-roadmap.md).
Stage 0에서 정리한 개념은 이 순서로:

1. [`network/concepts/01_vcn-vpc.md`](network/concepts/01_vcn-vpc.md) — 두 노드가 왜 못 만나는가
2. [`network/concepts/02_node-addressing.md`](network/concepts/02_node-addressing.md) — **포트를 다 열어도 안 되는 이유**
3. [`network/reference/`](network/reference/) — 채택한 방식과 그 근거

## 사건 기록

| 날짜 | 내용 |
|---|---|
| [2026-09-10](2026-09-10-terminfo-xterm-ghostty.md) | 원격에서 `clear` 실패 — terminfo에 `xterm-ghostty` 없음 |

## 사건 기록 형식

```markdown
## 증상
무엇이 어떻게 안 되었는가. 에러 메시지 원문 포함.

## 확인한 것
어떤 명령으로 무엇을 봤는가. 아니었던 가설도 적는다.

## 원인
왜 그랬는가.

## 해결
무엇을 바꿨는가.

## 배운 것
다음에 같은 증상을 보면 어디부터 볼 것인가.
```

# 스크립트

반복 작업을 묶어둔 것. **실행 전에 읽어볼 것** — 무엇을 하는지 모르고 돌리면
Stage 2 에서 손으로 익힌 의미가 사라진다.

| 스크립트 | 용도 |
|---|---|
| [`prep-node.sh`](prep-node.sh) | 노드 준비 — 커널 모듈, sysctl, containerd, kubeadm |

## 왜 스크립트로 묶었나

Stage 2 에서 `k2-cp1` 에 손으로 한 번 했다. 같은 작업을 노드마다 반복하는데,
**두 번째부터는 학습이 아니라 노동이고 실수만 는다.**
(여러 줄 붙여넣기로 명령이 유실되는 사고를 실제로 두 번 겪었다.)

각 단계의 의미는 스크립트 주석과
[`docs/stages/stage-02-first-cluster.md`](../docs/stages/stage-02-first-cluster.md) 에 있다.

## 사용

노드 안에서:

```bash
curl -sL https://raw.githubusercontent.com/JeekLee/k8s-study/main/scripts/prep-node.sh -o prep-node.sh
less prep-node.sh          # 읽어본다
sudo bash prep-node.sh
```

> 붙여넣기 사고를 피하려고 `curl` 로 받는다.
> 여러 줄을 터미널에 직접 붙이면 일부가 유실될 수 있다.

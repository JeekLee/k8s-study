# 2026-09-10 — 원격 서버에서 `clear` 실패 (`unknown terminal type`)

## 증상

k8s-1에 SSH 접속 후 `clear` 실행 시:

```
'xterm-ghostty': unknown terminal type.
```

`vim`, `less`, `top` 등 화면을 그리는 프로그램도 같은 이유로 동작하지 않는다.

## 확인한 것

```bash
echo $TERM              # → xterm-ghostty
infocmp xterm-ghostty   # 원격에서 실행 → 항목 없음
```

`~/.ssh/config`에 해당 호스트 설정:

```
Host k8s-1
    ...
    SetEnv TERM=xterm-ghostty
```

- 방화벽·권한 문제가 아니다 (SSH 자체는 정상)
- 로컬에서는 `infocmp -x xterm-ghostty`가 정상 출력 → **로컬에만 있고 원격에 없는 것**

## 원인

`TERM` 환경변수는 "이 터미널이 무슨 기능을 지원하는가"를 **terminfo 데이터베이스에서 조회하기 위한 키**일 뿐이다.
SSH가 `SetEnv`로 `xterm-ghostty`를 원격에 전달하지만, Ubuntu 기본 terminfo에는 Ghostty 항목이 없다.
조회에 실패하니 프로그램들이 화면 제어 방법을 알 수 없어 거부한다.

Ghostty가 비교적 새 터미널이라 배포판 terminfo 패키지에 아직 포함되지 않은 것이다.

## 해결

로컬의 terminfo 정의를 뽑아 원격에 심는다.

```bash
infocmp -x xterm-ghostty | ssh k8s-1 -- tic -x -
infocmp -x xterm-ghostty | ssh k8s-2 -- tic -x -
```

- `infocmp -x` : 로컬 terminfo 항목을 텍스트로 출력 (`-x`는 확장 기능 포함)
- `tic -x -` : 표준입력으로 받은 정의를 컴파일해 설치

원격의 `~/.terminfo/`에 **사용자 단위로** 설치되므로 sudo 불필요, 시스템 변경 없음.

```
"<stdin>", line 2, col 31, terminal 'xterm-ghostty': older tic versions may treat the description field as an alias
```

위 메시지가 뜨지만 오류가 아니라 경고다. 설치는 정상 완료된다.

검증:

```bash
TERM=xterm-ghostty tput colors   # → 256
```

기존 세션에는 적용되지 않으므로 **재접속**해야 한다.

## 배운 것

- `TERM`은 터미널 이름이 아니라 **terminfo DB 조회 키**다. 원격에 그 항목이 없으면 이름만 전달돼봐야 소용없다.
- 새 서버를 붙일 때마다 반복될 수 있다. `~/.ssh/config`에서 `SetEnv TERM=xterm-ghostty`를 쓰는 모든 호스트가 대상.
- 급하면 `TERM=xterm-256color clear`처럼 일회성으로 덮어써도 되지만, terminfo를 심는 쪽이 근본 해결이다.
- 비슷한 증상: `tput: unknown terminal`, `vim` 실행 시 화면 깨짐, `less`에서 방향키가 문자로 입력됨.

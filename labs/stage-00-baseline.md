# Stage 0 — 사전 점검 실측

| | |
|---|---|
| 일자 | 2026-09-10 |
| 결과 | ✅ 완료 (일부 항목은 Stage 4로 이월) |
| 대상 | k8s-1, k8s-2 |

> 계획: [`docs/02-roadmap.md`](../docs/02-roadmap.md)
> 개념 정리: [`notes/network/concepts/`](../notes/network/concepts/)

## 완료 기준

- [x] 두 노드가 서로 통신 가능한지 실측
- [x] 클러스터 구축에 필요한 패키지 가용성 확인
- [x] 중첩 가상화 가능 여부 확인
- [x] 개념 정리 (VCN, 노드 주소 문제, 진단 도구)

## 수행 기록

### 노드 스펙

| | k8s-1 | k8s-2 |
|---|---|---|
| CPU | Xeon Platinum 8358 — 16 vCPU (8C/2T) | 동일 — 32 vCPU (16C/2T) |
| Memory | 125 GiB | 251 GiB |
| Swap | 0B | 0B |
| Disk | 3.8 TB ext4 (사용 1%) | 동일 |
| OS | Ubuntu 26.04 LTS | 동일 |
| Kernel | 7.0.0-1009-oracle | 동일 |
| 가상화 | KVM 게스트 | 동일 |

### 사설 IP 도달성

```
k8s-1 → 10.0.0.169    2 packets transmitted, 0 received, 100% packet loss
k8s-2 → 10.0.0.155    2 packets transmitted, 0 received, 100% packet loss
```

**양방향 실패.** 두 노드 모두 `10.0.0.0/24`를 쓰지만 서로 다른 VCN이다.
같은 대역에 있다는 것과 같은 네트워크에 있다는 것은 다르다.

### 공인 IP TCP 도달성 (대조군)

```
k8s-1 → k8s-2:22    Connection succeeded
k8s-2 → k8s-1:22    Connection succeeded
```

**양방향 성공.** 이것이 대조군이다 — 경로 자체는 살아 있으므로,
이후 다른 포트가 실패하면 원인이 "그 포트의 규칙"으로 좁혀진다.

> ⚠️ 처음에 "맥에서 k8s-1로 SSH가 되니 k8s-2 → k8s-1도 될 것"이라고 판단했는데 **틀렸다.**
> 보안 목록 규칙에는 소스 CIDR이 붙으므로 출발지가 다르면 다른 테스트다.
> 대조군은 **본 테스트와 같은 방향**이어야 통제된 변수가 된다. 그래서 양방향을 따로 측정했다.

### 로컬 방화벽

```
Chain INPUT (policy ACCEPT)
1  ACCEPT  all   state RELATED,ESTABLISHED
2  ACCEPT  icmp
3  ACCEPT  all              ← 전부 허용
4  ACCEPT  tcp  dpt:22
5  REJECT  all   reject-with icmp-host-prohibited
```

3번이 5번보다 먼저 전부 허용한다. **차단 지점은 노드 바깥** — OCI 보안 목록이다.

### kubeadm 전제조건

| 항목 | 결과 |
|---|---|
| swap | 0B ✅ |
| `br_netfilter` / `overlay` / `nf_conntrack` | 모두 사용 가능 ✅ |
| NOPASSWD sudo | 양쪽 ✅ |
| 인터넷 egress | 정상 ✅ |

### 패키지 가용성

| 패키지 | 버전 | 출처 |
|---|---|---|
| kubeadm / kubelet / kubectl | **1.35.0-1.1** | pkgs.k8s.io — CKA 시험 버전과 일치 |
| containerd | 2.2.2-0ubuntu1.1 | Ubuntu repo |
| wireguard | 1.0.20250521-1ubuntu1 | Ubuntu repo |
| libvirt-daemon-system | 12.0.0-1ubuntu5.3 | Ubuntu repo |
| virtinst | 1:5.1.0 | Ubuntu repo |
| qemu-system-x86 | 1:10.2.1+ds-1ubuntu3.2 | Ubuntu repo |
| ~~qemu-kvm~~ | **없음** | 26.04에서 제거됨 → `qemu-system-x86` 사용 |

### 중첩 가상화

```
                k8s-1                    k8s-2
CPU 플래그      vmx                      vmx
/dev/kvm        존재 (crw-rw----)        존재 (crw-rw----)
커널 모듈       kvm, kvm_intel           kvm, kvm_intel
```

**양쪽 모두 가능.** 두 호스트에서 VM을 띄울 수 있다.

## 막힌 것

### 원격에서 `clear` 실패

→ [`incidents/2026-09-10-terminfo-xterm-ghostty.md`](incidents/2026-09-10-terminfo-xterm-ghostty.md)

## 결과 확인

핵심 발견은 **노드 주소 문제**다. 포트를 다 열어도 클러스터가 성립하지 않는다는 것을
확인했고, 이것이 이후 모든 설계 판단의 근거가 됐다.

→ [`notes/network/concepts/02_node-addressing.md`](../notes/network/concepts/02_node-addressing.md)

## Stage 4로 이월된 항목

네트워크 연결 검증은 **끝나지 않았다.** OCI 콘솔 작업이 선행돼야 하는데,
Stage 1~3은 k8s-2 내부에서만 이뤄져 네트워크가 필요 없으므로 뒤로 미뤘다.

| 항목 | 상태 |
|---|---|
| OCI 보안 목록에 UDP 51820 인그레스 (양쪽 VCN) | ⬜ 미완 |
| k8s-1 → k8s-2 UDP 51820 통과 확인 (tcpdump) | ⬜ 미완 |
| k8s-2 → k8s-1 UDP 51820 통과 확인 (tcpdump) | ⬜ 미완 |

절차는 [`notes/network/README.md`](../notes/network/README.md#phase-0-연결성-점검-절차) 3·4단계에 정리돼 있다.

> 미룬 것이 위험을 키우지는 않는다. Stage 4에서 막히더라도 그때까지 만든
> k8s-2 쪽 클러스터는 그대로 살아 있고, 최악의 경우 3노드로 계속 갈 수 있다.

## 배운 것

- **사설 IP는 전역 고유하지 않다.** 같은 대역이어도 다른 네트워크면 못 만난다.
- **대조군은 같은 방향이어야 한다.** 출발지가 다르면 다른 테스트다.
- **`ping` 실패로 단정하면 안 된다.** OCI는 ICMP를 부분 허용하므로 TCP는 되는데 ping만 안 될 수 있다.
- **쿠버네티스의 문제는 연결이 아니라 주소였다.** 이것을 먼저 이해하지 않고
  명령만 따라 쳤다면 Stage 4에서 원인을 못 찾고 헤맸을 것이다.

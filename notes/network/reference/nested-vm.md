# 중첩 VM 클러스터 — 참고 자료

> ✅ **채택됨** (2026-09-10) — 양쪽 호스트에서 VM을 띄우는 형태로 채택됐다.
> 아래 검토 메모는 판단 근거로 남겨둔다.

## KVM이란

**리눅스 커널에 내장된 하이퍼바이저**다. 커널 모듈(`kvm`, `kvm_intel`)이 CPU의
가상화 확장(Intel VT-x)을 직접 다루고, `/dev/kvm`이 그 기능을 사용자 프로그램(QEMU)에 열어준다.

VMware나 VirtualBox처럼 별도 소프트웨어가 필요 없다. **리눅스 자체가 하이퍼바이저**다.

## 중첩 가상화 (Nested Virtualization)

k8s-2 자체가 이미 클라우드의 VM이다. 보통 하이퍼바이저는 게스트에게
**CPU의 가상화 확장을 숨긴다.** 그러면 게스트 안에서 `vmx` 플래그가 보이지 않고,
KVM 모듈이 올라오지 않고, VM을 띄울 수 없다.

중첩 가상화는 호스트가 그것을 게스트에게도 노출해주는 기능이다.

### 실측 확인 (2026-09-10, k8s-2)

```
CPU 플래그    : vmx                          ← 게스트에 노출됨
/dev/kvm      : crw-rw---- root kvm 10,232   ← 존재
커널 모듈     : kvm, kvm_intel               ← 적재됨
```

**사용 가능하다.**

## 구조

```
물리 서버 (클라우드 데이터센터)
└─ k8s-2  ← VM (32 vCPU / 251 GiB / 3.8 TB)
   ├─ k1-cp1   ← VM 안의 VM
   ├─ k1-cp2
   ├─ k2-cp1
   ├─ k1-w1
   └─ k2-w1
```

### 자원 배분안

| VM | vCPU | RAM | 디스크 | 역할 |
|---|---:|---:|---:|---|
| k1-cp1 ~ cp3 | 2 | 4 GiB | 40 GB | control plane (etcd 쿼럼 3) |
| k1-w1 ~ w2 | 4 | 8 GiB | 60 GB | worker |
| **합계** | **14** | **28 GiB** | **240 GB** | |
| **남는 자원** | 18 | 223 GiB | 3.5 TB | |

control plane은 kubeadm 최소 요구가 2 vCPU다. 여유가 크므로 나중에 늘려도 된다.

## ⭐ 네트워크 문제가 사라지는 이유

libvirt로 VM을 만들면 k8s-2 안에 **가상 스위치**(`virbr0`)가 생기고 VM들이 전부 거기 물린다.
기본으로 `192.168.122.0/24` 같은 대역이 붙는다.

```
k8s-2 내부
   virbr0 (가상 스위치)  192.168.122.1
      ├── k1-cp1  192.168.122.11
      ├── k1-cp2  192.168.122.12
      ├── k2-cp1  192.168.122.13
      ├── k1-w1   192.168.122.21
      └── k2-w1   192.168.122.22
```

**전부 같은 네트워크에 있다.** 그러면 [노드 주소 문제](../concepts/02_node-addressing.md)의
조건이 그냥 충족된다.

| | 자기를 소개하는 주소 | 남이 닿는 주소 | 일치? |
|---|---|---|---|
| 물리 2노드 (현재) | `10.0.0.155` | `203.0.113.11` | ❌ |
| WireGuard 터널 | `10.10.0.1` | `10.10.0.1` | ✅ (직접 만듦) |
| **중첩 VM** | `192.168.122.11` | `192.168.122.11` | ✅ (원래 그럼) |

NAT도, 다른 VCN도, 클라우드 방화벽도 없다.
`kubeadm init`에 `--node-ip`도 `--apiserver-advertise-address`도 줄 필요가 없다. kubelet이 알아서 잡는다.

```bash
sudo kubeadm init \
  --pod-network-cidr=10.244.0.0/16 \
  --kubernetes-version=v1.35.0
```

> **같은 VCN에 있는 상황을 직접 만들어내는 셈이다.**
> WireGuard가 우회로 해결하려던 것을, 문제가 생기지 않는 환경을 만들어 없앤다.

## CKA 관점의 이득

| | 물리 2노드 | 중첩 VM 3~5대 |
|---|---|---|
| control plane | 1대 (쿼럼상 HA 불가) | **3대 → 진짜 HA** |
| etcd 쿼럼 실습 | ❌ | ✅ 1대 죽여보기 |
| `kubeadm upgrade` | 실패 시 복구 어려움 | **스냅샷 후 롤백** |
| 노드 고장 실습 | 진짜 서버를 망가뜨림 | 부담 없이 반복 |
| 네트워크 설정 | 터널 필요 | 불필요 |

**스냅샷이 특히 크다.** Troubleshooting은 배점 30%인데 망가뜨려야 는다.
VM은 `virsh snapshot-create-as` 한 번이면 몇 초 만에 되돌아온다.
물리 노드를 망가뜨리면 복구에 한 시간씩 쓴다.

## 트레이드오프

| 항목 | 내용 |
|---|---|
| **k8s-1이 유휴** | 나중에 2사이트 구성이나 다른 용도로 쓸 수는 있다 |
| **성능 손실** | 중첩이라 CPU 5~15%, 디스크 I/O는 더 큼. 스터디에는 영향 없는 수준 |
| **단일 장애점** | k8s-2가 죽으면 전부 죽는다. 실습 환경이라 감수 가능 |
| **터널 지식 미사용** | 오늘 정리한 WireGuard 내용을 쓰지 않게 된다 (언제든 별도로 해볼 수는 있음) |
| **자원 관리 추가** | VM 이미지, 스냅샷, 네트워크를 직접 관리해야 함 |

## 구성 도구

### libvirt + virt-install (표준)

```bash
sudo apt-get install -y \
  qemu-system-x86 qemu-utils \
  libvirt-daemon-system libvirt-clients \
  virtinst bridge-utils cloud-image-utils
sudo usermod -aG libvirt,kvm $USER   # 재로그인 필요
virsh list --all
```

> ⚠️ **Ubuntu 26.04에는 `qemu-kvm` 패키지가 없다.** `qemu-system-x86`으로 바뀌었다.
> 인터넷의 옛 문서를 그대로 따라 하면 `Unable to locate package`가 난다.
>
> 실측 확인 (k8s-2): `qemu-system-x86` 1:10.2.1, `libvirt-daemon-system` 12.0.0, `virtinst` 5.1.0 모두 설치 가능.

cloud-init으로 부팅하는 cloud image를 쓰면 VM 생성이 자동화된다.

### multipass (더 간단)

Canonical이 만든 Ubuntu VM 관리 도구. snap으로 설치한다 (k8s-2에 snap 사용 가능 확인됨).

```bash
sudo snap install multipass
multipass launch --name k1-cp1 --cpus 2 --memory 4G --disk 40G
multipass shell k1-cp1
```

libvirt보다 손이 훨씬 덜 가지만 세밀한 제어는 덜 된다. **처음 시작할 때 유리하다.**

### 스냅샷

```bash
# libvirt
virsh snapshot-create-as k1-cp1 before-upgrade
virsh snapshot-revert  k1-cp1 before-upgrade

# multipass
multipass snapshot k1-cp1 --name before-upgrade
multipass restore k1-cp1.before-upgrade
```

## 비교 — kind 는 어떤가

**kind**(Kubernetes in Docker)는 컨테이너를 노드처럼 쓴다. 훨씬 가볍고 빠르며 몇 초면 뜬다.

다만 컨테이너라 **호스트 커널을 공유**한다. 그래서:

| | VM | kind |
|---|---|---|
| 기동 속도 | 수십 초 | 수 초 |
| 자원 사용 | 큼 | 작음 |
| kubelet 정지·복구 실습 | ✅ | 제한적 |
| 커널 파라미터·systemd | ✅ | ❌ |
| 노드 레벨 트러블슈팅 | ✅ | ❌ |

CKA는 노드 레벨 문제가 많이 나오므로 **시험 대비에는 VM 쪽이 낫다.**
빠르게 여러 토폴로지를 찍어볼 때는 kind가 유용하니, 둘을 병행해도 된다.

## 검토 메모

### 결정 전에 답해볼 질문

1. 물리 2노드를 굳이 이어야 할 이유가 있는가?
   CKA 대비만 보면 VM 쪽이 시험 범위(HA, 업그레이드, etcd 복구)를 더 넓게 덮는다.
2. k8s-1을 놀리는 것이 아까운가? 다른 용도가 있는가?
3. 터널을 직접 구성해보는 **학습 가치**를 얼마나 크게 보는가?
   클라우드가 대신 해주던 일을 직접 만들어보는 경험은 그 자체로 값이 있다.
4. 두 가지를 **순차적으로** 할 수는 없는가?
   예: VM으로 먼저 CKA 실습을 진행하고, 터널은 별도 주제로 나중에 다룬다.

### 정리

> **WireGuard는 깨진 환경을 고쳐 쓰는 길이고, 중첩 VM은 안 깨진 환경을 새로 만드는 길이다.**
> 어느 쪽도 틀리지 않으며, 무엇을 배우고 싶은지에 달렸다.

## 관련

- 왜 이 문제가 생겼나 → [`../concepts/02_node-addressing.md`](../concepts/02_node-addressing.md)
- 다른 후보 → [`wireguard.md`](wireguard.md)

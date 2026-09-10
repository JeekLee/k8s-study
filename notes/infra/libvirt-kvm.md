# libvirt / KVM — VM 만들고 관리하기

Stage 1의 참고 자료. **무엇을 왜** 하는지는 [`docs/02-roadmap.md`](../../docs/02-roadmap.md),
**실제로 한 기록**은 [`labs/stage-01-virtualization.md`](../../labs/stage-01-virtualization.md).

## 구성 요소 — 헷갈리기 쉬운 4개

| 이름 | 정체 | 역할 |
|---|---|---|
| **KVM** | 커널 모듈 (`kvm`, `kvm_intel`) | CPU 가상화 확장을 다룸. **하드웨어 가속만** |
| **QEMU** | 사용자 공간 프로세스 | 실제 VM. 디스크·네트워크·USB 등 **장치를 흉내** |
| **libvirt** | 데몬 (`libvirtd`) | VM·네트워크·스토리지를 XML로 정의하고 QEMU를 띄움 |
| **virsh / virt-install** | CLI | libvirt에 명령을 보냄 |

> **KVM = 엔진, QEMU = 차체, libvirt = 관제, virsh = 리모컨.**
>
> QEMU 혼자서도 VM을 돌릴 수 있지만 CPU를 소프트웨어로 흉내 내서 매우 느리다.
> KVM과 함께 쓰면 CPU 명령이 **네이티브 속도**로 실행된다. 그래서 항상 붙여 쓴다.

## 설치

```bash
sudo apt-get update
sudo apt-get install -y \
  qemu-system-x86 qemu-utils \
  libvirt-daemon-system libvirt-clients \
  virtinst bridge-utils cloud-image-utils

sudo usermod -aG libvirt,kvm $USER
```

> ⚠️ **Ubuntu 26.04에는 `qemu-kvm` 패키지가 없다.** `qemu-system-x86`으로 바뀌었다.
> 인터넷의 옛 문서를 그대로 따라 하면 `Unable to locate package`가 난다.

> ⚠️ **`usermod` 후 재로그인해야 그룹이 적용된다.** 안 하면 `virsh list`가
> `failed to connect to the hypervisor`로 실패한다. `id`로 그룹을 확인할 것.

```bash
virsh list --all      # 빈 목록이 나오면 정상
systemctl status libvirtd
```

---

## 네트워크 — 여기가 가장 중요하다

### 네 가지 모드

| 모드 | 동작 | VM 주소 | 출발지 주소 보존 |
|---|---|---|---|
| **NAT** (기본) | 호스트가 SNAT(마스커레이드) | 사설 | ❌ 호스트 IP로 바뀜 |
| **routed** | 라우팅만, NAT 없음 | 사설 | ✅ **보존** |
| **bridge** | L2로 호스트 NIC에 직결 | 호스트망 대역 | ✅ |
| isolated | 외부 차단 | 사설 | — |

### 왜 routed인가

**NAT을 쓰면 Stage 0에서 겪은 주소 불일치 문제가 그대로 재발한다.**

NAT 모드에서 k8s-1의 `k1-cp1`(192.168.121.11)이 k8s-2의 `k2-w1`로 패킷을 보내면,
호스트가 출발지를 자기 IP(`10.10.0.1`)로 바꿔버린다.

```
k1-cp1 이 자기를 등록한 주소 : 192.168.121.11
k2-w1 가 실제로 보는 출발지  : 10.10.0.1        ← 불일치
```

→ [`../network/concepts/02_node-addressing.md`](../network/concepts/02_node-addressing.md)와 **똑같은 실패**다.

**routed 모드는 SNAT을 하지 않으므로 VM의 실제 주소가 보존된다.**

bridge 모드는 온프레미스에서 흔한 선택이지만 **클라우드에서는 막힌다.**
대부분의 클라우드가 vNIC의 MAC 스푸핑을 차단하기 때문이다.

### 기본 네트워크 정리

libvirt는 설치 시 `default`(NAT, `192.168.122.0/24`, `virbr0`)를 만든다.
우리가 쓸 대역과 겹치므로 먼저 치운다.

```bash
virsh net-list --all
sudo virsh net-destroy default
sudo virsh net-autostart default --disable
```

### routed 네트워크 정의

`k8snet.xml` (k8s-2 기준):

```xml
<network>
  <name>k8snet</name>
  <forward mode='route'/>
  <bridge name='virbr1' stp='on' delay='0'/>
  <ip address='192.168.122.1' netmask='255.255.255.0'>
    <dhcp>
      <range start='192.168.122.200' end='192.168.122.250'/>
      <host mac='52:54:00:00:02:11' name='k2-cp1' ip='192.168.122.11'/>
      <host mac='52:54:00:00:02:21' name='k2-w1'  ip='192.168.122.21'/>
      <host mac='52:54:00:00:02:22' name='k2-w2'  ip='192.168.122.22'/>
    </dhcp>
  </ip>
</network>
```

k8s-1에서는 대역만 `192.168.121.x`로 바꾼다 (Stage 4).

```bash
sudo virsh net-define k8snet.xml
sudo virsh net-start k8snet
sudo virsh net-autostart k8snet
virsh net-list
ip addr show virbr1
```

> 💡 **고정 IP를 DHCP 예약(`<host mac=...>`)으로 주는 이유.**
> cloud-init에 static IP를 박아도 되지만, libvirt가 MAC↔IP를 관리하면
> VM을 지우고 다시 만들어도 같은 주소가 나온다. 노드 주소가 흔들리면 클러스터가 깨진다.

### ⚠️ 인터넷 접속 — routed만으로는 안 된다

routed 모드는 NAT을 하지 않으므로, VM이 패키지를 받으러 인터넷에 나가면
**응답이 돌아오지 않는다.** 클라우드 VCN은 `192.168.122.0/24`가 뭔지 모르기 때문이다.

해결책은 **나가는 인터페이스별로 NAT을 구분**하는 것이다.

```bash
# 인터넷으로 나갈 때(ens3)만 NAT — 응답이 돌아올 수 있게
sudo iptables -t nat -A POSTROUTING -s 192.168.122.0/24 -o ens3 -j MASQUERADE

# wg0 로 나가는 것(상대 호스트의 VM)은 NAT 하지 않는다
#   → 출발지 주소가 보존되어 쿠버네티스 노드 주소와 일치한다
```

포워딩도 켜야 한다.

```bash
echo 'net.ipv4.ip_forward=1' | sudo tee /etc/sysctl.d/99-router.conf
sudo sysctl --system
```

재부팅 후에도 유지하려면:

```bash
sudo apt-get install -y iptables-persistent
sudo netfilter-persistent save
```

> 이 **"인터페이스별 NAT 구분"** 이 Stage 4의 핵심이다.
> 인터넷은 NAT, 상대 VM은 NAT 없이. 지금 이해해두면 Stage 4가 수월하다.

---

## VM 만들기

### 1. 베이스 이미지

Ubuntu cloud image를 받는다. 설치 과정 없이 바로 부팅되는 디스크 이미지다.

```bash
sudo mkdir -p /var/lib/libvirt/images/base
cd /var/lib/libvirt/images/base
sudo curl -LO https://cloud-images.ubuntu.com/releases/24.04/release/ubuntu-24.04-server-cloudimg-amd64.img
```

> 💡 **VM의 OS는 호스트와 달라도 된다.**
> 호스트는 Ubuntu 26.04로 고정이지만 VM은 우리가 고른다.
> **24.04 LTS를 권한다** — kubeadm이 검증한 범위 안이고 자료도 훨씬 많다.
> 26.04는 검증 대상 밖이라 preflight 경고가 날 수 있다.

### 2. 디스크

베이스 이미지를 **백킹 파일**로 두면 VM마다 전체 복사를 하지 않아 빠르고 공간도 아낀다.

```bash
sudo qemu-img create -f qcow2 \
  -F qcow2 -b /var/lib/libvirt/images/base/ubuntu-24.04-server-cloudimg-amd64.img \
  /var/lib/libvirt/images/k2-cp1.qcow2 40G
```

### 3. cloud-init seed

cloud image에는 계정도 비밀번호도 없다. 첫 부팅 때 cloud-init이 읽을 설정을
**텍스트 파일 두 개**로 만들고 ISO로 묶어 CD처럼 붙여준다.

이름이 정확히 `user-data`, `meta-data`여야 한다 (확장자 없음).
cloud-init의 NoCloud 방식이 이 이름으로 찾는다.

```bash
mkdir -p ~/vm/k2-cp1 && cd ~/vm/k2-cp1

cat > user-data <<'CLOUDCFG'
#cloud-config
hostname: k2-cp1
fqdn: k2-cp1
users:
  - name: ubuntu
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash
    ssh_authorized_keys:
      - ssh-ed25519 AAAA...          # VM에 접속할 기계들의 공개키
ssh_pwauth: false
package_update: true
CLOUDCFG

cat > meta-data <<'METADATA'
instance-id: k2-cp1
local-hostname: k2-cp1
METADATA

cloud-localds seed.iso user-data meta-data
sudo mv seed.iso /var/lib/libvirt/images/k2-cp1-seed.iso
```

| 항목 | 뜻 |
|---|---|
| `#cloud-config` | **첫 줄에 반드시.** 없으면 통째로 무시된다 |
| `ssh_authorized_keys` | 공개키 목록. 여러 개 가능 |
| `instance-id` | "처음 부팅인가" 판단용. **같으면 설정을 건너뛴다** |

`cloud-localds`는 `cloud-image-utils` 패키지에 들어 있다.
두 파일을 `cidata` 라벨의 ISO로 묶는다 — cloud-init이 그 라벨을 보고 찾는다.

### 4. virt-install

```bash
sudo virt-install \
  --name k2-cp1 \
  --memory 4096 --vcpus 2 \
  --disk path=/var/lib/libvirt/images/k2-cp1.qcow2,format=qcow2 \
  --disk path=/var/lib/libvirt/images/k2-cp1-seed.iso,device=cdrom \
  --network network=k8snet,mac=52:54:00:00:02:11 \
  --os-variant ubuntu24.04 \
  --graphics none \
  --import \
  --noautoconsole
```

| 옵션 | 뜻 |
|---|---|
| `--import` | 설치 미디어 없이 **기존 디스크로 바로 부팅** |
| `--graphics none` | 그래픽 없음. 서버라 시리얼 콘솔만 |
| `--noautoconsole` | 만들고 콘솔에 붙지 않음 |
| `--os-variant` | 최적 설정 힌트. `osinfo-query os`로 목록 확인 |
| `mac=` | 네트워크 XML의 DHCP 예약과 **반드시 일치**시킬 것 |

### 5. 확인

```bash
virsh list --all
virsh domifaddr k2-cp1          # 할당된 IP
virsh console k2-cp1            # 시리얼 콘솔 (빠져나올 땐 Ctrl+])
ssh ubuntu@192.168.122.11
```

---

## 스냅샷 — Stage 6의 기반

```bash
virsh snapshot-create-as k2-cp1 --name before-drill --description "훈련 전"
virsh snapshot-list    k2-cp1
virsh snapshot-revert  k2-cp1 before-drill
virsh snapshot-delete  k2-cp1 before-drill
```

- VM이 **실행 중**이면 메모리 상태까지 저장한다 (느리고 용량이 큼)
- VM이 **정지 상태**면 디스크만 저장한다 (빠름)

> ⚠️ **백킹 파일을 쓰면 내부 스냅샷에 제약이 있을 수 있다.**
> `snapshot-create-as`가 실패하면 백킹 없이 전체 복사본으로 디스크를 만들거나
> 외부 스냅샷(`--disk-only`)을 쓴다. 실패 메시지는 `labs/`에 기록해둘 것.

---

## 일상 운영

```bash
virsh list --all                 # 전체 목록
virsh start    k2-cp1
virsh shutdown k2-cp1            # 정상 종료 (ACPI)
virsh destroy  k2-cp1            # 강제 종료 = 전원 뽑기
virsh undefine k2-cp1 --remove-all-storage   # 정의와 디스크까지 삭제
virsh autostart k2-cp1           # 호스트 부팅 시 자동 시작
virsh edit     k2-cp1            # XML 직접 수정
virsh dominfo  k2-cp1
virsh domifaddr k2-cp1
```

> `shutdown`과 `destroy`를 헷갈리지 말 것.
> **`destroy`는 삭제가 아니라 강제 종료**다. 삭제는 `undefine`이다.

## 진단

| 증상 | 확인 |
|---|---|
| `failed to connect to the hypervisor` | `id`로 `libvirt` 그룹 확인 → 재로그인 |
| VM이 안 뜸 | `sudo cat /var/log/libvirt/qemu/k2-cp1.log` |
| 부팅 과정을 보고 싶음 | `virsh start k2-cp1 --console` |
| IP가 안 잡힘 | `virsh domifaddr`, MAC이 XML 예약과 맞는지 |
| SSH 안 됨 | `virsh console`로 들어가 `cloud-init status --long` |
| 네트워크 확인 | `virsh net-list --all`, `ip addr show virbr1` |
| VM끼리 통신 안 됨 | 호스트에서 `sudo iptables -L FORWARD -n -v` |

## 관련

- 네트워크 진단 → [`../network/diagnosis/`](../network/diagnosis/)
- 주소가 왜 중요한가 → [`../network/concepts/02_node-addressing.md`](../network/concepts/02_node-addressing.md)
- 자원 배분안 → [`../network/reference/nested-vm.md`](../network/reference/nested-vm.md)

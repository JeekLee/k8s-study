# Stage 1 — 가상화 기반

| | |
|---|---|
| 일자 | 2026-09-10 |
| 소요 | 약 1.5시간 |
| 결과 | ✅ 완료 |
| 대상 | k8s-2 (32 vCPU / 251 GiB) |

> 절차: [`docs/stages/stage-01-virtualization.md`](../docs/stages/stage-01-virtualization.md)
> 참고: [`notes/infra/libvirt-kvm.md`](../notes/infra/libvirt-kvm.md)

> 📎 호스트명·공인 IP·MAC은 문서화 전용 값으로 치환해 적는다.

## 완료 기준

- [x] `virsh list --all`이 오류 없이 동작한다
- [x] libvirt 네트워크가 **routed 모드**, 대역은 `192.168.122.0/24`
- [x] VM이 부팅되고 SSH로 들어가진다
- [x] VM에서 인터넷이 된다 (`apt update` 성공)
- [x] 스냅샷을 찍고 되돌렸을 때 변경이 사라진다

---

## 수행 기록

### 1. 패키지 설치

```bash
sudo apt-get install -y \
  qemu-system-x86 qemu-utils \
  libvirt-daemon-system libvirt-clients \
  virtinst bridge-utils cloud-image-utils
```

`qemu-system-x86` 하나에 의존 패키지 199개가 딸려 온다 (110 MB 다운로드, 481 MB 사용).
GTK·GStreamer 같은 데스크톱 라이브러리가 잔뜩 들어오는데, `qemu-system-gui` 때문이다.
서버라 쓰지 않지만 의존성이라 어쩔 수 없다.

설치 중 눈에 띈 것:

```
Created symlink '/etc/systemd/system/multi-user.target.wants/qemu-kvm.service'
Creating group 'libvirt' with GID 982.
Creating group 'libvirt-qemu' with GID 64055.
Enabling libvirt default network
```

`libvirt` 그룹이 **이때 처음 생긴다.** 그래서 `usermod`은 설치 이후에 해야 한다.

### 2. 권한 — 예고된 함정에 그대로 걸림

```bash
sudo usermod -aG libvirt,kvm $USER
virsh list --all
```

```
error: failed to connect to the hypervisor
error: Failed to connect socket to '/var/run/libvirt/libvirt-sock': Permission denied
```

재로그인 후 정상:

```bash
exit
ssh k8s-2
virsh list --all
#  Id   Name   State
# --------------------
```

문서에 적혀 있던 그대로였다. **읽었는데도 그냥 지나쳤다.**

### 3. 동작 확인

```bash
systemctl status libvirtd
# ● libvirtd.service - libvirt legacy monolithic daemon
#      Active: active (running) since Thu 2026-09-10 05:10:00 UTC
#      CGroup: ├─ /usr/sbin/libvirtd --timeout 120
#              ├─ /usr/sbin/dnsmasq --conf-file=/var/lib/libvirt/dnsmasq/default.conf
```

libvirt가 **`dnsmasq`를 자기 자식 프로세스로 띄운다.** 가상 네트워크의 DHCP·DNS를 담당한다.

### 4. 네트워크

```bash
virsh net-list --all
#  Name      State    Autostart   Persistent
#  default   active   yes         yes

sudo virsh net-destroy default
sudo virsh net-autostart default --disable
```

`k8snet.xml`을 작성하고:

```bash
sudo virsh net-define ~/k8snet.xml
# Network k8snet defined from /home/ubuntu/k8snet.xml
sudo virsh net-start k8snet
sudo virsh net-autostart k8snet

virsh net-list
#  Name     State    Autostart   Persistent
#  k8snet   active   yes         yes

ip addr show virbr1
# 4: virbr1: <NO-CARRIER,BROADCAST,MULTICAST,UP> mtu 1500 ... state DOWN
#     inet 192.168.122.1/24 brd 192.168.122.255 scope global virbr1
```

`NO-CARRIER`/`DOWN`은 VM이 아직 없어서 정상.

### 5. 라우팅과 NAT

```bash
echo 'net.ipv4.ip_forward=1' | sudo tee /etc/sysctl.d/99-router.conf
sudo sysctl --system
# ...
# * Applying /etc/sysctl.d/99-router.conf ...
# net.ipv4.ip_forward = 1

sudo iptables -t nat -A POSTROUTING -s 192.168.122.0/24 -o ens3 -j MASQUERADE
sudo netfilter-persistent save
# run-parts: executing /usr/share/netfilter-persistent/plugins.d/15-ip4tables save

sudo iptables -t nat -L POSTROUTING -n -v | grep 192.168.122
#     0     0 MASQUERADE  all  --  *  ens3  192.168.122.0/24  0.0.0.0/0
```

이 시점 패킷 카운터는 `0`. 아직 VM이 없으니 당연하다.
**나중에 VM에서 `apt update`를 돌린 뒤 이 값이 올라가는 것으로 규칙이 실제로 먹혔음을 확인했다.**

`iptables-persistent`는 이미 설치돼 있었다.

### 6. 베이스 이미지와 디스크

```bash
sudo curl -LO https://cloud-images.ubuntu.com/releases/24.04/release/ubuntu-24.04-server-cloudimg-amd64.img
# 100  595.8M  ... 49.55M/s  00:12

sudo qemu-img create -f qcow2 \
  -F qcow2 -b /var/lib/libvirt/images/base/ubuntu-24.04-server-cloudimg-amd64.img \
  /var/lib/libvirt/images/k2-cp1.qcow2 40G

sudo qemu-img info /var/lib/libvirt/images/k2-cp1.qcow2
# virtual size: 40 GiB
# disk size: 196 KiB          ← 백킹 파일 덕분에 실제로는 거의 0
# backing file: .../ubuntu-24.04-server-cloudimg-amd64.img
```

**논리 40 GiB인데 실제 점유는 196 KiB.** 백킹 파일을 쓰면 변경분만 자기 파일에 쌓인다.
VM을 6대 만들어도 베이스 596 MB 하나만 공유한다.

### 7. SSH 키 — k8s-2에는 없었다

```bash
cat ~/.ssh/id_ed25519.pub
# cat: /home/ubuntu/.ssh/id_ed25519.pub: No such file or directory

ssh-keygen -t ed25519
# The key fingerprint is:
# SHA256:xjyn...  ubuntu@k8s-2
```

예상대로 갓 만든 서버라 키가 없었다. 새로 만들고, `user-data`에 **공개키 두 개**를 등록했다.

```yaml
ssh_authorized_keys:
  - ssh-ed25519 AAAA...  <맥의 키>
  - ssh-ed25519 AAAA...  <k8s-2의 키>
```

```bash
cloud-localds seed.iso user-data meta-data
ls -lh seed.iso
# -rw-rw-r-- 1 ubuntu ubuntu 366K Sep 10 06:20 seed.iso
sudo mv seed.iso /var/lib/libvirt/images/k2-cp1-seed.iso
```

### 8. VM 생성

```bash
sudo virt-install \
  --name k2-cp1 --memory 4096 --vcpus 2 \
  --disk path=/var/lib/libvirt/images/k2-cp1.qcow2,format=qcow2 \
  --disk path=/var/lib/libvirt/images/k2-cp1-seed.iso,device=cdrom \
  --network network=k8snet,mac=52:54:00:00:02:11 \
  --os-variant ubuntu24.04 --graphics none --import --noautoconsole

# Starting install...
# Creating domain...
# Domain creation completed.
```

```bash
virsh list --all
#  Id   Name     State
#  1    k2-cp1   running

virsh domifaddr k2-cp1
#  Name    MAC address         Protocol   Address
#  vnet0   52:54:00:00:02:11   ipv4       192.168.122.11/24
```

**MAC 예약이 그대로 동작했다.** XML에 적은 대로 `.11`이 나왔다.
호스트 쪽에 `vnet0` 인터페이스가 생긴 것도 확인된다.

### 9. 접속과 인터넷

```bash
ssh ubuntu@192.168.122.11
# Welcome to Ubuntu 24.04.4 LTS (GNU/Linux 6.8.0-138-generic x86_64)
#   IPv4 address for enp1s0: 192.168.122.11
```

한 번에 들어갔다. 호스트에서 만든 키로 인증됐다.

```bash
cloud-init status --long
# status: done
# detail: DataSourceNoCloud [seed=/dev/sr0]
```

`seed=/dev/sr0` — 우리가 붙인 CD를 읽었다는 뜻이다.

```bash
ip addr show
# 2: enp1s0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 ...
#     inet 192.168.122.11/24 metric 100 brd 192.168.122.255 scope global dynamic enp1s0

ping -c3 8.8.8.8
# 3 packets transmitted, 3 received, 0% packet loss
# rtt min/avg/max/mdev = 33.638/33.665/33.715/0.035 ms

sudo apt-get update
# Hit:1 http://security.ubuntu.com/ubuntu noble-security InRelease
# ... Done
```

**`apt-get update` 성공 — 완료 기준 통과.** MASQUERADE 규칙이 실제로 동작한다.

### 10. 스냅샷 검증

```bash
# 호스트에서
ssh ubuntu@192.168.122.11 'touch ~/BEFORE_SNAPSHOT && ls ~'
# BEFORE_SNAPSHOT

virsh snapshot-create-as k2-cp1 --name clean --description "기본 상태"
# Domain snapshot clean created

virsh snapshot-list k2-cp1
#  Name    Creation Time               State
#  clean   2026-09-10 06:42:21 +0000   running

# 망가뜨린다
ssh ubuntu@192.168.122.11 'sudo rm -rf /etc/apt && touch ~/BROKEN && ls ~'
# BEFORE_SNAPSHOT
# BROKEN

# 되돌린다
virsh snapshot-revert k2-cp1 clean
# Domain snapshot clean reverted

ssh ubuntu@192.168.122.11 'ls ~ && ls /etc/apt'
# BEFORE_SNAPSHOT          ← BROKEN 사라짐
# apt.conf.d
# auth.conf.d
# keyrings
# ...                      ← /etc/apt 복구됨
```

**완벽하게 되돌아왔다.** `/etc/apt`를 통째로 지웠는데 몇 초 만에 복구됐다.

---

## 막힌 것

### `virsh list --all` — Permission denied

```
error: Failed to connect socket to '/var/run/libvirt/libvirt-sock': Permission denied
```

**증상** — `usermod -aG libvirt,kvm` 직후 `virsh`가 실패.

**원인** — 그룹은 로그인 시점에 프로세스에 부여된다. 현재 셸에는 반영되지 않는다.

**해결** — `exit` 후 재접속. `id`로 `libvirt`, `kvm` 확인.

**배운 것** — 문서에 경고가 있었는데도 그냥 지나쳤다. 앞으로 `usermod`을 치면
반사적으로 재로그인하는 습관을 들일 것.

---

## 관찰한 것 / 다음 단계에 영향

### 백킹 파일 + 내부 스냅샷 — 문제없이 동작

문서에 "백킹 파일을 쓰면 내부 스냅샷이 거부될 수 있다"고 적혀 있었으나
**실제로는 정상 동작했다.** qcow2 백킹 파일 + `snapshot-create-as`로 아무 문제 없었다.
VM 6대를 백킹 파일 방식으로 만들어도 된다.

### VM의 인터페이스 이름은 `enp1s0`

호스트는 `ens3`인데 VM은 `enp1s0`이다. 가상 하드웨어 구성이 다르기 때문.
**Stage 2에서 `--node-ip`나 CNI 인터페이스를 지정할 때 이름을 확인해야 한다.**

### VM MTU는 1500

```
2: enp1s0: ... mtu 1500
```

호스트 `ens3`는 9000인데 VM은 1500이다. **Stage 4에서 터널(1420)보다 크므로
조각화가 필요해진다.** 그때 VM MTU 조정을 검토할 것.

### 인터넷 RTT 33.6ms, 지터 0.035ms

매우 안정적이다. etcd 피어 지연 관점에서는 문제없는 수준.
다만 이건 VM→인터넷이고, **Stage 4의 호스트 간 터널 지연은 따로 측정해야 한다.**

### 커널 업그레이드 대기 중

```
Pending kernel upgrade!
Running kernel version: 7.0.0-1009-oracle
The currently running kernel version is not the expected kernel version 7.0.0-1010-oracle.
*** System restart required ***
```

패키지 설치 중 커널이 갱신됐다. **아직 재부팅하지 않았다.**
VM을 더 만들기 전에 재부팅하는 편이 낫고, 그 김에
`k8snet` 자동 시작과 `iptables-persistent` 규칙이 재부팅 후에도 살아남는지 확인할 수 있다.

### `libvirtd`가 `dnsmasq`를 자식으로 띄운다

가상 네트워크의 DHCP·DNS를 담당한다. VM이 IP를 못 받으면 이 프로세스를 봐야 한다.

---

## 다음

- [ ] **재부팅 후 검증** — `k8snet` 자동 시작, MASQUERADE 규칙 잔존, VM 자동 시작 여부
- [ ] 워커 VM 2대(`k2-w1`, `k2-w2`) 추가 생성 — Stage 3에서 필요
- [ ] [Stage 2 — 첫 클러스터](../docs/stages/stage-02-first-cluster.md)

#!/usr/bin/env bash
#
# 쿠버네티스 노드 준비 — 커널 모듈 · sysctl · containerd · kubeadm
#
# Stage 2 의 2~4 절과 동일한 작업이다. 노드를 추가할 때마다 반복되므로
# 스크립트로 묶었다. 각 단계가 왜 필요한지는 아래 주석과
# docs/stages/stage-02-first-cluster.md 를 참고할 것.
#
# 사용법 (노드 안에서):
#   curl -sL https://raw.githubusercontent.com/JeekLee/k8s-study/main/scripts/prep-node.sh -o prep-node.sh
#   less prep-node.sh          # 실행 전에 읽어볼 것
#   sudo bash prep-node.sh
#
set -euo pipefail

K8S_MINOR="${K8S_MINOR:-v1.35}"

say() { printf '\n\033[1;34m== %s ==\033[0m\n' "$*"; }

# ─────────────────────────────────────────────────────────────
say "1. swap 확인"
# kubelet 은 swap 이 켜져 있으면 시작을 거부한다.
# 메모리가 swap 으로 밀려나면 스케줄러의 자원 계산이 무의미해지기 때문.
if [ "$(swapon --show | wc -l)" -ne 0 ]; then
  echo "swap 이 켜져 있다. 끄고 /etc/fstab 에서도 제거한다."
  swapoff -a
  sed -i.bak '/\sswap\s/s/^/#/' /etc/fstab
fi
free -h | grep Swap

# ─────────────────────────────────────────────────────────────
say "2. 커널 모듈"
# overlay      : 컨테이너 이미지 레이어를 겹쳐 하나의 파일시스템으로
# br_netfilter : 브리지를 지나는 패킷도 iptables 를 타게 한다.
#                Service·NetworkPolicy 가 이것에 의존한다.
printf 'overlay\nbr_netfilter\n' > /etc/modules-load.d/k8s.conf
modprobe overlay
modprobe br_netfilter
lsmod | grep -E '^overlay|^br_netfilter'

# ─────────────────────────────────────────────────────────────
say "3. sysctl"
# br_netfilter 모듈이 먼저 올라와야 이 키들이 존재한다. 순서가 중요.
cat > /etc/sysctl.d/k8s.conf <<'SYSCTL'
net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
SYSCTL
sysctl --system >/dev/null
sysctl net.bridge.bridge-nf-call-iptables net.ipv4.ip_forward

# ─────────────────────────────────────────────────────────────
say "4. containerd"
apt-get update -qq
apt-get install -y -qq containerd
containerd --version

# 설정은 반드시 config default 로 생성한다.
# containerd 2.x 는 스키마 version 3 이라 옛 예제를 붙이면 뜨지 않는다.
mkdir -p /etc/containerd
containerd config default > /etc/containerd/config.toml

# cgroup 드라이버를 systemd 로. 빠뜨리면 kubelet 이 조용히 실패한다.
sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' /etc/containerd/config.toml
grep -q 'SystemdCgroup = true' /etc/containerd/config.toml || {
  echo "SystemdCgroup 치환 실패 — config.toml 을 직접 확인할 것"; exit 1;
}

systemctl restart containerd
systemctl is-active containerd

# ─────────────────────────────────────────────────────────────
say "5. kubeadm · kubelet"
# 워커에는 kubectl 이 필수가 아니다. 관리 명령은 control plane 이나 맥에서 친다.
apt-get install -y -qq apt-transport-https ca-certificates curl gpg
mkdir -p /etc/apt/keyrings

curl -fsSL "https://pkgs.k8s.io/core:/stable:/${K8S_MINOR}/deb/Release.key" \
  | gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg --yes

echo "deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/${K8S_MINOR}/deb/ /" \
  > /etc/apt/sources.list.d/kubernetes.list

apt-get update -qq
apt-get install -y -qq kubelet kubeadm

# 버전 고정 — kubeadm upgrade 를 의도적으로 연습하기 위해
apt-mark hold kubelet kubeadm

kubeadm version -o short
kubelet --version

# ─────────────────────────────────────────────────────────────
say "완료"
cat <<'DONE'
이 노드는 클러스터에 합류할 준비가 됐다.

control plane 에서 join 명령을 받아 이 노드에서 실행한다:

    # control plane 에서
    kubeadm token create --print-join-command

    # 이 노드에서
    sudo kubeadm join <엔드포인트>:6443 --token <토큰> \
      --discovery-token-ca-cert-hash sha256:<해시>
DONE

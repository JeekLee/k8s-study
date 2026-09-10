# Stage 2 — 첫 클러스터 (단일 노드)

| | |
|---|---|
| 대상 | k8s-2의 VM 1대 |
| 예상 소요 | 하루 |
| 선행 | [Stage 1](stage-01-virtualization.md) |
| 기록할 곳 | `labs/stage-02-first-cluster.md` |

> 📝 이 문서는 아직 **계획 수준**이다.
> 단계에 진입할 때 Stage 1처럼 실행 가능한 절차로 확장한다.

## 목표

`kubectl get nodes`가 처음으로 동작한다. **가장 큰 이정표.**

노드 하나로 시작한다. 여기서 막히면 노드를 늘려도 똑같이 막히므로
한 대에서 완전히 이해하고 넘어간다.

## 완료 기준

- [ ] `kubectl get nodes`에 노드가 `Ready`로 나온다
- [ ] `kubectl run nginx --image=nginx`로 띄운 파드가 `Running`
- [ ] `kubectl logs`가 동작한다

## 할 일

### HAProxy를 먼저 세운다

> ⚠️ control plane이 Stage 5에서 3대가 되므로 `--control-plane-endpoint`가 필요하다.
> **나중에 바꾸려면 인증서를 전부 재발급해야 한다.**
> 처음부터 HAProxy를 거치게 잡으면 Stage 5에서 클러스터 재구축을 피할 수 있다.
> → [`notes/infra/haproxy.md`](../../notes/infra/haproxy.md)

### 컨테이너 런타임

```bash
# config.toml 은 반드시 containerd config default 로 생성 (2.x 는 스키마 version 3)
sudo mkdir -p /etc/containerd
containerd config default | sudo tee /etc/containerd/config.toml >/dev/null
sudo sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' /etc/containerd/config.toml
sudo systemctl restart containerd
```

`SystemdCgroup = true`를 빠뜨리면 kubelet이 **조용히 실패한다.**

### kubeadm

```bash
sudo kubeadm init \
  --control-plane-endpoint=192.168.122.1:6443 \
  --pod-network-cidr=10.244.0.0/16 \
  --upload-certs \
  --kubernetes-version=v1.35.0
```

설치 후 `apt-mark hold kubelet kubeadm kubectl` — Stage 6의 `kubeadm upgrade` 실습을 위해.

### CNI — Calico

- **Flannel은 안 된다.** NetworkPolicy 미지원이라 CKA 20% 영역이 통째로 빠진다
- **MTU를 1370으로 미리 잡는다.** Stage 4의 이중 캡슐화(`wg0` 1420 → VXLAN −50)를 대비
- `IP_AUTODETECTION_METHOD`를 인터페이스 고정으로

### taint

파드를 띄워보기 위해 잠시 지우고, **다시 걸어둔다.**
남겨둬야 Workloads & Scheduling(15%) 실습 재료가 된다.

다음: [Stage 3 — 다중 노드](stage-03-multi-node.md)

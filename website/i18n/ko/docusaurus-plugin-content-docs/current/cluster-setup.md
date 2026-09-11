---
sidebar_position: 2
title: 클러스터 구축
---
# GPU Kubernetes 클러스터 구축

> 📚 [문서 홈](./README.md)

gShare는 **기존** GPU Kubernetes 클러스터에 배포됩니다. 이 페이지는 그 전제 클러스터를 처음부터
만드는 법을 다룹니다. 자동화는 [`hack/cluster-bootstrap.sh`](../hack/cluster-bootstrap.sh)에
있습니다.

만들어지는 스택:

| 구성 요소 | 선택 |
|---|---|
| Kubernetes | kubeadm **1.36** — 컨트롤 플레인 하나, GPU 워커 N, 선택적 CPU 워커 M |
| 런타임 | **NVIDIA 런타임**이 있는 containerd(RuntimeClass `nvidia`) |
| CNI | **flannel**, 파드 CIDR `10.244.0.0/16` |
| GPU 분할 | **HAMi** — 디바이스 플러그인과 스케줄러, `nvidia.com/gpumem`과 `gpucores` |
| 인그레스 | NodePort 30080/30443의 **ingress-nginx**, 일반 HTTP |
| TLS | **앞단 리버스 프록시**가 종단. 클러스터 내부는 HTTP |
| 스토리지 | 기본 StorageClass **local-path**; 선택적으로 df에 보이는 실제 쿼터의 사용자 볼륨을 위한 **스토리지 노드**(democratic-csi 뒤의 ZFS + NFS) |

## 권장: 제어 머신에서 명령 하나로

제어 머신 — 노트북이나 배스천 — 에 `cluster-info`를 쓰고 스크립트가 SSH로 모든 노드를 설정하게
하세요.

**전제:** 제어 머신에서 각 노드로 (1) SSH 키 인증(`ssh-copy-id`)과 (2) 비밀번호 없는 원격 `sudo`가
이미 동작해야 합니다.

```bash
cp hack/cluster-info.example hack/cluster-info   # MASTER_NODE와 WORKER_NODES 기입
./hack/cluster-bootstrap.sh up                   # prereqs → init → join → addons → label → verify
```

`cluster-info` 형식:

```sh
MASTER_NODE=ubuntu@10.0.0.10
# 워커는 user@ip:MODE. MODE는 exclusive 또는 fractional(기본: fractional).
WORKER_NODES=ubuntu@10.10.0.196:exclusive,ubuntu@10.10.0.197:fractional
# 선택적 GPU 없는 워커, 쉼표 구분. `cpu`로 라벨; NVIDIA 런타임은 설치하지 않음.
# CPU_WORKERS=ubuntu@10.10.0.200,ubuntu@10.10.0.201
# 선택적 스토리지 노드: 주어진(빈) 블록 디바이스의 ZFS 풀을 democratic-csi를 통해
# StorageClass gshare-data로 NFS 내보내기. `storage`로 라벨·테인트.
# STORAGE_NODE=ubuntu@10.10.0.194:/dev/vdb
# 선택적 LAN 일반 HTTP 레지스트리. 모든 노드의 containerd에 설정.
# LOCAL_REGISTRY=10.10.0.191:5001
# SSH_OPTS="-i ~/.ssh/id_ed25519 -o StrictHostKeyChecking=accept-new"   # 선택
```

`up`은 스크립트를 모든 노드에 복사한 뒤 순서대로 실행합니다. 전제 조건(컨트롤 플레인, CPU 워커,
GPU 워커 병렬) → 드라이버를 막 받은 GPU 워커 재부팅·재접속 → 컨트롤 플레인에서 `kubeadm init`,
join 명령 수확 → 워커 join(GPU·CPU 병렬) → 컨트롤 플레인 애드온 → 노드 라벨(컨트롤 플레인과 CPU
워커는 `cpu`, GPU 워커는 설정된 모드) → 검증.

`hack/cluster-info`는 실제 주소를 담으며 git 무시됩니다. `cluster-info.example`만 추적됩니다.
`hack/storage-csi-key`(스토리지 노드가 설정되면 스크립트가 democratic-csi용으로 생성하는 SSH 키
쌍)도 git 무시됩니다 — 새 클론은 다음 `up`에서 새 쌍을 생성합니다.

> 각 노드에서 단계를 손으로 실행하려면 같은 하위 명령을 직접 쓰세요 — 아래 참고.

## 전제 조건

- **노드 OS:** Ubuntu 22.04 또는 24.04(apt 기반). 컨트롤 플레인 하나, GPU 워커 N, 선택적 GPU 없는
  CPU 워커 M.
- **NVIDIA 드라이버:** GPU 워커에서 `nvidia-smi`가 동작하지 않으면 `prereqs --gpu`가 설치합니다 —
  `NVIDIA_DRIVER=auto`는 `ubuntu-drivers` 권장을 씁니다. `NVIDIA_DRIVER=nvidia-driver-550-server`로
  버전을 고정하거나 `NVIDIA_DRIVER=skip`으로 설치를 건너뜁니다. 새 설치는 커널 모듈 로드를 위해
  **재부팅**이 필요합니다. `up`은 노드를 직접 재부팅하고 `nvidia-smi`가 동작하는 채로
  돌아올(`boot_id` 변경) 때까지 기다립니다. 타임아웃은 `REBOOT_WAIT_TRIES` × 5초, 기본 10분.
  단독 실행 시 `prereqs --gpu`는 `NVIDIA_DRIVER_REBOOT=1`을 주지 않으면 안내만 출력합니다.
  드라이버가 동작하는 노드는 건드리지 않습니다.
- **helm v3:** 없으면 `addons` 단계에서 자동 설치(`get-helm-3`). `HELM_SKIP_INSTALL=1`로 비활성화.
- **네트워크:** 노드 간 6443(API 서버), 10250(kubelet), 8472/udp(flannel VXLAN), NodePort 범위
  30000–32767 개방.

## 단계별

### 1. 모든 노드 — 전제 조건

```bash
# 컨트롤 플레인과 CPU 전용 노드
sudo ./hack/cluster-bootstrap.sh prereqs

# GPU 워커 — nvidia-container-toolkit과 런타임, 그리고 nvidia-smi가 없으면 드라이버도 설치
sudo ./hack/cluster-bootstrap.sh prereqs --gpu
```

`SystemdCgroup`이 켜진 containerd, 필요한 커널 모듈과 sysctl을 설치하고, swap을 끄고, kubeadm·
kubelet·kubectl 1.36을 설치합니다. 드라이버를 새로 설치하면 재부팅을 요청하며,
`NVIDIA_DRIVER_REBOOT=1`을 주면 스스로 재부팅합니다.

### 2. 컨트롤 플레인 — 초기화

```bash
sudo ./hack/cluster-bootstrap.sh init
```

`kubeadm init`을 실행하고 flannel을 적용한 뒤 `kubeadm join …` 명령을 출력합니다. 복사하세요.

### 3. 각 워커 — join

```bash
sudo ./hack/cluster-bootstrap.sh join "kubeadm join 10.x.x.x:6443 --token ... --discovery-token-ca-cert-hash sha256:..."
```

### 4. 컨트롤 플레인 — 애드온

```bash
./hack/cluster-bootstrap.sh addons
```

RuntimeClass `nvidia`, HAMi, NodePort의 ingress-nginx, 기본 StorageClass local-path를 설치합니다.

### 5. 컨트롤 플레인 — 노드 라벨

HAMi는 `gpu=on`이, gShare 스케줄링은 `gshare.io/gpu-mode`가 필요합니다. **`up` 경로는 이미
`cluster-info`의 모드를 적용했습니다** — 이 단계는 수동 경로에만 해당합니다.

```bash
./hack/cluster-bootstrap.sh label <gpu-node-1> exclusive
./hack/cluster-bootstrap.sh label <gpu-node-2> fractional
./hack/cluster-bootstrap.sh label <control-plane> cpu
```

### 6. 검증

```bash
./hack/cluster-bootstrap.sh verify
```

노드가 Ready인지, `nvidia.com/gpu`와 `nvidia.com/gpumem` 용량이 광고되는지, HAMi·ingress·flannel·
local-path 파드가 Running인지, 기본 StorageClass가 있는지 확인합니다.

### 스토리지 노드(선택): 실제 쿼터가 있는 볼륨 {#storage-node-optional-volumes-with-a-real-quota}

local-path는 RWO만 제공하고 아무것도 강제하지 않습니다. 50 GiB 볼륨이 `df`에서 노드 디스크
전체를 보여 주고 그것을 채울 수 있습니다. 스토리지 노드가 둘 다 해결합니다. `cluster-info`의
`STORAGE_NODE=user@ip:/dev/<device>`가 `up`이 애드온 뒤에 다음을 실행하게 합니다.

1. 그 노드에서 **`storage <device>`** — `zfsutils-linux`와 `nfs-kernel-server` 설치, 디바이스에 풀
   `gshare` 생성(통째로. `STORAGE_VDEVS`로 여러 디바이스를 미러나 raidz로), 데이터셋
   `gshare/volumes`와 `gshare/snapshots`, ARC를 `ZFS_ARC_MAX_MB`(3 GiB)로 제한, `gshare-csi`
   계정 생성: SSH 키만, sudo는 드라이버가 실행하는 zfs/exportfs/chown 명령으로 제한.
2. 컨트롤 플레인에서 **`storage-csi <ip> <key>`** — democratic-csi(`zfs-generic-nfs`, 값은
   `deploy/storage/democratic-csi-values.yaml`)와 StorageClass **`gshare-data`** 설치: PVC당
   데이터셋 하나에 `refquota` = 요청량이라 세션 안의 `df`가 정확히 쿼터를 보여 주고 넘는 쓰기는
   `ENOSPC`로 실패. RWO, RWX, ROX 모두 이 클래스 하나에서. 승인된 쿼터 증가를 위한
   `allowVolumeExpansion`.
3. **`label <node> storage`** — `gshare.io/role=storage`와 `NoSchedule` 테인트. 세션과 제어
   플레인이 거기 절대 배치되지 않습니다.

모든 노드는 `prereqs`에서 `nfs-common`을 받습니다. 그다음 오퍼레이터를 그 클래스로 지정:
`--set operator.volumeStorageClass=gshare-data`(또는 값 오버레이에서 주석 해제). 오퍼레이터는
각 볼륨 PVC를 `operator.volumeSyncInterval`(5m)마다 제어 플레인에 보고합니다. 원장용 사용
바이트, 승인된 쿼터 증가의 클레임 반영, 그리고 `api.volumeReclaimGraceHours`(24h) 전에 삭제된
볼륨의 PVC 회수 — 데이터셋 포함.

손으로는 그 순서대로: 스토리지 노드에서
`sudo STORAGE_CSI_PUBKEY="$(cat key.pub)" bash cluster-bootstrap.sh storage /dev/vdb`, 그다음
컨트롤 플레인에서 `bash cluster-bootstrap.sh storage-csi <ip> key`와
`bash cluster-bootstrap.sh label <node> storage`.

풀은 설계상 단일 장애점입니다(복제 없음). 내구성을 위해 노드에서 ZFS 스냅샷을 찍고 `zfs send`로
외부에 복제하세요.

### 로컬 레지스트리(선택) {#local-registry-optional}

세션 이미지는 큽니다(5–15 GiB). LAN에서는 노드마다 Docker Hub에서 받는 것보다 로컬 레지스트리가
낫습니다. 두 부분, 둘 다 선택.

1. **레지스트리 자체** — `deploy/registry/registry.yaml`이 스토리지 노드(`gshare.io/role=storage`)에
   일반 HTTP 레지스트리 두 개를 돌립니다. 로컬 빌드 세션 이미지의 푸시 대상 `:5000`, 그리고
   공개 카탈로그 이미지가 첫 풀 이후 LAN에서 받아지도록 하는 docker.io **풀스루 미러** `:5001`.
   `kubectl apply -f deploy/registry/registry.yaml`(레이아웃이 다르면 헤더의 nodeSelector /
   storageClassName 조정).
2. **노드 신뢰** — 모든 노드의 containerd에 알려야 합니다.

   ```bash
   sudo LOCAL_REGISTRY=<storage-ip>:5000 LOCAL_REGISTRY_MIRROR=<storage-ip>:5001 \
        bash cluster-bootstrap.sh registry     # 노드마다; 멱등
   ```

   `/etc/containerd/certs.d/<host:port>/hosts.toml`(그리고 미러를 거쳐 풀하고 업스트림을 대체로
   두는 `docker.io` 항목)을 쓰고 **또한** `config.toml`의 `config_path`를 설정합니다 — containerd
   2.x는 이것 없이 `certs.d`를 조용히 무시하고 모든 풀이 "server gave HTTP response to HTTPS
   client"로 끝납니다. `up` 경로는 `cluster-info`에 `LOCAL_REGISTRY`가 있으면 모든 노드에서 이를
   실행합니다. 나중에 TLS로 옮기려면 `hosts.toml` 옆에 CA를 두면 됩니다. 레이아웃은 그대로.

레지스트리를 `"insecure-registries"`에 올린 아무 docker 호스트에서 카탈로그 이미지를 빌드·푸시:

```bash
REG=<storage-ip>:5000 build/images/build.sh push   # 모든 카탈로그 이미지 빌드, LAN에 푸시
```

그다음 콘솔에서 등록(이미지 → 레지스트리 참조는 `<storage-ip>:5000/gshare-session:<tag>`).
노드는 LAN에서 바로 풀합니다.

## 운영 중인 클러스터 늘리기·줄이기 {#growing-or-shrinking-a-running-cluster}

위 단계는 첫 구축을 설명하지만 각 하위 명령은 멱등하고 독립적이므로, 같은 조각으로 이미 세션을
서비스 중인 클러스터에 기계를 추가할 수 있습니다. 여기 어느 것도 진행 중인 작업을 방해하지
않습니다. 기존 노드는 건드리지 않습니다.

### 노드 추가

1. **새 노드에서 — 전제 조건.** swap 끄기, 커널 모듈과 sysctl, containerd, `nfs-common`, 그리고
   GPU 노드라면 NVIDIA 런타임(`nvidia-smi`가 없으면 드라이버도):

   ```bash
   sudo ./hack/cluster-bootstrap.sh prereqs        # GPU 노드는 `gpu` 추가
   ```

2. **컨트롤 플레인에서 — join 명령 발급**, 새 노드에서 실행:

   ```bash
   kubeadm token create --print-join-command       # 컨트롤 플레인
   sudo ./hack/cluster-bootstrap.sh join "kubeadm join 10.x.x.x:6443 --token ... --discovery-token-ca-cert-hash sha256:..."
   ```

3. **컨트롤 플레인에서 — 라벨.** 이걸 빼먹는 것이 새 GPU 노드가 용량을 광고하지 않는 흔한
   이유입니다. HAMi는 `gpu=on` 노드의 카드만 잡고, 배치는 `gshare.io/gpu-mode`를 읽습니다.

   ```bash
   ./hack/cluster-bootstrap.sh label <node> fractional    # 또는: exclusive | cpu | storage
   ```

4. **새 노드에서 — 클러스터가 쓴다면 LAN 레지스트리.** `prereqs`는 `LOCAL_REGISTRY`에서 이것을
   쓰므로 손으로 join한 노드는 이를 놓치고 모든 세션 이미지 풀이
   `http: server gave HTTP response to HTTPS client`로 실패합니다 — 노드는 레지스트리가 일반
   HTTP를 쓴다는 것을 알 길이 없습니다. 변수를 설정해 `prereqs`를 다시 실행하는 것이 안전한
   방법입니다.

   ```bash
   sudo LOCAL_REGISTRY=<registry-ip>:5000 LOCAL_REGISTRY_MIRROR=<registry-ip>:5001 \
        ./hack/cluster-bootstrap.sh prereqs
   ```

   손으로 한다면? 동작하는 노드에서 `/etc/containerd/certs.d/`를 복사하고
   `/etc/containerd/config.toml`에 `config_path = "/etc/containerd/certs.d"`를 설정합니다. 한 번
   장애를 낸 두 규칙: **먼저 파일을 백업**(`cp config.toml config.toml.bak`)하고, `sed`/정규식
   치환 대신 편집기로 값을 쓰세요 — 파일에는 `plugin_config_path`도 있어서 짧은 키에 맞는 패턴이
   긴 키를 망가뜨리고, 그러면 containerd가 시작을 거부합니다. **containerd 재시작은 노드 자체
   콘솔에서**(`sudo systemctl restart containerd`), 그 노드의 파드에서 하지 마세요. containerd를
   멈추면 명령을 낸 파드가 죽고 시작 절반이 실행되지 않으며, 그 노드에는 고칠 `kubectl exec`가
   없습니다.

5. **검증** — 노드 Ready, `nvidia.com/gpu`와 `nvidia.com/gpumem` 광고, 애드온 Running:

   ```bash
   ./hack/cluster-bootstrap.sh verify
   ```

6. **`hack/cluster-info`에 기록**(`WORKER_NODES`, `CPU_WORKERS`, …). 나중의 `up` 실행이 파일과
   클러스터를 맞춰 두도록.

그다음 gShare 자체에서:

7. **등록할 것 없음.** 오퍼레이터의 인벤토리 컨트롤러가 다음 틱에 노드와 카드를 보고하고, 제어
   플레인은 (클러스터, 호스트명)으로 upsert하며 노드는 **노드** 아래 저절로 나타납니다.
   `node_liveness`가 하트비트가 오면 `ready`로(멈추면 `NODE_STALE_SEC`, 기본 5분 후 `offline`으로)
   옮깁니다.

8. **그 GPU 모델의 오퍼링 확인.** 승인은 `offering.gpu_model`을 디바이스 모델과 **문자열
   동등**으로 맞추므로, 활성 오퍼링이 없는 모델의 카드는 관리자에게 보이지만 쓸 수 없습니다 —
   세션 생성이 `409 unserviceable`로 답합니다. **자원 → GPU 오퍼링**의 카탈로그 행에 있는
   "클러스터 보유" 태그가 어느 모델이 실제 카드로 뒷받침되는지 알려 줍니다. 용량을 공지하기 전에
   새 모델의 오퍼링을 만들거나 활성화하세요.

9. **선택, 콘솔에서:**
   - **노드 풀** — 특정 부서가 먼저 써야 한다면 노드를 전용 풀에 배정. 미배정 노드는 모두가
     공유.
   - **세션 이미지 미리 풀** — 첫 세션이 5–15 GiB 풀을 기다리지 않도록(4단계의 LAN 레지스트리가
     있으면 빠르지만 즉시는 아님).
   - **무손실 일시정지** — CRIU와 cuda-checkpoint가 준비되면 노드에 `gshare.io/criu=ready`와
     `gshare.io/cuda-checkpoint=ready` 라벨. 없으면 그 노드의 세션은 콜드 일시정지로 대체.

### 노드 제거

먼저 drain, 그다음 삭제. 원장이 사라진 하드웨어 위의 세션을 쥐고 있어서는 안 됩니다.

1. **콘솔에서** — 노드에 남은 세션을 종료하거나 일시정지(세션, 노드로 필터)해 크레딧이 정산되게
   합니다.
2. **컨트롤 플레인에서:**

   ```bash
   kubectl cordon <node>
   kubectl drain <node> --ignore-daemonsets --delete-emptydir-data --timeout=300s
   kubectl delete node <node>
   ```

   DaemonSet(calico, kube-proxy, HAMi 디바이스 플러그인, dcgm-exporter, node-exporter, CSI 노드
   플러그인)은 남는 것이 정상입니다. `--ignore-daemonsets`가 그것입니다.
3. **제거되는 기계에서**, 영구히 떠난다면: `sudo kubeadm reset -f`와 `/etc/cni/net.d` 정리.
4. **콘솔에서 — 노드 → 삭제.** 노드가 `offline`으로 읽히면(`node_liveness`가 하트비트가 멈춘 뒤
   표시) 버튼이 나타납니다. 살아 있는 할당이나 비종료 세션이 남아 있으면 `409 node_busy`로
   거부되고, 노드와 카드 기록을 지우되 과금 이력은 유지합니다 — 과거 할당은 더 이상 없는 카드에서
   분리된 채 `gpu_uuid`를 가지고 남습니다.
5. **정리** — 마지막 노드를 잃은 전용 풀은 빈 풀로 남습니다. 삭제하거나 다른 노드를 배정하세요.
   풀이 비어 버린 테넌트의 세션은 정책이 넘침을 허용하면(`shared_pool`) 계속 돌며 공유 노드로
   대체됩니다.

아직 클러스터에 있는 노드를 삭제하는 것은 위험하다기보다 무의미합니다. 오퍼레이터의 다음
인벤토리 보고가 행을 다시 만듭니다.

## 다음 — gShare 배포

클러스터가 준비되면 올인원 설치가 가장 단순한 길입니다. 차트가 데이터 계층, 시크릿, CRD,
네임스페이스, 오퍼레이터 내부 JWT, 로컬 클러스터 등록을 수동 전제 없이 올립니다.

```bash
make deploy-incluster                          # deploy/values/incluster.yaml
ADMIN_JWT=$(./hack/bootstrap-superadmin.sh)    # 선택: 관리자 API 호출용 super_admin 토큰
```

앞에 리버스 프록시를 두어 콘솔 도메인의 TLS를 종단하고 ingress-nginx NodePort(`:30080`, HTTP)로
전달하세요. 외부 CloudNativePG, Redis, external-secrets에 대한 프로덕션 설치는
`deploy/values/dockerhub.yaml`로 `make prod-deploy`.

## 주의

- 이 스크립트는 **검증된 스택 하나를 재현**합니다. 어디서나 수정 없이 동작한다는 보장은 없습니다 —
  드라이버 버전, 커널, 사내 프록시와 레지스트리, 방화벽 정책 모두 조정을 요구합니다. 단계마다
  `verify`를 실행하세요.
- **재실행은 안전합니다.** `prereqs`, `init`, `join`, `addons`는 멱등합니다. 키링은 덮어쓰고, swap
  줄은 두 번 주석 처리되지 않으며, 애드온은 `apply`나 `helm upgrade -i`를 씁니다. `init`은 API
  서버의 `/healthz`를 프로브해 할 일을 정합니다 — 정상이면 건너뛰고, 이전 init의 잔재만
  있으면(점유된 포트, 매니페스트, etcd 데이터) `kubeadm reset -f` 후 재초기화합니다.
  `INIT_FORCE_RESET=0`이면 대신 알려 줍니다. `join`은 `kubelet.conf`가 있으면 건너뜁니다. 예외
  하나: containerd 설정은 매번 기본값에서 재생성되므로 그곳의 수동 편집은 보존되지 않습니다.
- HAMi 스케줄러 이미지 태그는 클러스터 버전에 맞춰 자동 설정되지만(`scheduler.kubeScheduler.imageTag`)
  HAMi 호환성 매트릭스로 확인하세요.
- 프로덕션 강화 — 다중 컨트롤 플레인, RWX 볼륨용 CephFS나 NFS, Vault나 KMS를 쓰는
  external-secrets, Kyverno와 cosign 검증 — 은 이 스크립트 범위 밖입니다. 루트
  [`README.md`](../README.md)의 참조 구성을 보세요.

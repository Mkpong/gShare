---
sidebar_position: 2
title: 클러스터 구축
---
# GPU Kubernetes 클러스터 구축

> 📚 [문서 홈](./README.md)

gShare는 기존 GPU Kubernetes 클러스터 환경에 배포됩니다. 본 문서에서는 이러한 사전 요건 클러스터를 처음부터 구축하는 방법을 설명합니다. 전체 구축 과정은 [`hack/cluster-bootstrap.sh`](../hack/cluster-bootstrap.sh) 스크립트로 자동화되어 있습니다.

구축되는 스택 구성:

| 구성 요소 | 선택 |
|---|---|
| Kubernetes | kubeadm **1.36**: 컨트롤 플레인 1대, GPU 워커 N대, CPU 워커 M대(선택) |
| 런타임 | **NVIDIA 런타임**이 구성된 containerd (RuntimeClass: `nvidia`) |
| CNI | **flannel** (파드 CIDR: `10.244.0.0/16`) |
| GPU 분할 | **HAMi**: 디바이스 플러그인 및 스케줄러 (`nvidia.com/gpumem`, `gpucores` 지원) |
| 인그레스 | **ingress-nginx** (NodePort 30080/30443, 일반 HTTP) |
| TLS | **전면 리버스 프록시**: TLS 종단 담당 (클러스터 내부 통신은 HTTP) |
| 스토리지 | 기본 StorageClass: **local-path**. 사용자 볼륨의 실제 쿼터를 반영하기 위해 선택적으로 **스토리지 노드**(democratic-csi 기반 ZFS + NFS) 구성 가능 |

## 권장 사항: 제어 머신에서 단일 명령어로 실행

노트북이나 배스천 등 제어 머신에 `cluster-info` 파일만 작성하면, 스크립트가 SSH를 통해 전체 노드를 자동으로 설정합니다.

**사전 조건:** 제어 머신에서 각 노드로 (1) SSH 키 기반 인증(`ssh-copy-id`) 및 (2) 비밀번호 없는 원격 `sudo` 실행이 설정되어 있어야 합니다.

```bash
cp hack/cluster-info.example hack/cluster-info   # MASTER_NODE 및 WORKER_NODES 기입
./hack/cluster-bootstrap.sh up                   # prereqs → init → join → addons → label → verify 순으로 진행
```

`cluster-info` 작성 형식:

```sh
MASTER_NODE=ubuntu@10.0.0.10
# 워커 포맷: user@ip:MODE (MODE는 exclusive 또는 fractional이며, 기본값은 fractional입니다.)
WORKER_NODES=ubuntu@10.10.0.196:exclusive,ubuntu@10.10.0.197:fractional
# GPU가 없는 CPU 전용 워커 목록(쉼표 구분). 'cpu' 레이블이 부여되며 NVIDIA 런타임은 설치되지 않습니다.
# CPU_WORKERS=ubuntu@10.10.0.200,ubuntu@10.10.0.201
# 스토리지 노드 설정(선택): 지정한 (비어 있는) 블록 디바이스에 ZFS 풀을 생성하고, democratic-csi를 통해
# StorageClass gshare-data로 NFS 내보내기를 수행합니다. 'storage' 레이블 및 테인트가 설정됩니다.
# STORAGE_NODE=ubuntu@10.10.0.194:/dev/vdb
# 사내/LAN 전용 HTTP 레지스트리(선택). 모든 노드의 containerd에 설정됩니다.
# LOCAL_REGISTRY=10.10.0.191:5001
# SSH_OPTS="-i ~/.ssh/id_ed25519 -o StrictHostKeyChecking=accept-new"   # 옵션
```

`up` 명령은 스크립트를 모든 노드로 복사한 후 다음 순서에 따라 집행합니다:
1. 사전 조건 구성 (컨트롤 플레인, CPU 워커, GPU 워커 병렬 처리)
2. 신규 드라이버가 설치된 GPU 워커 재부팅 및 재접속
3. 컨트롤 플레인에서 `kubeadm init` 실행 및 join 명령어 수집
4. 워커 노드 join (GPU 및 CPU 노드 병렬 처리)
5. 컨트롤 플레인 애드온 설치
6. 노드 레이블 지정 (컨트롤 플레인 및 CPU 워커: `cpu`, GPU 워커: 지정한 모드)
7. 클러스터 검증

`hack/cluster-info` 파일은 실제 노드 주소 정보를 포함하므로 Git 추적 대상에서 제외(`.gitignore`)됩니다. 버전 관리에는 `cluster-info.example`만 포함됩니다. 스토리지 노드가 설정될 때 democratic-csi용으로 자동 생성되는 SSH 키 쌍(`hack/storage-csi-key`) 역시 Git 추적에서 제외됩니다. 새 환경에서 클론한 경우 다음 `up` 실행 시 새로운 키 쌍을 생성합니다.

> 각 노드에서 개별 단계를 수동으로 실행하려는 경우, 아래 절차에 따라 동일한 하위 명령을 직접 실행할 수 있습니다.

## 사전 조건

- **노드 OS:** Ubuntu 22.04 또는 24.04 (apt 기반). 컨트롤 플레인 1대, GPU 워커 N대, CPU 워커 M대(선택).
- **NVIDIA 드라이버:** GPU 워커 노드에서 `nvidia-smi`가 정상 작동하지 않는 경우, `prereqs --gpu` 실행 시 드라이버를 자동 설치합니다. `NVIDIA_DRIVER=auto` 설정 시 `ubuntu-drivers`에서 권장하는 버전을 설치합니다. 특정 버전을 고정하려면 `NVIDIA_DRIVER=nvidia-driver-550-server`와 같이 지정하며, 설치를 스킵하려면 `NVIDIA_DRIVER=skip`을 사용합니다. 신규 드라이버 설치 후 커널 모듈 로드를 위해 **시스템 재부팅**이 필요합니다. `up` 명령 실행 시 노드를 자동으로 재부팅하며, `boot_id` 변경 확인을 통해 `nvidia-smi`가 동작하는 상태가 될 때까지 대기합니다 (대기 타임아웃: `REBOOT_WAIT_TRIES` × 5초, 기본값 10분). `prereqs --gpu`를 단독으로 실행할 경우 `NVIDIA_DRIVER_REBOOT=1` 옵션을 부여하지 않으면 재부팅 안내 메시지만 출력하며, 이미 드라이버가 정상 작동 중인 노드는 별도로 변경하지 않습니다.
- **Helm v3:** 미설치 시 `addons` 단계에서 자동 설치됩니다 (`get-helm-3`). 비활성화하려면 `HELM_SKIP_INSTALL=1`을 설정합니다.
- **네트워크:** 노드 간 주요 포트 개방 필요 (6443: API 서버, 10250: kubelet, 8472/udp: flannel VXLAN, 30000–32767: NodePort 범위).

## 단계별 실행 절차

### 1. 모든 노드 — 사전 조건 설정

```bash
# 컨트롤 플레인 및 CPU 전용 노드
sudo ./hack/cluster-bootstrap.sh prereqs

# GPU 워커 — nvidia-container-toolkit, 런타임 및 (nvidia-smi 미작동 시) 드라이버 설치
sudo ./hack/cluster-bootstrap.sh prereqs --gpu
```

`SystemdCgroup`이 활성화된 containerd, 필요한 커널 모듈 및 sysctl 설정, 스왑(swap) 비활성화, 그리고 kubeadm·kubelet·kubectl 1.36 버전을 설치합니다. 드라이버가 새롭게 설치된 경우 재부팅 안내가 표시되며, `NVIDIA_DRIVER_REBOOT=1` 옵션을 전달하면 즉시 재부팅을 수행합니다.

### 2. 컨트롤 플레인 — 초기화

```bash
sudo ./hack/cluster-bootstrap.sh init
```

`kubeadm init`을 실행하여 클러스터를 초기화하고 flannel CNI를 적용한 후, 워커 노드 참가에 필요한 `kubeadm join ...` 명령어를 출력합니다. 해당 명령어를 복사해 두시기 바랍니다.

### 3. 각 워커 노드 — 클러스터 참가 (Join)

```bash
sudo ./hack/cluster-bootstrap.sh join "kubeadm join 10.x.x.x:6443 --token ... --discovery-token-ca-cert-hash sha256:..."
```

### 4. 컨트롤 플레인 — 애드온 설치

```bash
./hack/cluster-bootstrap.sh addons
```

RuntimeClass(`nvidia`), HAMi, ingress-nginx(NodePort), 기본 StorageClass(`local-path`)를 설치합니다.

### 5. 컨트롤 플레인 — 노드 레이블 지정

HAMi 동작에는 `gpu=on` 레이블이, gShare 스케줄링에는 `gshare.io/gpu-mode` 레이블이 필요합니다. **`up` 스크립트를 통해 구축한 경우 `cluster-info` 설정값이 이미 적용되어 있습니다.** 따라서 본 단계는 수동으로 구성하는 경우에만 수행합니다.

```bash
./hack/cluster-bootstrap.sh label <gpu-node-1> exclusive
./hack/cluster-bootstrap.sh label <gpu-node-2> fractional
./hack/cluster-bootstrap.sh label <control-plane> cpu
```

### 6. 검증

```bash
./hack/cluster-bootstrap.sh verify
```

노드 상태가 Ready인지, `nvidia.com/gpu` 및 `nvidia.com/gpumem` 리소스 용량이 정상 할당 및 노출되는지, HAMi·ingress·flannel·local-path 파드가 Running 상태인지, 기본 StorageClass가 설정되었는지 검증합니다.

### 스토리지 노드 (선택): 실제 쿼터가 적용되는 볼륨 {#storage-node-optional-volumes-with-a-real-quota}

`local-path`는 RWO(ReadWriteOnce)만 지원하며 용량 제한을 강제하지 않습니다. 이 경우 50 GiB로 요청한 볼륨이 `df` 명령어 실행 시 노드의 전체 디스크 용량으로 표시되어 디스크 공간 전체를 사용하는 문제가 발생할 수 있습니다. 스토리지 노드를 구성하면 이러한 문제점들을 모두 해결할 수 있습니다. `cluster-info` 파일에 `STORAGE_NODE=user@ip:/dev/<device>` 항목을 설정하면 `up` 스크립트 실행 시 애드온 설치 이후 다음 작업이 자동으로 진행됩니다:

1. 해당 스토리지 노드에서 **`storage <device>`** 실행: `zfsutils-linux` 및 `nfs-kernel-server` 패키지를 설치하고 지정한 디바이스 전체에 ZFS 풀 `gshare`를 생성합니다 (`STORAGE_VDEVS`를 설정하여 여러 디바이스를 미러 또는 raidz 구성 가능). 이어서 데이터셋(`gshare/volumes`, `gshare/snapshots`)을 구성하고 ZFS ARC 용량을 `ZFS_ARC_MAX_MB`(기본값 3 GiB)로 제한합니다. SSH 키 기반으로 작동하는 `gshare-csi` 계정을 생성하며, `sudo` 권한은 드라이버에 필요한 zfs/exportfs/chown 명령어로 엄격히 제한됩니다.
2. 컨트롤 플레인에서 **`storage-csi <ip> <key>`** 실행: democratic-csi(`zfs-generic-nfs`, 설정 파일: `deploy/storage/democratic-csi-values.yaml`) 및 StorageClass **`gshare-data`**를 설치합니다. PVC마다 독립된 데이터셋을 할당하고 `refquota`를 요청 용량과 동일하게 설정하므로, 세션 내부에서 `df` 실행 시 정확한 쿼터 용량이 표시되며 초과 쓰기 시 `ENOSPC` 오류로 차단됩니다. 단일 StorageClass에서 RWO, RWX, ROX 접근 모드를 모두 지원하며, 승인된 용량 증설을 위한 `allowVolumeExpansion` 옵션이 활성화됩니다.
3. **`label <node> storage`** 실행: 해당 노드에 `gshare.io/role=storage` 레이블 및 `NoSchedule` 테인트를 부여합니다. 이를 통해 일반 세션 파드 및 제어 플레인 구성 요소가 스토리지 노드에 스케줄링되지 않도록 보호합니다.

모든 노드는 `prereqs` 단계에서 `nfs-common` 패키지가 미리 설치됩니다. 이후 `--set operator.volumeStorageClass=gshare-data` 옵션(또는 values 오버레이 파일 주석 해제)을 지정하여 오퍼레이터가 해당 StorageClass를 사용하도록 설정합니다. 오퍼레이터는 `operator.volumeSyncInterval`(기본 5분) 주기마다 각 볼륨 PVC 정보를 제어 플레인에 동기화합니다. 이 과정에서 사용 중인 바이트 수 집계, 승인된 용량 증설 요청 반영, 그리고 `api.volumeReclaimGraceHours`(기본 24시간) 기준을 초과하여 삭제된 볼륨의 PVC 및 실제 ZFS 데이터셋 회수를 처리합니다.

수동으로 설정하는 경우 순서는 다음과 같습니다:
스토리지 노드에서 `sudo STORAGE_CSI_PUBKEY="$(cat key.pub)" bash cluster-bootstrap.sh storage /dev/vdb` 명령어 실행 후, 컨트롤 플레인에서 `bash cluster-bootstrap.sh storage-csi <ip> key` 및 `bash cluster-bootstrap.sh label <node> storage` 명령어를 차례로 실행합니다.

구성되는 풀은 이중화가 없는 단일 장애점(SPOK) 구조입니다. 데이터 내구성을 보장하려면 스토리지 노드에서 주기적으로 ZFS 스냅샷을 생성하고 `zfs send` 명령을 통해 외부 백업 시스템으로 복제할 것을 권장합니다.

### 로컬 레지스트리 (선택) {#local-registry-optional}

세션 컨테이너 이미지는 5~15 GiB 규모로 용량이 큽니다. 따라서 사내 네트워크(LAN) 환경에서는 각 노드가 매번 외부 Docker Hub에서 이미지를 받기보다 로컬 컨테이너 레지스트리를 운용하는 것이 훨씬 효율적입니다. 구성은 두 부분으로 나뉘며 모두 선택 사항입니다.

1. **레지스트리 배포**: `deploy/registry/registry.yaml` 매니페스트를 통해 스토리지 노드(`gshare.io/role=storage`)에 2개의 HTTP 레지스트리를 실행합니다. 하나는 자체 빌드한 세션 이미지를 푸시하기 위한 레지스트리(`:5000`), 다른 하나는 공개 카탈로그 이미지를 최초 1회 다운로드 후 LAN 내에서 캐싱하여 제공하는 docker.io **풀스루 미러(Pull-through Mirror)**(`:5001`)입니다.
   ```bash
   kubectl apply -f deploy/registry/registry.yaml   # 레이아웃에 따라 nodeSelector / storageClassName 수정
   ```
2. **노드 신뢰 설정**: 모든 노드의 containerd에 해당 레지스트리 정보를 등록해야 합니다.

   ```bash
   sudo LOCAL_REGISTRY=<storage-ip>:5000 LOCAL_REGISTRY_MIRROR=<storage-ip>:5001 \
        bash cluster-bootstrap.sh registry     # 각 노드별 실행 (멱등성 보장)
   ```

   이 명령은 `/etc/containerd/certs.d/<host:port>/hosts.toml` 설정 파일(및 미러를 경유하도록 조율하는 `docker.io` 항목)을 생성하고, `config.toml` 내의 `config_path` 속성을 지정합니다. containerd 2.x 버전에서는 이 설정이 누락되면 `certs.d` 경로를 무시하여 이미지를 가져올 때 "server gave HTTP response to HTTPS client" 오류가 발생합니다. `up` 실행 경로에서는 `cluster-info`에 `LOCAL_REGISTRY` 항목이 정의되어 있으면 모든 노드에서 이 과정을 자동으로 처리합니다. 향후 TLS 환경으로 전환할 경우, 기존 레이아웃을 유지한 채 `hosts.toml`과 동일한 디렉터리에 CA 인증서를 배치하면 됩니다.

`"insecure-registries"` 항목에 해당 레지스트리가 등록된 Docker 호스트에서 카탈로그 이미지를 빌드 및 푸시합니다:

```bash
REG=<storage-ip>:5000 build/images/build.sh push   # 전체 카탈로그 이미지 빌드 및 LAN 레지스트리 푸시
```

이후 웹 콘솔에 해당 이미지 정보를 등록합니다 (이미지 참조 주소: `<storage-ip>:5000/gshare-session:<tag>`). 각 워커 노드는 LAN 내부 레지스트리로부터 이미지를 신속하게 다운로드합니다.

## 운영 중인 클러스터 노드 확장 및 축소 {#growing-or-shrinking-a-running-cluster}

상기 절차는 초기 구축 과정을 기준으로 설명되었으나, 모든 하위 명령은 멱등성(Idempotency)을 보장하며 독립적으로 작동합니다. 따라서 이미 세션을 서비스 중인 운영 클러스터에 언제든지 신규 노드를 추가할 수 있습니다. 노드 추가 작업은 실행 중인 워크로드에 영향을 주지 않으며 기존 노드의 상태를 변경하지 않습니다.

### 노드 추가

1. **신규 노드 사전 조건 설정.** 스왑 비활성화, 커널 모듈 및 sysctl 설정, containerd 설치, `nfs-common` 설치, GPU 노드의 경우 NVIDIA 런타임(드라이버 미설치 시 드라이버 포함) 설치:

   ```bash
   sudo ./hack/cluster-bootstrap.sh prereqs        # GPU 노드는 `prereqs --gpu` 실행
   ```

2. **컨트롤 플레인에서 join 명령어 생성 및 신규 노드에서 실행:**

   ```bash
   kubeadm token create --print-join-command       # 컨트롤 플레인에서 실행
   sudo ./hack/cluster-bootstrap.sh join "kubeadm join 10.x.x.x:6443 --token ... --discovery-token-ca-cert-hash sha256:..."
   ```

3. **컨트롤 플레인에서 노드 레이블 지정.** 신규 GPU 노드에서 리소스 용량이 인식되지 않는 가장 흔한 원인은 레이블 누락입니다. HAMi는 `gpu=on` 레이블이 지정된 노드의 GPU만 인식하며, 워크로드 배치는 `gshare.io/gpu-mode` 레이블을 참조합니다.

   ```bash
   ./hack/cluster-bootstrap.sh label <node> fractional    # 또는: exclusive | cpu | storage
   ```

4. **신규 노드 LAN 레지스트리 설정 (클러스터에서 사용 중인 경우).** `prereqs` 단독 실행 시 `LOCAL_REGISTRY` 변수를 전달하지 않으면, 수동 join된 노드는 비암호화 레지스트리 정보를 알 수 없어 이미지 다운로드 시 `http: server gave HTTP response to HTTPS client` 오류가 발생합니다. 환경 변수를 지정하여 `prereqs` 명령을 다시 실행하는 것이 안정적인 방법입니다.

   ```bash
   sudo LOCAL_REGISTRY=<registry-ip>:5000 LOCAL_REGISTRY_MIRROR=<registry-ip>:5001 \
        ./hack/cluster-bootstrap.sh prereqs
   ```

   *수동 처리 시 주의 사항:* 정상 작동 중인 노드에서 `/etc/containerd/certs.d/` 디렉터리를 복사한 후, `/etc/containerd/config.toml` 파일에 `config_path = "/etc/containerd/certs.d"` 구문을 추가합니다. 반드시 사전에 기존 설정 파일을 백업하십시오 (`cp config.toml config.toml.bak`). 또한 `sed`나 정규식 치환을 사용하는 대신 텍스트 편집기로 직접 수정하는 것을 권장합니다. 해당 파일 내에 존재하는 `plugin_config_path`와 같은 유사업종 키에 잘못된 치환이 적용되면 containerd가 정상적으로 시작되지 않습니다. **containerd 서비스 재시작은 반드시 대상 노드의 로컬 콘솔에서 직접 수행해야 합니다** (`sudo systemctl restart containerd`). 해당 노드 위에서 실행 중인 파드 내부에서 재시작 명령을 내릴 경우, containerd가 중지되면서 해당 파드도 함께 종료되어 재시작 절차가 완료되지 않으며 `kubectl exec`를 통한 복구도 불가능해집니다.

5. **검증** — 노드 Ready 상태 전환, `nvidia.com/gpu` 및 `nvidia.com/gpumem` 용량 인지, 주요 애드온 Running 상태 확인:

   ```bash
   ./hack/cluster-bootstrap.sh verify
   ```

6. **`hack/cluster-info` 파일 업데이트** (`WORKER_NODES`, `CPU_WORKERS` 등). 차후 `up` 스크립트 실행 시 설정 파일과 실제 클러스터 상태가 일치하도록 반영해 둡니다.

gShare 시스템 내부 자동 반영:

7. **별도 등록 절차 불필요.** 오퍼레이터의 인벤토리 컨트롤러가 다음 동기화 주기(tick)에 신규 노드와 GPU 카드를 자동으로 감지합니다. 제어 플레인은 (클러스터명, 호스트명) 조합으로 upsert를 수행하며, 신규 노드가 웹 콘솔의 **노드** 목록에 자동으로 등록됩니다. 노드 하트비트 신호 수신 시 `node_liveness` 상태가 `ready`로 전환됩니다 (하트비트 중단 시 `NODE_STALE_SEC` 기준, 기본 5분 후 `offline`으로 전환).

8. **해당 GPU 모델의 오퍼링(Offering) 확인.** 시스템 승인 로직은 `offering.gpu_model`과 실제 디바이스 모델명을 **문자열로 정확히 비교**합니다. 따라서 활성화된 오퍼링이 없는 새로운 GPU 모델 카드는 관리자 화면에만 노출될 뿐 실제 세션 할당 시 `409 unserviceable` 에러가 발생하며 사용할 수 없습니다. **자원 → GPU 오퍼링** 메뉴의 카탈로그 목록에서 "클러스터 보유" 태그를 통해 어떤 모델이 실물 GPU 카드로 등록되어 있는지 확인하십시오. 신규 노드의 용량을 오픈하기 전에 해당 GPU 모델의 오퍼링을 새로 생성하거나 활성화해야 합니다.

9. **웹 콘솔 추가 설정 (선택 사항):**
   - **노드 풀(Node Pool) 배정** — 특정 부서나 프로젝트 전용으로 할당해야 하는 경우 해당 노드를 전용 풀로 지정합니다. 미배정 노드는 공유 풀로 동작합니다.
   - **세션 이미지 미리 가져오기(Pre-pull)** — 사용자가 첫 세션을 생성할 때 대용량 이미지(5~15 GiB) 다운로드 대기 시간을 줄여줍니다 (LAN 레지스트리가 구성된 경우 빨라지지만 즉시 시작을 위해 권장).
   - **무손실 일시 중지 기능 설정** — CRIU 및 cuda-checkpoint 설정이 준비된 경우 대상 노드에 `gshare.io/criu=ready` 및 `gshare.io/cuda-checkpoint=ready` 레이블을 부여합니다. 레이블이 없으면 해당 노드의 세션은 콜드(Cold) 일시 중지 방식으로 대체됩니다.

### 노드 제거

먼저 워크로드를 다른 노드로 비우는 Drain 작업을 진행한 후 노드를 삭제합니다. 원장(Ledger)에 이미 제거된 하드웨어의 세션 정보가 잔재로 남아 있어서는 안 됩니다.

1. **웹 콘솔 사전 조치** — 해당 노드에 잔여 세션이 남아 있다면 정산 처리가 이루어지도록 세션을 종료하거나 일시 중지합니다 (세션 목록에서 노드로 필터링).
2. **컨트롤 플레인에서 다음 명령어 실행:**

   ```bash
   kubectl cordon <node>
   kubectl drain <node> --ignore-daemonsets --delete-emptydir-data --timeout=300s
   kubectl delete node <node>
   ```

   DaemonSet(calico, kube-proxy, HAMi 디바이스 플러그인, dcgm-exporter, node-exporter, CSI 노드 플러그인 등) 파드가 남아 있는 것은 정상 동작입니다. `--ignore-daemonsets` 옵션이 이를 처리합니다.
3. **제거 대상 노드에서 (영구 축출 시):** `sudo kubeadm reset -f` 실행 및 `/etc/cni/net.d` 디렉터리를 정리합니다.
4. **웹 콘솔에서 노드 삭제** — 하트비트 수신이 중지되어 `node_liveness` 상태가 `offline`으로 변경되면 콘솔에 삭제 버튼이 활성화됩니다. 아직 활성 할당이나 종료되지 않은 세션이 남아 있는 경우 `409 node_busy` 에러와 함께 거부됩니다. 삭제 시 노드 및 GPU 카드 기록은 지워지지만 과금 이력 데이터는 보존되며, 과거 할당 이력은 삭제된 카드와 분리된 채 `gpu_uuid` 정보를 유지합니다.
5. **후속 정리** — 전용 풀의 모든 노드가 제거된 경우 해당 풀은 빈 상태로 유지됩니다. 불필요 시 풀을 삭제하거나 다른 노드를 새로 할당하십시오. 전용 풀이 비워진 테넌트의 세션은 오버플로우 정책이 허용(`shared_pool`)되어 있다면 공유 노드로 전환되어 정상 실행됩니다.

클러스터에 여전히 접속된 라이브 노드를 콘솔에서 임의 삭제하는 것은 인벤토리 보고에 의해 즉시 재등록되므로 무의미합니다.

## 다음 절차 — gShare 배포

클러스터 구성이 완료된 후 가장 간편한 배포 방식은 올인원(All-in-one) 패키지를 사용하는 것입니다. 해당 헬름 차트는 데이터 계층, 시크릿, CRD, 네임스페이스, 오퍼레이터 내부 JWT 생성 및 로컬 클러스터 등록까지 추가 수동 작업 없이 일괄 처리합니다.

```bash
make deploy-incluster                          # deploy/values/incluster.yaml
ADMIN_JWT=$(./hack/bootstrap-superadmin.sh)    # 선택: 관리자 API 호출용 super_admin 토큰
```

클러스터 전면에 리버스 프록시를 배치하여 콘솔 도메인의 TLS를 종단하고, 내부 ingress-nginx NodePort(`:30080`, HTTP)로 트래픽을 전달하도록 구성합니다. 외부 CloudNativePG, Redis, external-secrets를 활용하는 프로덕션 환경 배포는 `deploy/values/dockerhub.yaml` 파일과 함께 `make prod-deploy` 명령을 사용하십시오.

## 주의 사항

- 본 스크립트는 **검증된 표준 스택 환경을 재현**하도록 구성되어 있습니다. 모든 환경에서 별도 수정 없이 100% 동작하는 것을 보장하지는 않으며, 드라이버 버전, 커널, 사내 프록시 및 레지스트리, 방화벽 정책 등에 따라 적절한 사전 조정이 필요할 수 있습니다. 각 주요 단계 완료 후 반드시 `verify` 하위 명령으로 검증을 수행하십시오.
- **스크립트 재실행 시 멱등성을 보장합니다.** `prereqs`, `init`, `join`, `addons` 등의 명령은 안전하게 재실행할 수 있습니다. 키링 파일은 덮어쓰기 처리되고, swap 설정 구문은 중복 처리되지 않으며, 애드온은 `apply` 및 `helm upgrade -i` 방식으로 업데이트됩니다. `init` 명령은 API 서버의 `/healthz` 엔드포인트를 헬스체크하여 작동 여부를 판단합니다. 이미 정상 구동 중이면 초기화를 건너뛰고, 포트 점유·매니페스트 잔재·etcd 데이터 등 이전 실행 기록만 감지될 경우 `kubeadm reset -f`를 수행한 후 재초기화합니다 (`INIT_FORCE_RESET=0` 설정 시 초기화 대신 경고 메시지 출력). `join` 명령은 `kubelet.conf` 파일이 이미 존재하는 경우 실행을 건너뜁니다. **단, 예외 사항으로** containerd 설정 파일은 실행 시 기본 템플릿으로부터 매번 재생성되므로 수동으로 추가한 기존 편집 내용이 유실될 수 있습니다.
- HAMi 스케줄러 이미지 태그는 Kubernetes 클러스터 버전에 맞춰 자동 지정되지만(`scheduler.kubeScheduler.imageTag`), 적용 전에 공식 HAMi 호환성 매트릭스를 직접 확인하는 것을 권장합니다.
- 프로덕션 환경의 고도화 작업(다중 컨트롤 플레인 구성, RWX 볼륨을 위한 CephFS/NFS 도입, Vault/KMS 연동 external-secrets, Kyverno 및 cosign을 활용한 서명 검증 등)은 본 자동화 스크립트의 제공 범위를 벗어납니다. 해당 내용은 프로젝트 루트의 [`README.md`](../README.md) 참조 구성을 확인해 주시기 바랍니다.
---
sidebar_position: 4
title: 멀티 클러스터
---
# 여러 클러스터에서 gShare 운영하기

제어 플레인 하나, GPU 클러스터 여럿. 제어 플레인은 사용자, 돈, 결정을 쥐고, 각 클러스터는 그
결정을 파드로 바꾸고 실제로 일어난 일을 보고하는 오퍼레이터를 돌립니다.

이 문서는 운영자 가이드입니다. 무엇이 갖춰져야 하는지, 무엇을 실행하는지, 잘 됐는지 어떻게
아는지.

---

## 각 쪽의 책임

| | 제어 플레인 클러스터 | 데이터 플레인 클러스터 |
|---|---|---|
| 실행 | api, worker, 콘솔, Postgres, Redis | 오퍼레이터만 |
| 보유 | 사용자, 크레딧, 정책, 세션 기록, 모든 클러스터의 자격 증명 | GPU, 세션 파드, 자체 인그레스 |
| 통신 대상 | 등록한 kubeconfig로 각 클러스터의 apiserver | 제어 플레인의 `/internal` 경로 |

시작 전에 짚어 둘 두 가지 결과:

- **각 클러스터는 자기 세션 URL을 서비스합니다.** 세션 주소는 세션이 도는 클러스터의 호스트명입니다.
  그 클러스터의 인그레스가 파드로 라우팅하기 때문입니다. 호스트명은 클러스터마다 줍니다. 전역
  하나는 없습니다.
- **제어 플레인은 데이터 플레인에서 닿아야 하고, 그 반대도 마찬가지입니다.** 오퍼레이터는 상태
  보고를 위해 콜백하고, 제어 플레인은 세션 리소스 적용을 위해 apiserver를 호출합니다.

---

모든 오퍼레이터 토큰은 `operator:<cluster_id>`로 발급되고 제어 플레인은 각 콜백을 거기에 묶습니다.
상태 보고, 인벤토리 upsert, 사용량 샘플 배치는 토큰에 적힌 클러스터의 세션·노드에 대해서만
받아들여집니다(아니면 `403 forbidden`). 따라서 침해된 클러스터는 자기 세션에 대해서는 거짓말할 수
있어도 남의 세션에 대해서는 할 수 없습니다.

---

## 전제 조건

**제어 플레인에서** 내부 플레인이 데이터 플레인 클러스터에서 닿아야 합니다. 기본은 닫혀 있으며,
단일 클러스터 설치에는 그것이 맞습니다.

```bash
helm upgrade gshare charts/gshare -n gshare-system --reuse-values \
  --set ingress.internalPlane.enabled=true \
  --set ingress.internalPlane.sourceRange="10.0.0.0/8"
```

`/internal`과 `/.well-known`만 열립니다. 둘 다 이미 RS256 내부 JWT를 요구하므로 인증 없는 표면은
아니지만 — 그래도 `sourceRange`를 클러스터가 실제로 있는 네트워크로 제한하세요.

확인:

```bash
curl -s https://gshare.example.com/.well-known/gshare-internal-jwks.json | head -c 40
# {"keys":[{"alg":"RS256", ...     ← 콘솔 HTML이 아니라 진짜 키
```

**새 클러스터의 각 GPU 노드에서** 세 가지가 이미 동작해야 합니다. 연결 스크립트가 셋 다 확인하고
빠진 것이 있으면 해결 방법과 함께 멈춥니다. 어느 것도 원격으로 할 수 없기 때문입니다.

```bash
nvidia-smi                                              # 드라이버
nvidia-ctk --version                                    # 컨테이너 툴킷
sudo containerd config dump | grep nvidia-container-runtime   # containerd에 런타임 등록
```

마지막 줄이 아무것도 출력하지 않으면:

```bash
sudo nvidia-ctk runtime configure --runtime=containerd && sudo systemctl restart containerd
```

드라이버가 아예 없으면 그 노드에서 `sudo ./hack/cluster-bootstrap.sh prereqs --gpu`. 보통 재부팅이
필요합니다.

**새 클러스터의 kubeconfig**는 `server:`가 실제 네트워크 주소여야 합니다. kubeadm의 `admin.conf`는
흔히 `127.0.0.1`이라 그 노드에서만 동작하는데, 제어 플레인도 닿아야 합니다. 시작 전에 고치세요.

```bash
grep server: remote.kubeconfig     # localhost가 아니라 노드의 LAN 주소여야 함
```

---

## 클러스터 연결

```bash
./hack/attach-cluster.sh \
  --kubeconfig ~/remote.kubeconfig \
  --name lab-c2 \
  --control-plane https://gshare.example.com \
  --session-domain gshare.lab-c2.example.com \
  --ingress-node master-c2 \
  --storage-values ~/csi-values.yaml     # 선택, "볼륨과 스토리지" 참고
```

`--session-domain`은 이 클러스터의 ingress-nginx가 도는 노드로 해석되어야 하는 호스트명입니다. 이
클러스터의 세션은 거기로 안내됩니다.

**현재 kube 컨텍스트는 제어 플레인을 가리켜야** 합니다. 오퍼레이터 토큰이 거기서 서명되기
때문입니다 — 서명 키는 절대 그곳을 떠나지 않습니다. 원격 클러스터는 `--kubeconfig`로만 지정합니다.

스크립트는 멱등합니다. 다시 실행하는 것이 반쯤 끝난 연결을 고치거나 오퍼레이터를 올리는 공식
방법입니다. 하는 일:

1. kubeconfig가 클러스터에 닿고 localhost를 가리키지 않는지 확인.
2. 모든 GPU 노드의 드라이버와 containerd nvidia 런타임 확인.
3. `nvidia` RuntimeClass 생성, GPU 노드 라벨(`gpu=on`, `gshare.io/gpu-mode`).
4. HAMi 설치(스케줄러 이미지를 클러스터의 Kubernetes 버전에 고정), GPU가 실제로 광고될 때까지
   대기.
5. ingress-nginx 설치(이미 있으면 `--skip-ingress`).
6. 제어 플레인에 클러스터 등록. 제어 플레인은 받아들이기 전에 프로브합니다.
7. 오퍼레이터 배포, 제어 플레인에서 토큰 발급·주입.
8. `--storage-values`가 있으면: 모든 노드의 NFS 클라이언트 확인, 공유 풀에 대해 democratic-csi
   설치, 오퍼레이터를 그 StorageClass로 지정. 없으면 건너뜀.
9. 연결 테스트 실행, 첫 인벤토리 보고 대기.

---

## 검증

```bash
# 클러스터가 응답하며, 제어 플레인이 신경 쓰는 런타임 검사 결과 포함
curl -sX POST https://gshare.example.com/api/v1/clusters/$CID/connection-test \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
# → {"status":"connected","checks":{"runtime_class_nvidia":true,"hami_device_plugin":true,...}}
```

그다음 콘솔에서: 상단 바 선택기에 클러스터가 나타나고, 노드 관리에 노드가, GPU 관리에 카드가
나타납니다. 상단 바에서 클러스터를 고르면 관리자 화면이 그것으로 좁혀집니다.

진짜 테스트는 세션입니다. 새 클러스터에 고정해 하나 만들고 열어 보세요. URL에 새 클러스터의
호스트명이 있어야 합니다. 제어 플레인의 것이면 `session_domain`이 설정되지 않은 것입니다.

---

## 볼륨과 스토리지 {#volumes-and-storage}

gShare 볼륨은 클러스터에 묶이지 않습니다. 볼륨은 소유자와 쿼터를 가지고, 세션이 배치된 클러스터의
오퍼레이터가 PVC를 만듭니다. 이것은 **모든 클러스터가 같은 풀을 마운트**할 때만 성립합니다 —
NFS/ZFS 서버 하나, 클러스터당 democratic-csi 드라이버 하나, 모두 그것을 가리킴. 클러스터별
스토리지는 각 사용자를 데이터가 있는 클러스터에 묶어 버리는데, 공유 플릿의 목적과 정반대입니다.

제어 플레인 클러스터에서는 `cluster-bootstrap.sh`가 드라이버를 설치했습니다. 연결된 클러스터에는
그 값을 내보내 같은 드라이버를 설치합니다.

```bash
# 제어 플레인에서: 스토리지 서버에 쓰는 SSH 키를 포함한 드라이버 설정
helm -n gshare-storage get values gshare-storage > csi-values.yaml && chmod 600 csi-values.yaml
# 딱 하나 수정: controller.nodeSelector → 새 클러스터의 노드(프로비저너가 거기서 돕니다)
./hack/attach-cluster.sh ... --storage-values csi-values.yaml
```

값 파일에는 스토리지 서버의 SSH 키가 들어 있습니다. 저장소 밖에 두고 연결이 끝나면 삭제하세요.

### 풀 등록

풀은 노드 역할에서 추론하는 것이 아니라 등록하는 객체입니다. `POST /api/v1/storage/pools`로
(아직 콘솔 화면은 없습니다) 다음 값과 함께 등록합니다.

- **클러스터** — 스토리지 서버가 있는 클러스터;
- **스토리지 클래스** — 거기서 프로비저닝하는 클래스. 오퍼레이터에 `--volume-storage-class`로 준
  것과 같은 이름;
- **공유** — 플릿의 모든 클러스터에 `all`(NFS 서버 하나를 전체에 내보내는 보통의 형태), 또는
  `selected`와 볼륨을 둘 수 있는 클러스터 목록.

**스토리지 서버 여러 대는 풀 하나가 아닙니다.** 볼륨은 정확히 하나에 존재합니다 — PVC가 지정한
StorageClass가 위치를 정하고 gShare는 아무것도 고르지 않습니다. 따라서 용량 게이트와 대시보드는
합계가 아니라 배치가 쓸 수 있는 *가장 큰* 풀을 상한으로 삼습니다. 2 TB 서버 두 대를 더해 4 TB
볼륨을 허가하면 어느 쪽도 담을 수 없습니다.

### 용량 값의 출처

순서대로, 그리고 각 값은 어느 출처를 썼는지 표시합니다.

1. **`csi`** — 드라이버의 `GetCapacity`. external-provisioner가 `CSIStorageCapacity` 객체로
   발행하고 오퍼레이터가 볼륨 동기화 틱마다 읽습니다. 유일한 자동 소스입니다. 다른 어느 것도
   노드 루트 디스크 너머를 볼 수 없습니다.
2. **`manual`** — 풀에 적어 둔 값(`manual_capacity_gb`). 제어 플레인 전체의
   `STORAGE_POOL_CAPACITY_GB`는 단일 풀 설치의 플릿 기본값으로 여전히 동작합니다.
3. **`node_disk`** — 스토리지 노드의 시스템 드라이브. 대용이며 그렇게 표시됩니다. ZFS 서버에서는
   풀과 다른 디스크라 수백 GB 차이가 날 수 있습니다.

`attach-cluster.sh`는 `csiDriver.storageCapacity=true`를 설정해 용량을 지원하는 드라이버가 발행을
시작하게 합니다. 모든 드라이버가 지원하지는 않으며, 프로비저너에도 `--enable-capacity`,
`--capacity-for-immediate-binding=true`(우리 StorageClass는 즉시 바인딩)와 노드 토폴로지를
보고하는 드라이버가 필요합니다. 토폴로지가 없으면 객체가 갱신마다 생성·삭제를 반복합니다. 아무것도
발행되지 않으면 풀은 적어 둔 용량을 유지하고, 대시보드는 측정한 척하지 않고 `manual`이라고
말합니다.

연결된 클러스터의 전제 — 스크립트가 둘 다 확인하고 빠지면 해결 방법과 함께 멈춥니다.

- **모든 노드에 NFS 클라이언트**(Debian/Ubuntu는 `nfs-common`, RHEL은 `nfs-utils`): 드라이버는
  세션이 도는 노드에 풀을 마운트합니다. `mount.nfs`가 없는 노드는 세션을 `ContainerCreating`에
  묶어 둡니다.
- **모든 노드에서 스토리지 서버로의 네트워크 경로** 2049/tcp(NFSv3 내보내기라면 111/tcp,
  20048/tcp도). 다른 서브넷의 노드는 내보내기의 허용 범위에도 있어야 합니다.

관리자 대시보드의 스토리지 타일은 풀을 플릿 전체로 읽고, 클러스터를 선택하면 *클러스터 간 공유*라고
표시합니다. 풀이 어느 한 클러스터의 것이 아니기 때문입니다. 제어 플레인의
`STORAGE_POOL_CAPACITY_GB`가 풀의 실제 크기를 말하고, 없으면 타일은 스토리지 노드의 디스크로
대체합니다.

---

## 토큰 회전

오퍼레이터 토큰은 7일 유효합니다. 지금은 아무것도 자동 회전하지 않으며, 만료되면 오퍼레이터
콜백이 401로 실패하기 시작합니다 — 파드는 계속 도는데 세션 기록이 갱신되지 않는, 디버그하기
혼란스러운 상태. 스케줄에 올리세요.

```bash
# 제어 플레인에서, 하루 한 번
CID=clu_...
TOKEN=$(kubectl -n gshare-system exec deploy/gshare-api -c api -- python -c \
  "from app.auth.internal_jwt import sign_internal_jwt; print(sign_internal_jwt('operator:$CID', ttl=604800))")
printf '%s' "$TOKEN" | KUBECONFIG=~/remote.kubeconfig kubectl -n gshare-system \
  create secret generic gshare-operator-internal-jwt --from-file=internal-jwt=/dev/stdin \
  --dry-run=client -o yaml | KUBECONFIG=~/remote.kubeconfig kubectl apply -f -
```

오퍼레이터는 시도마다 파일을 다시 읽으므로 재시작이 필요 없습니다.

---

## 안 될 때

**클러스터는 등록되는데 노드가 안 보입니다.** 오퍼레이터가 제어 플레인에 닿지 못합니다. 로그를
보고, `internalPlane`이 켜져 있고 `sourceRange`에 클러스터가 포함되는지 확인하세요.

```bash
KUBECONFIG=~/remote.kubeconfig kubectl -n gshare-system logs deploy/gshare-operator --tail=50
```

**등록이 런타임 오류로 거부됩니다.** 프로브가 `nvidia` RuntimeClass나 HAMi를 찾지 못했습니다. 둘 다
연결 스크립트가 설치합니다. 손으로 등록했다면 먼저 설치하세요.

**등록이 멈췄다가 unreachable로 실패합니다.** kubeconfig의 apiserver 주소가 *제어 플레인
파드에서* 닿지 않습니다. 프로브는 거기서 돌지 노트북에서 돌지 않습니다. 포기까지 몇 분 걸립니다.

**세션은 시작되는데 URL이 404입니다.** `session_domain`이 비어 있거나 잘못된 호스트를 가리켜,
사용자가 그 세션의 경로가 없는 클러스터 인그레스로 보내집니다.

```bash
curl -sX PATCH https://gshare.example.com/api/v1/clusters/$CID \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"session_domain":"gshare.lab-c2.example.com"}'
```

**세션은 시작되는데 연결하면 401입니다.** 세션의 인그레스가 제어 플레인에 연결 토큰 검증을
요청하므로, 오퍼레이터만이 아니라 *데이터 플레인 클러스터의 인그레스 컨트롤러*도
`/internal/connect/verify`에 닿아야 합니다.

---

## 클러스터 제거

```bash
curl -sX DELETE https://gshare.example.com/api/v1/clusters/$CID -H "Authorization: Bearer $TOKEN"
```

살아 있는 세션이나 할당이 있으면 거부됩니다 — 먼저 종료하세요. 등록 해제는 노드와 디바이스를
지우고, 세션 이력은 원장이 참조하므로 남습니다.

---

## 알려진 제한

- **Prometheus는 클러스터별이 아니라 제어 플레인 전체입니다.** 모니터링 화면은 Prometheus 하나를
  읽습니다. 연결된 클러스터의 노드·카드는 페더레이션하거나 두 번째 스크레이프 대상을 추가하기
  전까지 거기 나타나지 않습니다. 대시보드·노드·카드·세션 화면은 영향 없습니다 — 제어 플레인 자체
  인벤토리(클러스터별)를 읽습니다.
- **토큰 회전은 수동입니다.** 위 참고.
- **이미지는 클러스터별입니다.** 세션 이미지는 세션이 배치되는 클러스터에서 풀 가능해야 합니다.
  모든 클러스터가 닿는 레지스트리에 올리거나 클러스터마다 미리 적재하세요.
- **볼륨은 처음 마운트한 클러스터에 머뭅니다.** PersistentVolume 객체는 클러스터별이므로 PVC가
  클러스터 A에 있는 볼륨을 클러스터 B의 세션이 마운트할 수 없습니다 — 스케줄러는 그런 세션을 A에
  두고 B를 명시한 요청은 거부합니다(`409 volume_on_another_cluster`). 데이터는 공유 풀에 있지만
  두 번째 클러스터의 PVC에 바인딩하는 것은 아직 자동화되지 않았습니다.
- **자격 증명은 제자리에서 회전할 수 없습니다.** 클러스터 kubeconfig를 갱신하려면 등록 해제 후
  재등록해야 하며, 새 클러스터 id — 따라서 새 오퍼레이터 토큰과 갱신할 Helm 값 — 가 생깁니다.

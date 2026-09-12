---
sidebar_position: 4
title: 멀티 클러스터
---
# 여러 클러스터에서 gShare 운영하기

단일 제어 플레인(Control Plane)과 다수의 GPU 클러스터(Data Plane) 환경을 구성합니다. 제어 플레인은 사용자 계정, 자산/크레딧, 중앙 정책 및 리소스 할당을 관장하며, 각 데이터 플레인 클러스터는 해당 결정을 실제 워크로드 파드로 변환하고 수행 상태를 보고하는 오퍼레이터(Operator)를 실행합니다.

본 문서는 클러스터 운영자를 위한 가이드로, 사전 요구 사항, 실행 절차 및 정상 작동 검증 방법을 안내합니다.

---

## 각 영역별 역할 및 책임

| 구분 | 제어 플레인 클러스터 | 데이터 플레인 클러스터 |
|---|---|---|
| 실행 요소 | api, worker, 콘솔, Postgres, Redis | 오퍼레이터 (Operator) 단독 실행 |
| 보유 리소스 | 사용자, 크레딧, 정책, 세션 기록, 전체 클러스터 접근 자격 증명 | GPU 리소스, 세션 파드, 자체 인그레스 (Ingress) |
| 통신 대상 | 등록된 kubeconfig 기반 각 클러스터의 apiserver | 제어 플레인의 `/internal` 엔드포인트 |

- **독립적인 세션 URL 제공**: 각 데이터 플레인 클러스터는 자신만의 세션 URL을 서비스합니다. 세션 접속 주소는 워크로드가 실행되는 클러스터의 호스트명으로 지정되며, 해당 클러스터의 인그레스가 파드로 트래픽을 라우팅합니다. 전역 단일 도메인이 아닌 클러스터별 전용 도메인을 부여합니다.
- **양방향 통신 요구 사항**: 제어 플레인과 데이터 플레인 간 양방향 네트워크 연결이 필요합니다. 오퍼레이터는 상태 보고를 위해 제어 플레인을 콜백하며, 제어 플레인은 세션 리소스 반영을 위해 대상 클러스터의 apiserver를 호출합니다.

> **보안 아키텍처**
> 모든 오퍼레이터 인증 토큰은 `operator:<cluster_id>` 형태로 발급되며, 제어 플레인은 해당 토큰을 기반으로 콜백 요청을 검증합니다. 상태 보고, 인벤토리 갱신(upsert), 사용량 메트릭 수집은 토큰에 명시된 클러스터의 세션 및 노드에 대해서만 허용됩니다 (위반 시 `403 Forbidden`). 이를 통해 특정 클러스터가 침해되더라도 타 클러스터의 세션에 대한 위변조를 방지합니다.

---

## 사전 요구 사항

### 1. 제어 플레인 엔드포인트 개방
데이터 플레인 클러스터에서 제어 플레인의 내부 엔드포인트에 접근할 수 있어야 합니다. 기본 설치 환경에서는 외부 접근이 차단되어 있으므로 아래와 같이 설정을 변경합니다.

```bash
helm upgrade gshare charts/gshare -n gshare-system --reuse-values \
  --set ingress.internalPlane.enabled=true \
  --set ingress.internalPlane.sourceRange="10.0.0.0/8"
```

`/internal` 및 `/.well-known` 경로가 개방됩니다. 해당 엔드포인트는 RS256 내부 JWT 검증을 거치지만, 보안 강화를 위해 `sourceRange`를 실제 데이터 플레인 클러스터가 위치한 CIDR 대역으로 제한하는 것을 권장합니다.

```bash
# 정상 개방 여부 확인 (HTML이 아닌 JWKS JSON 키가 반환되어야 함)
curl -s [https://gshare.example.com/.well-known/gshare-internal-jwks.json](https://gshare.example.com/.well-known/gshare-internal-jwks.json) | head -c 40
# {"keys":[{"alg":"RS256", ...
```

### 2. 신규 데이터 플레인 노드 구성
각 GPU 노드에서 다음 3가지 항목이 정상 작동해야 합니다. 연동 스크립트 실행 시 각 항목을 자동으로 검증합니다.

```bash
nvidia-smi                                              # GPU 드라이버
nvidia-ctk --version                                    # 컨테이너 툴킷
sudo containerd config dump | grep nvidia-container-runtime   # containerd 런타임 등록 확인
```

containerd 런타임이 등록되지 않은 경우:

```bash
sudo nvidia-ctk runtime configure --runtime=containerd && sudo systemctl restart containerd
```

GPU 드라이버가 누락된 노드의 경우 아래 명령으로 필수 패키지를 설치합니다 (설치 후 시스템 재부팅 필요).

```bash
sudo ./hack/cluster-bootstrap.sh prereqs --gpu
```

### 3. Kubeconfig 엔드포인트 검증
신규 클러스터의 `kubeconfig` 내 `server:` 주소는 루프백(`127.0.0.1`)이 아닌 실제 네트워크 접근 가능한 LAN/WAN IP여야 합니다.

```bash
grep server: remote.kubeconfig     # localhost가 아닌 노드의 실제 접근 가능 IP 확인
```

---

## 클러스터 연동

```bash
./hack/attach-cluster.sh \
  --kubeconfig ~/remote.kubeconfig \
  --name lab-c2 \
  --control-plane [https://gshare.example.com](https://gshare.example.com) \
  --session-domain gshare.lab-c2.example.com \
  --ingress-node master-c2 \
  --storage-values ~/csi-values.yaml     # 선택 사항, "볼륨 및 스토리지" 절 참조
```

`--session-domain`은 대상 클러스터의 ingress-nginx가 바인딩된 노드로 라우팅되는 호스트명입니다. 해당 클러스터에서 생성된 모든 세션은 이 도메인을 통해 접속합니다.

> **주의**: 현재 실행 중인 `kubectl` 컨텍스트는 **제어 플레인**을 가리키고 있어야 합니다. 오퍼레이터 토큰이 제어 플레인에서 서명되기 때문입니다. 연동 대상 원격 클러스터는 `--kubeconfig` 파라미터로 지정합니다.

스크립트는 멱등성(Idempotency)을 보장하므로 실패 시 재실행이 가능합니다. 주요 자동화 작업:

1. kubeconfig 네트워크 연동 및 IP 유효성 검증
2. GPU 노드 드라이버 및 containerd nvidia 런타임 상태 점검
3. `nvidia` RuntimeClass 생성 및 GPU 노드 레이블 부여 (`gpu=on`, `gshare.io/gpu-mode`)
4. HAMi 설치 (Kubernetes 버전에 맞춰 스케줄러 이미지 고정) 및 GPU 디바이스 할당 대기
5. ingress-nginx 배포 (기존 설치 시 `--skip-ingress` 옵션 활용)
6. 제어 플레인에 클러스터 등록 및 헬스 체크 프로브 수행
7. 오퍼레이터 배포 및 내부 JWT 토큰 발급/주입
8. `--storage-values` 지정 시: NFS 클라이언트 상태 점검, democratic-csi 배포, 오퍼레이터 StorageClass 지정

---

## 연동 검증

```bash
# 제어 플레인에서 연동 클러스터의 런타임 헬스 체크 실행
curl -sX POST [https://gshare.example.com/api/v1/clusters/$CID/connection-test](https://gshare.example.com/api/v1/clusters/$CID/connection-test) \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
# 정상 응답 예시: {"status":"connected","checks":{"runtime_class_nvidia":true,"hami_device_plugin":true,...}}
```

검증 완료 후 콘솔 UI 상단 클러스터 선택기에 신규 클러스터가 추가되며, 노드 및 GPU 디바이스 관리에 관련 리소스가 정상 표시됩니다.

실제 워크로드 생성 테스트 시, 신규 클러스터를 지정하여 세션을 생성하고 접속 URL의 호스트명이 지정한 `session_domain`과 일치하는지 확인합니다.

---

## 볼륨 및 스토리지

gShare 볼륨은 특정 클러스터에 귀속되지 않으며 독립된 소유권과 쿼터를 가집니다. 워크로드가 배치된 클러스터의 오퍼레이터가 이에 대응하는 PVC를 동적으로 생성합니다. 따라서 **모든 클러스터가 동일한 공유 스토리지 풀(NFS/ZFS)을 마운트**하는 아키텍처를 권장합니다.

```bash
# 제어 플레인에서 기존 스토리지 드라이버 설정 추출
helm -n gshare-storage get values gshare-storage > csi-values.yaml && chmod 600 csi-values.yaml

# csi-values.yaml 내 controller.nodeSelector 항목을 신규 클러스터 노드로 수정한 후 연동 실행
./hack/attach-cluster.sh ... --storage-values csi-values.yaml
```

### 스토리지 풀 등록

콘솔 UI(**자원 → 볼륨 관리 → 스토리지 풀**) 또는 API(`POST /api/v1/storage/pools`)를 통해 스토리지 풀을 등록합니다.

- **클러스터**: 스토리지 서버가 위치한 원천 클러스터
- **스토리지 클래스**: 해당 풀에서 사용하는 StorageClass 명칭
- **공유 범위**: 전체 클러스터 대상 `all`, 또는 특정 클러스터 지정 `selected`

> **스토리지 용량 산정 방식**
> 다수의 스토리지 서버를 하나의 풀로 합산하여 관리하지 않습니다. 단일 볼륨은 정해진 하나의 스토리지 풀에 위치하므로, 용량 제한 및 할당 정책은 각 스토리지 풀의 **최대 가용 용량**을 기준으로 평가됩니다.

### 용량 산정 데이터 원천

1. **`csi`**: CSI 드라이버의 `GetCapacity` 메트릭 (`CSIStorageCapacity` 객체 기준, 자동 측정)
2. **`manual`**: 스토리지 풀 등록 시 직접 입력한 명시적 용량 (`manual_capacity_gb`)
3. **`node_disk`**: 스토리지 노드의 루트 디스크 용량 (대체 메트릭)

### 스토리지 연결 사전 조건

- **모든 노드에 NFS 클라이언트 설치**: Debian/Ubuntu (`nfs-common`), RHEL/Rocky (`nfs-utils`). 미설치 시 세션 파드가 `ContainerCreating` 상태에 멈추게 됩니다.
- **네트워크 방화벽 개방**: 스토리지 서버 간 `2049/tcp` (NFSv3 사용 시 `111/tcp`, `20048/tcp` 추가 개방) 포트 통신이 가능해야 합니다.

---

## 오퍼레이터 토큰 로테이션

오퍼레이터 내부 JWT 인증 토큰의 유효 기간은 7일입니다. 주기적인 로테이션을 권장하며, 토큰 만료 시 콜백 통신이 `401 Unauthorized`로 거부됩니다.

```bash
# 제어 플레인 환경에서 주기적(1일 1회 등)으로 토큰 재발급 및 반영
CID=clu_...
TOKEN=$(kubectl -n gshare-system exec deploy/gshare-api -c api -- python -c \
  "from app.auth.internal_jwt import sign_internal_jwt; print(sign_internal_jwt('operator:$CID', ttl=604800))")
printf '%s' "$TOKEN" | KUBECONFIG=~/remote.kubeconfig kubectl -n gshare-system \
  create secret generic gshare-operator-internal-jwt --from-file=internal-jwt=/dev/stdin \
  --dry-run=client -o yaml | KUBECONFIG=~/remote.kubeconfig kubectl apply -f -
```

오퍼레이터는 런타임에 시크릿 파일을 수시로 다시 읽어들이므로 프로세스 재시작이 필요하지 않습니다.

---

## 트러블슈팅

- **클러스터 등록 완료 후 노드가 미표시되는 경우**: 오퍼레이터가 제어 플레인에 연결하지 못하는 상태입니다. `internalPlane.enabled` 및 `sourceRange` 방화벽 설정을 재확인합니다.
  ```bash
  KUBECONFIG=~/remote.kubeconfig kubectl -n gshare-system logs deploy/gshare-operator --tail=50
  ```
- **런타임 오류로 등록이 거부되는 경우**: `nvidia` RuntimeClass 또는 HAMi 디바이스 플러그인 미설치 상태입니다.
- **연동 시 Unreachable 에러로 타임아웃 발생하는 경우**: `kubeconfig`에 기술된 apiserver IP가 제어 플레인 파드에서 라우팅 불가능한 주소인지 점검합니다.
- **세션 생성 후 URL 접속 시 404가 발생하는 경우**: `session_domain` 설정값이 누락되었거나 대상 클러스터의 인그레스 도메인과 불일치하는 상태입니다.
  ```bash
  curl -sX PATCH [https://gshare.example.com/api/v1/clusters/$CID](https://gshare.example.com/api/v1/clusters/$CID) \
    -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
    -d '{"session_domain":"gshare.lab-c2.example.com"}'
  ```
- **세션 접속 시 401 Unauthorized가 발생하는 경우**: 데이터 플레인 인그레스 컨트롤러에서 제어 플레인의 `/internal/connect/verify` 엔드포인트로의 인증 요청 트래픽이 차단되었는지 확인합니다.

---

## 클러스터 해제

```bash
curl -sX DELETE [https://gshare.example.com/api/v1/clusters/$CID](https://gshare.example.com/api/v1/clusters/$CID) -H "Authorization: Bearer $TOKEN"
```

실행 중인 세션이나 할당된 리소스가 남아 있는 경우 해제가 거부되므로 사전 세션 종료가 필요합니다. 등록 해제 시 노드 및 디바이스 메타데이터가 정리되며, 과거 세션 이력 데이터는 보존됩니다.

---

## 제약 사항

- **Prometheus 통합 모니터링**: 모니터링 시스템은 단일 Prometheus 엔드포인트를 사용하므로, 신규 데이터 플레인의 메트릭 수집을 위해서는 페더레이션 설정이나 스크레이프 타깃 추가가 필요합니다. (단, 콘솔 인벤토리/노드/세션 제어 기능은 영향받지 않습니다.)
- **토큰 수동 로테이션**: 오퍼레이터 인증 토큰 로테이션 자동화 절차가 필요합니다.
- **컨테이너 이미지 접근성**: 세션 이미지는 워크로드가 실행되는 해당 클러스터의 노드에서 접근 및 렌더링이 가능해야 합니다.
- **볼륨 클러스터 바인딩**: PVC 기반의 PersistentVolume은 특정 클러스터에 고정됩니다.
- **자격 증명 인플레이스 로테이션 미지원**: 클러스터 `kubeconfig` 변경 시 기존 등록 해제 후 재등록 절차가 필요합니다.
---
sidebar_position: 1
title: 시작하기
---
# 시작하기

> 📚 [문서 홈](./README.md)

본 문서는 신규 클론 환경에서 진행해야 하는 전체 설정 과정을 순서대로 안내합니다. 진행 방식은 다음 두 가지 경로 중 선택할 수 있습니다.

- **A. 로컬 둘러보기**: Docker Compose를 사용하여 제어 플레인과 콘솔만 신속하게 실행합니다. Kubernetes 및 GPU 환경이 필요하지 않습니다.
- **B. 실제 배포**: GPU Kubernetes 클러스터에 올인원 방식으로 시스템을 설치하고 실제 세션을 실행합니다.

> **참고 문서**: 전체 아키텍처 개요는 [`README.md`](../README.md), 클러스터 신규 구축 방법은 [`cluster-setup.md`](./cluster-setup.md), 클러스터 등록 및 오퍼레이터 연동은 [`cluster-connect.md`](./cluster-connect.md) 문서를 참조하시기 바랍니다.

---

## 0. 저장소 클론 및 사전 조건

```bash
git clone [https://github.com/boanlab/gShare.git](https://github.com/boanlab/gShare.git) && cd gShare
```

| 구분 | 요구 사항 |
|---|---|
| A. 로컬 둘러보기 | Docker 및 Docker Compose |
| B. 실제 배포 | 대상 클러스터가 지정된 `kubectl`, `helm` v3, Kubernetes 클러스터.<br>(GPU 세션 실행 시: NVIDIA 런타임, HAMi, 기본 StorageClass, ingress-nginx 필요) |

이미지를 직접 빌드할 필요는 없습니다. 관련 구성 요소는 `boanlab/gshare-{backend,operator,frontend}:latest` 공개 이미지로 제공됩니다. 소스 코드를 직접 수정한 경우에만 빌드를 진행합니다 (부록 참조).

---

## A. 로컬 둘러보기 (Kubernetes 미사용, GPU 미사용)

제어 플레인과 콘솔을 실행하여 API 및 UI 구성을 확인하는 경로입니다. 오퍼레이터 및 GPU 스케줄러가 포함되지 않으므로 **실제 세션 파드는 시작되지 않습니다** (실제 세션 실행은 경로 B를 참고하십시오).

Compose 기반으로 실행된 제어 플레인에 실제 세션 워크로드를 연동하려면 `hack/cluster-bootstrap.sh up` 스크립트로 GPU 클러스터를 구축하고, 콘솔에서 클러스터를 등록한 후 `make deploy-dataplane CLUSTER_ID=… CONTROL_PLANE_URL=http://<compose-host>:8080` 명령으로 데이터 플레인을 배포합니다. 전체 절차는 [`cluster-connect.md`](./cluster-connect.md) §C 절을 참조하시기 바랍니다.

```bash
make compose-up        # api, worker, frontend, postgres, redis 빌드 및 실행
```

- 콘솔 접속: **http://localhost:8000**
- API 엔드포인트: **http://localhost:8080** (`/healthz`, `/api/v1/...`)
- 초기 관리자 계정: **admin@example.com** / **12345678** (Compose 기본값, 최초 로그인 시 비밀번호 변경 필수)

> **참고**: 기본값 변경은 선택 사항입니다. `.env` 파일이 없어도 시스템은 정상 구동됩니다. 설정을 변경하려면 저장소 루트의 `.env` 파일(Compose에서 자동 로드)을 수정하거나, `make compose-up` 실행 전 셸 환경 변수로 `GSHARE_BOOTSTRAP_ADMIN_EMAIL`, `GSHARE_BOOTSTRAP_ADMIN_PASSWORD`, `GSHARE_SESSION_DOMAIN`을 지정할 수 있습니다. 보안 강화 목적의 RS256 키 등 실제 시크릿 생성이 필요한 경우 `hack/gen-secrets.sh` 스크립트로 `.env` 파일을 작성하십시오.

```bash
make smoke             # API 정상 구동(healthy) 상태까지 대기 및 검증
make compose-down      # 컨테이너 중지 및 볼륨 삭제
```

---

## B. 실제 배포 (GPU Kubernetes 클러스터)

클러스터 내부 인그레스는 **일반 HTTP 통신**을 사용합니다. 직접 운용하는 외부 리버스 프록시에서 TLS를 종단한 후, ingress-nginx의 NodePort(`:30080`)로 트래픽을 전달하도록 구성합니다.

> **단 하나의 설정 파일만 수정하면 됩니다.**
> 템플릿 파일인 [`domain.example.yaml`](../deploy/values/domain.example.yaml)을 `deploy/values/domain.yaml`(Git 추적 제외)로 복사한 후 도메인 및 관리자 계정 정보를 입력하고 `make deploy-incluster` 명령을 실행하십시오. 시크릿, CRD, 네임스페이스, 데이터베이스, Redis, 관리자 초기 계정은 차트에서 자동으로 생성합니다. 기존 클러스터가 이미 존재하는 경우 0단계는 스킵해도 됩니다. `hack/cluster-info` 파일은 클러스터를 신규 구축할 때만 작성합니다.

### 0단계 — 클러스터 사전 준비

ingress-nginx, 기본 StorageClass, GPU 연동을 위한 HAMi 및 NVIDIA 런타임이 이미 준비되어 있다면 1단계로 이동하십시오. 구성되어 있지 않은 경우 [`cluster-setup.md`](./cluster-setup.md) 문서 또는 자동화 부트스트랩 스크립트를 활용합니다.

```bash
cp hack/cluster-info.example hack/cluster-info   # MASTER_NODE, WORKER_NODES(:mode), CPU_WORKERS 기입
./hack/cluster-bootstrap.sh up                   # kubeadm + flannel + HAMi + ingress-nginx(:30080) + local-path 자동 구성
```

`up` 명령은 `cluster-info`에 정의된 모드에 따라 각 노드에 레이블을 부여합니다. 수동 레이블링은 단계별 구성 절차를 진행할 때만 필요합니다.

### 1단계 — 도메인 및 TLS 구성

1. 콘솔에서 사용할 도메인을 지정합니다 (예: `gshare.example.com`).
2. DNS 설정을 **리버스 프록시**로 지정하고, 프록시에서 TLS 종단 처리 후 원본 `Host` 헤더를 유지한 채 `http://<any-node>:30080`으로 `proxy_pass`하도록 설정합니다.
3. 도메인 및 관리자 계정 정보를 배포 오버레이 설정 파일에 입력합니다. 본 설정은 경로 B에서 수정하는 **유일한** 설정값입니다. 배포 환경마다 달라지며 버전 관리(Git)에 포함되지 않도록 전용 파일로 관리됩니다.

   ```bash
   cp deploy/values/domain.example.yaml deploy/values/domain.yaml
   ```

   ```yaml
   # deploy/values/domain.yaml
   global:
     domains:
       console: gshare.example.com   # 실제 도메인 — 콘솔 및 경로 기반 세션에 사용되는 단일 호스트명
   bootstrapAdmin:
     email: admin@example.com        # 최초 super_admin 로그인 계정 (기본값: admin@example.com)
     password: 12345678      # 초기 비밀번호 (최초 로그인 시 변경 필수)
   ```

   `make deploy-incluster` 및 `make prod-deploy` 명령 실행 시 해당 파일이 존재하면 오버레이 설정(`-f`)으로 반영되며, 없을 경우 차트 기본값을 적용합니다. 지정한 도메인 값 하나로 콘솔 UI, 모든 세션 접속 URL(`/proxy/{cr}/{lab,terminal,code}`), 인그레스 호스트 설정이 일괄 지정됩니다. 관리자 계정은 최초 구동 시 입력된 이메일과 비밀번호로 자동 생성됩니다. `password: ""`로 설정 시 무작위 비밀번호가 생성되며, 생성된 비밀번호는 3단계에서 조회할 수 있습니다. 표시 이름은 로그인 후 콘솔 프로필 화면에서 수정 가능합니다.

### 2단계 — 배포 실행

```bash
make deploy-incluster
```

배포 절차가 완료되었습니다. 차트는 수동 개입 없이 클러스터 내 Postgres, Redis, 시크릿, CRD, 네임스페이스, 오퍼레이터 내부 JWT(Job 및 CronJob을 통한 발급/로테이션), 로컬 클러스터 등록까지 모든 구성을 일괄 처리합니다. 이미지 태그는 공개된 `:latest` 버전을 사용합니다.

> 프로덕션 고도화 환경(외부 CloudNativePG, Redis, external-secrets 연동) 배포 시에는 [`deploy/values/dockerhub.yaml`](../deploy/values/dockerhub.yaml) 설정과 함께 `make prod-deploy` 명령을 사용합니다.

**선택적 애드온 구성** (독립 실행 가능, [`domain.example.yaml`](../deploy/values/domain.example.yaml) 내 주석 예시 참조):

- **모니터링**: `make deploy-monitoring` 실행 시 dcgm / node / kube-state 익스포터 및 Prometheus를 통합 배포합니다. 관리자 모니터링 화면, 세션별 실시간 리소스 사용량 패널, 그리고 유휴 세션 리퍼(Reaper)를 위한 사용률 측정 데이터 원천(`operator.prometheusUrl`)을 제공합니다. GPU 노드가 2개 이상인 클러스터에서는 `prometheusUrl`을 반드시 지정해야 합니다. (HAMi 모니터링 대체 경로 사용 시 노드 파드를 라운드로빈 방식으로 조회하므로 유휴 세션 자동 일시정지가 올바르게 동작하지 않을 수 있습니다.) Prometheus 데이터는 클러스터의 **기본 StorageClass** PVC에 저장되므로 별도의 스토리지 노드가 필요하지 않습니다. (이전 설치로 인해 `gshare-data`에 고정된 PVC가 잔재하는 경우 삭제 후 재배포하십시오. PVC의 `storageClassName`은 변경 불가능합니다.)
- **이종 GPU 플릿 구성**: 단일 클러스터 내에 서로 다른 GPU 모델이 혼재된 경우 `operator.perCardMode: true` 설정이 필요합니다. 원장(Ledger)에서 예약된 정확한 카드로 세션 파드를 고정하여, 특정 모델 가격으로 결제된 세션이 다른 모델 노드에 잘못 배치되는 현상을 방지합니다.
- **사내/LAN 이미지 레지스트리**: `deploy/registry/registry.yaml` 배포 및 노드별 신뢰 설정을 진행합니다. 자세한 내용은 [`cluster-setup.md` §로컬 레지스트리](./cluster-setup.md#local-registry-optional) 절을 참조하십시오. `api.buildRegistry`를 지정하면 콘솔에서 빌드된 이미지도 해당 레지스트리로 푸시됩니다.
- **실제 볼륨 쿼터 적용**: ZFS 기반 스토리지 노드를 구성합니다 ([`cluster-setup.md` §스토리지 노드](./cluster-setup.md#storage-node-optional-volumes-with-a-real-quota) 참조). 구성 후 `operator.volumeStorageClass: gshare-data`로 지정합니다.

### 3단계 — 배포 상태 확인 및 로그인

```bash
kubectl get pods -n gshare-system   # api, worker, operator, frontend, pg, redis가 모두 Running 상태인지 확인

# 초기 관리자 비밀번호 기본값은 12345678입니다.
# 설정값을 변경했거나 무작위 생성되도록 비워둔 경우 다음 명령으로 시크릿에서 비밀번호를 조회합니다:
kubectl get secret -n gshare-system gshare-bootstrap-admin -o jsonpath='{.data.password}' | base64 -d
```

리버스 프록시를 통해 **https://gshare.example.com**에 접속한 후, `bootstrapAdmin.email` 계정과 해당 비밀번호로 로그인합니다. 로그인 직후 비밀번호 변경 화면으로 이동합니다.

### 4단계 — 기본 카탈로그 확인 (관리자)

최초 실행 시 기본 카탈로그가 멱등하게 자동 생성(Seed)됩니다. 기본 항목에는 GPU 오퍼링(RTX, A100, H100), 기본 컨테이너 이미지, 컴퓨트/GPU 프리셋, 전역 자원 정책, 시스템 지갑이 포함됩니다. 관리자는 콘솔 UI 또는 API (`POST /api/v1/offerings`, `POST /api/v1/images`, `/images/import`)를 통해 카탈로그를 수정하거나 확장할 수 있습니다.

- **오퍼링**: 사용자가 선택하는 GPU 모델, 티어 및 시간당 크레딧 단가입니다. 자동 생성된 단가는 예시값이므로 콘솔에서 실제 환경에 맞게 조정하십시오.
- **이미지**: 세션 컨테이너 이미지입니다. gShare 세션 이미지에는 JupyterLab, 웹 터미널, code-server가 포함되어 있습니다.
- 사용자는 공용 카탈로그 이미지로 제한되지 않으며, 사용자 API를 통해 자신의 개별 이미지를 등록할 수 있습니다 (`POST /api/v1/images/import`로 공개 레지스트리 참조, `POST /api/v1/image-builds`로 빌드 요청). 해당 항목은 소유자 본인에게만 노출되며 생성 마법사에서 **내 이미지** 태그로 구분됩니다 (사용자당 최대 20개).

오퍼레이터가 GPU 인벤토리를 주기적으로 자동 보고하므로, 노드 및 디바이스 정보(예: RTX 4090)는 추가 설정 없이 인프라 관리 화면에 자동으로 표시됩니다.

### 5단계 — 세션 생성 및 접속 (사용자)

사용자가 로그인하여 오퍼링과 이미지를 선택한 후 세션을 생성합니다. 세션 상태가 `running`으로 전환되면, 콘솔에 단일 도메인 기반의 일회용 접속 토큰이 포함된 연결 링크가 제공됩니다.

- `https://gshare.example.com/proxy/{cr}/lab` → JupyterLab
- `https://gshare.example.com/proxy/{cr}/terminal` → 웹 터미널 (ttyd)
- `https://gshare.example.com/proxy/{cr}/code/` → code-server (VS Code)

인그레스의 포워드 인증(Forward-auth) 모듈이 일회용 `?gshare_cnx=…` 토큰을 단기 쿠키로 변환한 후 대상 애플리케이션으로 프록시합니다. SSH 접속은 제공되지 않으며, 웹 터미널 또는 code-server 내 터미널을 사용합니다.

세션은 **일시 중지** 및 **재개**가 가능합니다. 일시 중지 시 파드가 종료되고 GPU 리소스 반납과 함께 과금이 정지됩니다. 재개 시 GPU 리소스를 재할당받아 세션을 다시 실행합니다.

---

## 요약

- **로컬 둘러보기**: `make compose-up` 실행 후 `http://localhost:8000` 콘솔 접속 (제어 플레인 단독 구성).
- **올인원 배포**: 클러스터 사전 준비 → 도메인 설정 및 TLS 종단 프록시 구성 → `make deploy-incluster` 실행 → 관리자 로그인 후 오퍼링/이미지 검토 → 사용자 세션 생성 → `https://{domain}/proxy/{cr}/{lab|terminal|code}` 경로로 접속.
- **Compose + 외부 클러스터 연동**: `make compose-up`으로 제어 플레인 구동 → GPU 클러스터에서 `cluster-bootstrap.sh up` 실행 → 콘솔에서 클러스터 등록 → `make deploy-dataplane CLUSTER_ID=… CONTROL_PLANE_URL=…` 실행 ([`cluster-connect.md`](./cluster-connect.md) §C 참조).

---

## 부록 — 컨테이너 이미지 직접 빌드 및 푸시

소스 코드를 변경한 경우에만 진행합니다. 기본 배포 환경에서는 공개된 전용 이미지를 사용합니다.

```bash
make images TAG=<tag>            # backend, operator, frontend 빌드
make login                       # DOCKERHUB_USERNAME / DOCKERHUB_TOKEN 정보로 로그인
make push TAG=<tag>
make deploy-incluster TAG=<tag>  # 해당 태그 버전으로 배포
```

- Helm 차트의 자동 생성 대신 시크릿을 직접 주입하려는 경우: `hack/gen-secrets.sh --k8s` 명령을 사용합니다.
- 테스트 실행: 단위 및 기능 테스트는 `make test`, 전체 파이프라인 검증은 `make ci` 명령을 사용합니다.
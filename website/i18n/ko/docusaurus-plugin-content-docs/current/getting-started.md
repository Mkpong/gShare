---
sidebar_position: 1
title: 시작하기
---
# 시작하기

> 📚 [문서 홈](./README.md)

새 클론에서 해야 할 모든 것을 순서대로. 두 가지 길이 있습니다.

- **A. 로컬 둘러보기** — Docker Compose로 제어 플레인과 콘솔만 띄웁니다. Kubernetes도 GPU도
  필요 없습니다.
- **B. 실제 배포** — GPU Kubernetes 클러스터에 올인원으로 설치하고 실제 세션을 돌립니다.

> 관련: 전체 그림은 [`README.md`](../README.md), 클러스터 자체를 만드는 법은
> [`cluster-setup.md`](./cluster-setup.md), 클러스터 등록과 오퍼레이터 연결은
> [`cluster-connect.md`](./cluster-connect.md).

---

## 0. 클론과 전제 조건

```bash
git clone https://github.com/boanlab/gShare.git && cd gShare
```

| 경로 | 요구 사항 |
|---|---|
| A. 로컬 둘러보기 | Docker와 Docker Compose |
| B. 실제 배포 | 대상 클러스터를 가리키는 `kubectl`, `helm` v3, Kubernetes 클러스터. GPU 세션에는 NVIDIA 런타임, HAMi, 기본 StorageClass, ingress-nginx |

이미지를 빌드할 필요는 없습니다. 구성 요소는 `boanlab/gshare-{backend,operator,frontend}:latest`로
공개되어 있습니다. 코드를 바꿨을 때만 빌드하세요 — 부록 참고.

---

## A. 로컬 둘러보기 (Kubernetes 없음, GPU 없음)

제어 플레인과 콘솔을 띄워 API와 UI를 살펴보는 경로입니다. 오퍼레이터와 GPU 스케줄링이 없으므로
기본적으로 **실제 세션 파드는 시작되지 않습니다** — 그것은 경로 B입니다.

Compose에 올린 제어 플레인으로 실제 세션을 돌리려면 `hack/cluster-bootstrap.sh up`으로 GPU
클러스터를 만들고, 콘솔에서 등록한 뒤,
`make deploy-dataplane CLUSTER_ID=… CONTROL_PLANE_URL=http://<compose-host>:8080`으로 데이터
플레인을 올리세요. 전체 절차는 [`cluster-connect.md`](./cluster-connect.md) §C에 있습니다.

```bash
make compose-up        # api, worker, frontend, postgres, redis 빌드·시작
```

- 콘솔: **http://localhost:8000**
- API: **http://localhost:8080** (`/healthz`, `/api/v1/...`)
- 로그인: **admin@example.com** / **12345678** — Compose 기본값. 첫 로그인 때 비밀번호 변경이
  강제됩니다.

> 기본값 변경은 선택입니다. 스택은 `.env` 없이도 돕니다. 바꾸려면 저장소 루트 `.env`(Compose가
> 자동 로드)나 `make compose-up` 전 셸 환경에 `GSHARE_BOOTSTRAP_ADMIN_EMAIL`,
> `GSHARE_BOOTSTRAP_ADMIN_PASSWORD`, `GSHARE_SESSION_DOMAIN`을 두세요. 진짜 RS256 키 같은 강한
> 시크릿이 필요하면 `hack/gen-secrets.sh`로 `.env`를 생성하세요 — 역시 Compose에서는 선택입니다.

```bash
make smoke             # API가 healthy를 보고할 때까지 대기
make compose-down      # 정지하고 볼륨 삭제
```

---

## B. 실제 배포 (GPU Kubernetes 클러스터)

클러스터는 **일반 HTTP**만 받습니다. 직접 운영하는 리버스 프록시가 TLS를 종단하고 ingress-nginx
NodePort `:30080`으로 전달합니다.

> **파일 딱 하나만 편집합니다.** 템플릿
> [`domain.example.yaml`](../deploy/values/domain.example.yaml)을
> `deploy/values/domain.yaml`(커밋하지 않음)로 복사해 도메인과 관리자 계정을 채우고
> `make deploy-incluster`를 실행하세요. 시크릿, CRD, 네임스페이스, 데이터베이스, Redis, 관리자
> 비밀번호는 모두 차트가 만듭니다. 클러스터가 이미 있으면 0단계는 건너뛰세요.
> `hack/cluster-info`는 새로 만들 때만 필요합니다.

### 0단계 — 클러스터 준비

ingress-nginx, 기본 StorageClass, 그리고 GPU 작업용 HAMi와 NVIDIA 런타임이 이미 있으면 1단계로.
아니면 [`cluster-setup.md`](./cluster-setup.md)를 보거나 자동화 경로를 쓰세요.

```bash
cp hack/cluster-info.example hack/cluster-info   # MASTER_NODE, WORKER_NODES(:mode), CPU_WORKERS 기입
./hack/cluster-bootstrap.sh up                   # kubeadm + flannel + HAMi + ingress-nginx(:30080) + local-path
```

`up`은 `cluster-info`의 모드대로 노드에 라벨을 붙입니다. 수동 라벨링은 단계별 경로에서만 필요합니다.

### 1단계 — 도메인과 TLS 결정

1. 콘솔 도메인을 정합니다. 예: `gshare.example.com`.
2. DNS를 **리버스 프록시**로 향하게 하고, 프록시가 TLS를 종단한 뒤 `Host` 헤더를 유지한 채
   `http://<any-node>:30080`으로 `proxy_pass`하게 합니다.
3. 도메인과 관리자 계정을 배포 로컬 오버레이에 적습니다. 경로 B에서 손대는 **유일한** 설정입니다.
   배포마다 다르고 커밋하면 안 되므로 자체 파일에 둡니다(git 무시, 예시만 추적):

   ```bash
   cp deploy/values/domain.example.yaml deploy/values/domain.yaml
   ```

   ```yaml
   # deploy/values/domain.yaml
   global:
     domains:
       console: gshare.example.com   # 실제 도메인 — 콘솔과 경로 기반 세션이 쓰는 호스트 하나
   bootstrapAdmin:
     email: admin@example.com        # 첫 super_admin 로그인(기본: admin@example.com)
     password: 12345678      # 초기 비밀번호; 첫 로그인 때 변경 필수
   ```

   `make deploy-incluster`와 `make prod-deploy`는 이 파일이 있으면 `-f`로 적용하고, 없으면 차트
   기본값을 씁니다. 도메인 값 하나가 콘솔, 모든 세션 URL(`/proxy/{cr}/{lab,terminal,code}`),
   인그레스 호스트를 정합니다. 관리자 계정은 첫 시작 때 이 이메일과 비밀번호로 만들어집니다.
   `password: ""`로 두면 무작위 비밀번호가 생성되며 — 3단계에서 읽어 옵니다. 표시 이름은 로그인 후
   콘솔에서 편집합니다.

### 2단계 — 배포

```bash
make deploy-incluster
```

이것이 설치 전부입니다. 차트는 수동 전제 없이 모든 것을 구성합니다. 클러스터 내 Postgres와 Redis,
시크릿, CRD, 네임스페이스, 오퍼레이터 내부 JWT(Job과 CronJob이 발급·회전), 로컬 클러스터 등록.
공개 `:latest` 이미지를 씁니다.

> 프로덕션 변형 — 외부 CloudNativePG와 Redis, external-secrets — 은
> [`deploy/values/dockerhub.yaml`](../deploy/values/dockerhub.yaml)로 `make prod-deploy`.

**선택 애드온**(각각 독립. 오버레이로 활성화 — 모든 항목이
[`domain.example.yaml`](../deploy/values/domain.example.yaml)에 주석 예시로 있음):

- **모니터링** — `make deploy-monitoring`이 dcgm / node / kube-state 익스포터와 함께 Prometheus를
  설치합니다. 관리자 모니터링 페이지, 세션별 실시간 사용량 패널, 그리고
  (`operator.prometheusUrl`을 통해) 유휴 리퍼의 사용률 소스를 제공합니다. GPU 노드가 둘 이상인
  클러스터에서는 `prometheusUrl`을 설정하세요. HAMi 모니터 대체 경로는 노드별 파드를
  라운드로빈해 유휴 세션이 자동 일시정지되지 않습니다. Prometheus는 클러스터의 **기본
  StorageClass** PVC에 데이터를 두며 선택 스토리지 노드가 필요 없습니다. (이전 설치가
  `gshare-data`에 고정된 PVC를 남겼다면 재적용 전에 그 PVC를 삭제하세요. `storageClassName`은
  불변입니다.)
- **혼합 GPU 플릿** — 한 클러스터에 다른 카드 모델이 있으면 `operator.perCardMode: true`가
  필요합니다. 각 세션 파드를 원장이 예약한 정확한 카드에 고정합니다. 없으면 한 모델 가격의
  세션이 다른 모델에 배치될 수 있습니다.
- **LAN 이미지 레지스트리** — `deploy/registry/registry.yaml`과 노드별 신뢰 설정.
  [`cluster-setup.md` §로컬 레지스트리](./cluster-setup.md#local-registry-optional) 참고.
  `api.buildRegistry`를 설정해 콘솔 빌드 이미지도 거기로 푸시하게 하세요.
- **실제 볼륨 쿼터** — ZFS 스토리지 노드
  ([`cluster-setup.md` §스토리지 노드](./cluster-setup.md#storage-node-optional-volumes-with-a-real-quota));
  그다음 `operator.volumeStorageClass: gshare-data`.

### 3단계 — 확인과 로그인

```bash
kubectl get pods -n gshare-system   # api, worker, operator, frontend, pg, redis 모두 Running

# 관리자 비밀번호 기본값은 12345678. 다르게 설정했거나 비워서 무작위 생성했다면
# 시크릿에서 읽습니다:
kubectl get secret -n gshare-system gshare-bootstrap-admin -o jsonpath='{.data.password}' | base64 -d
```

리버스 프록시를 통해 **https://gshare.example.com**을 열고 `bootstrapAdmin.email`과 그 비밀번호로
로그인합니다. 즉시 변경을 요구받습니다.

### 4단계 — 카탈로그 확인(관리자)

시작 시 기본 카탈로그가 멱등하게 시드됩니다. GPU 오퍼링(RTX, A100, H100), 기본 이미지, 컴퓨트·GPU
프리셋, 전역 자원 정책, 시스템 지갑. 관리자는 콘솔이나 `POST /api/v1/offerings`,
`POST /api/v1/images` / `/images/import`로 편집·확장만 하면 됩니다.

- **오퍼링**은 사용자가 고르는 것: GPU 모델과 티어, 시간당 크레딧 단가. 시드된 단가는 제안값이니
  콘솔에서 조정하세요.
- **이미지**는 세션 컨테이너 이미지. gShare 세션 이미지는 JupyterLab, 웹 터미널, code-server를
  포함합니다.
- 사용자는 공용 카탈로그에 묶이지 않습니다. 구성원은 API로 자기 이미지를 등록할 수 있습니다
  (`POST /api/v1/images/import`로 공개 레지스트리 참조, `POST /api/v1/image-builds`로 빌드). 그 행은
  소유자에게만 보이고 마법사에서 **내 이미지** 태그가 붙으며, 한 구성원당 최대 20개입니다.

오퍼레이터가 GPU 인벤토리를 자동 보고하므로 노드와 디바이스(예: RTX 4090)는 추가 설정 없이 인프라
화면에 나타납니다.

### 5단계 — 세션 생성과 연결(사용자)

사용자가 로그인해 오퍼링과 이미지를 고르고 세션을 만듭니다. `running`이 되면 콘솔이 연결 링크 —
각각 일회용 토큰 포함 — 를 한 도메인 아래에 보여 줍니다.

- `https://gshare.example.com/proxy/{cr}/lab` → JupyterLab
- `https://gshare.example.com/proxy/{cr}/terminal` → 웹 터미널(ttyd)
- `https://gshare.example.com/proxy/{cr}/code/` → code-server(VS Code)

인그레스 forward-auth가 일회용 `?gshare_cnx=…` 토큰을 짧은 쿠키로 바꾼 뒤 앱으로 프록시합니다.
SSH는 없습니다. 셸은 웹 터미널이나 code-server 터미널입니다.

세션은 **일시정지·재개**할 수 있습니다. 일시정지는 파드를 내리고 GPU를 반환하며 과금을 멈추고,
재개는 GPU를 다시 확보해 다시 시작합니다.

---

## 요약

- **로컬:** `make compose-up`, 그다음 `:8000`의 콘솔(제어 플레인만).
- **올인원:** 클러스터 준비 → 도메인 설정과 TLS 종단 프록시 → `make deploy-incluster` → 관리자로
  로그인해 오퍼링·이미지 검토 → 사용자가 세션 생성 →
  `https://{domain}/proxy/{cr}/{lab|terminal|code}`로 연결.
- **Compose + 외부 클러스터:** 제어 플레인은 `make compose-up` → GPU 클러스터에서
  `cluster-bootstrap.sh up` → 콘솔에서 등록 →
  `make deploy-dataplane CLUSTER_ID=… CONTROL_PLANE_URL=…`.
  [`cluster-connect.md`](./cluster-connect.md) §C 참고.

---

## 부록 — 직접 이미지 빌드·푸시

구성 요소를 바꿨을 때만 필요합니다. 기본 설치는 공개 이미지를 씁니다.

```bash
make images TAG=<tag>            # backend, operator, frontend 빌드
make login                       # DOCKERHUB_USERNAME / DOCKERHUB_TOKEN으로 로그인
make push TAG=<tag>
make deploy-incluster TAG=<tag>  # 그 태그로 배포
```

- 차트가 생성하는 대신 시크릿을 직접 주입하려면: `hack/gen-secrets.sh --k8s`.
- 테스트: 단위·기능 테스트는 `make test`, 전체 게이트는 `make ci`.

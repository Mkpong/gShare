---
sidebar_position: 3
title: 클러스터 연결
---

# 클러스터 연결

> **다중 클러스터(Multi-Cluster) 환경을 구성 중이신가요?**  
> 상세 운영 런북은 [multi-cluster.md](multi-cluster.md) 및 `hack/attach-cluster.sh` 스크립트를 참고하세요. 본 문서는 클러스터 연결 아키텍처 개요 및 단일 클러스터/Compose 토폴로지 연결 방법을 안내합니다.

> 📚 [문서 홈](./README.md)

[`cluster-setup.md`](./cluster-setup.md)가 신규 GPU 클러스터를 **구축**하는 절차라면, 본 문서는 구축된 클러스터를 gShare **제어 플레인(Control Plane)**에 **연결**하는 절차를 다룹니다. 제어 플레인은 클러스터 위치에 종속되지 않으며, 등록된 `kubeconfig`를 기반으로 외부 GPU 클러스터에 `GShareSession` 커스텀 리소스(CR)를 적용합니다. 이후 각 클러스터의 오퍼레이터가 이를 재조정(Reconcile)하여 자원 인벤토리 및 세션 상태를 콜백으로 동기화합니다.

## 핵심 개념

| 주체 | 위치 | 주요 역할 및 기능 |
|---|---|---|
| **제어 플레인 (`api`, `worker`)** | Compose 또는 Kubernetes | 클러스터 등록 관리, `kubeconfig` 기반 CR 적용, 오퍼레이터 콜백 검증, 내부 RS256 JWT 서명/검증 및 JWKS 발행 |
| **오퍼레이터 (Operator)** | 각 GPU 클러스터 | `GShareSession` CR 재조정, GPU 자원 인벤토리 및 세션 상태 보고 (내부 JWT 인증) |

- **`cluster_id`:** 클러스터 등록 시 제어 플레인이 발급하는 고유 식별자(`clu_…` ULID)입니다. 오퍼레이터 실행 파라미터의 `--cluster-id` 설정값은 발급된 ID와 **정확히 일치**해야 합니다.
- **내부 JWT:** 오퍼레이터에서 제어 플레인으로 전달되는 상태 보고 콜백을 인증하는 RS256 서명 토큰(`aud=gshare-internal`)입니다. 공개 검증 키는 `GET /.well-known/gshare-internal-jwks.json` 엔드포인트를 통해 발행됩니다.
- **`kubeconfig` 관리:** `kubeconfig` 보안을 위해 데이터베이스에 평문으로 저장되지 않으며, 파일 보안 마운트 방식(Kubernetes: External Secrets, Compose: 로컬 파일 마운트)을 사용합니다. 접근 경로는 `GSHARE_CLUSTER_KUBECONFIG_DIR` 설정값 하위의 `<cluster_id>/kubeconfig`입니다.

## A. 클러스터 내 올인원 (In-Cluster All-in-One)

`make deploy-incluster` 실행 시 `bootstrapLocalCluster: true` 옵션이 설정되어 고정 ID(`clu_local`)를 가진 클러스터 항목이 자동 생성되며, Helm 차트의 `operator.clusterId: clu_local` 설정이 이를 참조합니다. 오퍼레이터는 동일 클러스터 내부의 ServiceAccount 권한으로 Kubernetes API에 직접 접근하므로 별도의 `kubeconfig` 등록 절차가 필요하지 않습니다.

## B. 외부 클러스터 등록

클러스터 등록 시 제어 플레인은 대상 클러스터 통신 여부, `nvidia` RuntimeClass 존재 여부, HAMi의 `nvidia.com/gpumem` 리소스 할당 가능 여부를 검증 프로브로 확인합니다. 사전 환경 구축 방법은 [`cluster-setup.md`](./cluster-setup.md)를 참고하세요.

관리자 콘솔의 **관리자 → 클러스터** 메뉴에서 이름과 `kubeconfig`를 입력하여 등록하거나, REST API를 통해 직접 등록할 수 있습니다.

```bash
curl -sX POST https://<console>/api/v1/clusters \
  -H "Authorization: Bearer $ADMIN_JWT" -H "Idempotency-Key: $(uuidgen)" \
  -d "{\"name\":\"gpu-a\",\"role\":\"primary\",\"kubeconfig_b64\":\"$(base64 -w0 <kubeconfig)\"}"
```

검증 프로브 통과 시 `clu_…` 형태의 ID가 반환됩니다. `kubeconfig` 정보는 최초 검증 시에만 활용되며, 이후 모든 I/O 작업은 마운트된 보안 파일 또는 ServiceAccount 권한을 통해 처리됩니다.

## C. Compose 제어 플레인 + 외부 GPU 클러스터

Docker Compose 환경은 기본 HTTP 서비스를 제공하므로 전면에 TLS 종단 리버스 프록시가 배치되어야 합니다 ([`docker-compose.yml`](../docker-compose.yml) 참고). 제어 플레인의 `/internal/*` 엔드포인트 및 JWKS 경로는 외부 GPU 클러스터에서 네트워크 접근이 가능해야 합니다.

> **세션 트래픽 라우팅 설정**
>
> 세션 접속 URL 포맷은 `{GSHARE_SESSION_DOMAIN}/proxy/{cr}/{code|lab|terminal}` 구조를 가집니다. Compose 콘솔 프런트엔드와 외부 클러스터의 Ingress-Nginx는 서로 다른 백엔드이므로, 리버스 프록시에서 **`/proxy/` 경로 요청만** 외부 클러스터 인그레스로 라우팅해야 합니다.
>
> Nginx 라우팅 설정 예시:
>
> ```nginx
> location /proxy/ {                          # 세션 웹앱 → 외부 클러스터 인그레스 (예: NodePort 30080)
>     proxy_pass http://<cluster-node>:30080;
>     proxy_set_header Host $host;            # GSHARE_SESSION_DOMAIN과 동일해야 함
>     proxy_http_version 1.1;                 # WebSocket 프로토콜 지원 (VS Code / 터미널)
>     proxy_set_header Upgrade $http_upgrade;
>     proxy_set_header Connection "upgrade";
>     proxy_read_timeout 3600s;
> }
> location / { proxy_pass http://<compose-host>:8000; }   # 콘솔 프런트엔드
> ```
>
> 경로 분리 방식 외에도 전용 세션 도메인(예: `sessions.example.com`)을 외부 클러스터 인그레스로 직접 연결하고, `GSHARE_SESSION_DOMAIN` 및 오퍼레이터의 `SESSION_DOMAIN`을 해당 도메인으로 동일하게 설정하여 관리할 수 있습니다.
>
> 프록시 단에서 경로 분리가 어려운 경우 Compose `.env` 파일에 `GSHARE_SESSION_INGRESS=<cluster-node>:30080`을 지정하면 Compose Nginx 프런트엔드가 `/proxy/` 트래픽을 해당 외부 클러스터 인그레스로 자동 중계합니다.
>
> **프록시 환경에서의 클라이언트 IP 추적:**  
> 로그인 보안 감사 및 IP 기반 차단 정책을 위해 `X-Forwarded-For` 헤더를 수집합니다. 프록시 경유 단계에 맞춰 `.env` 파일의 `GSHARE_TRUSTED_PROXY_HOPS` 설정값(기본값: `1`)을 조정하세요. (Helm 차트의 경우 `api.trustedProxyHops`)

### 구축 순서

1. **내부 인증 키 생성:** RS256 키를 생성한 후 서비스를 시작합니다.
   ```bash
   ./hack/gen-secrets.sh   # .env 파일에 GSHARE_INTERNAL_JWT_PRIVATE_KEY 및 KID 기록
   make compose-up
   ```
2. **클러스터 등록:** B절의 등록 절차를 수행하고 발급된 `clu_id`를 확인합니다.
3. **`kubeconfig` 마운트:** 제어 플레인이 CR을 발급할 수 있도록 지정된 경로에 파일을 배치합니다.
   ```bash
   mkdir -p deploy/clusters/<clu_id> && cp <kubeconfig> deploy/clusters/<clu_id>/kubeconfig
   ```
   *Note: Compose 환경은 해당 디렉터리를 `/run/gshare/clusters` 경로에 읽기 전용으로 자동 마운트합니다.*

4. **데이터 플레인 배포:**
   
   **권장: Helm 기반 데이터 플레인 배포**  
   제어 플레인 기능을 제외한(`controlPlane.enabled=false`) 데이터 플레인 전용 Helm 차트를 배포합니다.
   ```bash
   KUBECONFIG=<target cluster kubeconfig> \
     make deploy-dataplane CLUSTER_ID=<clu_id> CONTROL_PLANE_URL=http://<compose-host>:8080
   ```
   `CONTROL_PLANE_URL`은 오퍼레이터 파드 및 Ingress-Nginx에서 접근 가능한 주소여야 합니다. 토큰 기본 유효기간은 7일(`JWT_TTL`)이며, 만료 전 `make dataplane-token CLUSTER_ID=<clu_id>` 명령으로 시크릿을 갱신합니다.

   **대안: 경량화 배포 스크립트**  
   유휴 자원 자동 회수, 무손실 일시정지, 웹훅 기능 없이 기본 세션 실행 환경만 구성하는 경우 경량 배포 스크립트를 사용할 수 있습니다.
   ```bash
   TOKEN=$(make -s compose-operator-token CLUSTER_ID=<clu_id>)   # 내부 JWT 발급 (24시간 유효)
   CLUSTER_ID=<clu_id> SOT_ENDPOINT=https://<public control-plane URL> OPERATOR_TOKEN="$TOKEN" \
     KUBECONFIG=<target cluster kubeconfig> SESSION_DOMAIN=<GSHARE_SESSION_DOMAIN과 동일 설정> \
     ./hack/deploy-operator.sh
   ```
   > ⚠️ `SESSION_DOMAIN`은 제어 플레인의 `GSHARE_SESSION_DOMAIN`과 **반드시 동일하게 설정**해야 합니다. 값이 일치하지 않을 경우 인그레스 호스트 매칭 실패로 접속 시 404 오류가 발생합니다.

5. **연결 상태 검증:** 오퍼레이터 로그에서 콜백 응답 코드 `200`을 확인하고, 관리자 콘솔의 클러스터 상태가 `connected`로 변경되었는지 및 GPU 인벤토리가 수집되었는지 확인합니다.

### 토큰 자동 회전 (Token Rotation)

내부 인증 JWT 토큰은 만료 전 주기적으로 갱신해야 합니다.

- **Helm 배포 환경:** `make dataplane-token CLUSTER_ID=<clu_id>` 실행 (7일 주기 갱신 권장)
- **스크립트 배포 환경:** 새 토큰 발급 후 `./hack/deploy-operator.sh` 재실행

```bash
# 예시: Compose 호스트 crontab 등록 (매일 02:00 자동 회전)
0 2 * * * cd /path/to/gShare && KUBECONFIG=<target cluster kubeconfig> make -s dataplane-token CLUSTER_ID=<clu_id>
```

## D. Kubernetes 제어 플레인 + 추가 외부 클러스터

제어 플레인이 Kubernetes 클러스터 상에서 실행되는 경우 External Secrets Operator가 각 외부 클러스터의 `kubeconfig`를 `GSHARE_CLUSTER_KUBECONFIG_DIR` 경로 하위에 자동 투영합니다. 신규 외부 클러스터 추가 시 Helm 차트를 이용하여 오퍼레이터만 배포하며, `operator.clusterId`, `operator.controlPlaneUrl`, `operator.internalJwtSecret` 값을 지정합니다.

## 보안 및 제약 사항

- **`kubeconfig` 보안:** 데이터베이스 내에 평문으로 저장되지 않으며 읽기 전용 보안 마운트 파일로 관리됩니다.
- **인증 보안:** `/internal/*` 엔드포인트 및 모든 콜백 통신은 `aud=gshare-internal` 클레임을 포함하는 RS256 서명 토큰을 요구합니다.
- **네트워크 접근성:** Compose 제어 플레인 사용 시 `/internal` 엔드포인트 및 JWKS URL이 외부 GPU 클러스터 파드에서 상호 통신 가능하도록 방화벽 및 DNS 설정이 구성되어야 합니다.
- **토큰 자동 갱신:** Kubernetes 환경에서는 CronJob을 통해 토큰이 자동 회전되며, Compose 환경에서는 수동 갱신 스크립트 또는 Crontab 설정이 필요합니다.
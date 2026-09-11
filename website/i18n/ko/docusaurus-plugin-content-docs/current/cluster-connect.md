---
sidebar_position: 3
title: 클러스터 연결
---
# 클러스터 연결

> **두 번째 클러스터를 붙이나요?** [multi-cluster.md](multi-cluster.md)와
> `hack/attach-cluster.sh`를 쓰세요. 이 문서는 개념과 단일 클러스터·Compose 토폴로지를 다루고,
> 저 문서는 맨 GPU 클러스터를 위한 운영자 런북입니다.

> 📚 [문서 홈](./README.md)

[`cluster-setup.md`](./cluster-setup.md)가 GPU 클러스터를 **만드는** 곳이라면, 이 페이지는 그것을
gShare **제어 플레인**에 **붙이는** 곳입니다. 제어 플레인은 클러스터에 무관합니다. 등록된
kubeconfig로 외부 GPU 클러스터에 `GShareSession` 커스텀 리소스를 적용하고, 각 클러스터의
오퍼레이터가 이를 재조정해 상태와 인벤토리를 콜백합니다.

## 개념

| 주체 | 위치 | 책임 |
|---|---|---|
| 제어 플레인(`api`, `worker`) | Compose 또는 Kubernetes | 클러스터 등록, kubeconfig로 커스텀 리소스 적용, 오퍼레이터 콜백 검증. 내부 JWT를 서명·검증하고 JWKS를 발행 |
| 오퍼레이터 | 각 GPU 클러스터 | `GShareSession` 재조정, 인벤토리·상태 보고. 내부 JWT 보유 |

- **`cluster_id`** — 등록 시 제어 플레인이 발급하는 `clu_…` ULID. 오퍼레이터의 `--cluster-id`는
  **반드시 이와 같아야** 합니다. 아니면 인벤토리와 세션 외래 키가 맞지 않습니다. 협상은 없습니다.
  등록이 돌려준 id를 오퍼레이터 배포에 넣으세요.
- **내부 JWT** — 오퍼레이터→제어 플레인 콜백을 인증합니다(RS256, `aud=gshare-internal`). 제어
  플레인이 서명·검증하고 공개 검증 키를 `GET /.well-known/gshare-internal-jwks.json`에 발행합니다.
- **kubeconfig** — 데이터베이스에 평문으로 저장되지 않습니다. 제어 플레인은 투영된 파일만
  읽습니다. Kubernetes에서는 external-secrets, Compose나 베어메탈에서는 직접 마운트. 경로는
  `GSHARE_CLUSTER_KUBECONFIG_DIR` 아래 `<cluster_id>/kubeconfig`.

## A. 클러스터 내 올인원 — 자동 등록

`make deploy-incluster`는 `bootstrapLocalCluster: true`를 설정해 시작 시 고정 id `clu_local`의
`Cluster` 행을 보장하고, 차트의 `operator.clusterId: clu_local`이 그것을 가리킵니다. 오퍼레이터는
같은 클러스터의 자기 ServiceAccount로 Kubernetes에 접근하므로 등록할 kubeconfig가 없습니다.
**할 일 없음.**

## B. 외부 클러스터 등록

등록 프로브는 대상 클러스터가 닿는지, RuntimeClass `nvidia`가 있는지, HAMi의 `nvidia.com/gpumem`을
광고하는지 확인합니다. 그런 클러스터를 만드는 법은 [`cluster-setup.md`](./cluster-setup.md).

콘솔의 **관리자 → 클러스터**에서 이름과 kubeconfig를 붙여 넣어 등록하거나 API로:

```bash
curl -sX POST https://<console>/api/v1/clusters \
  -H "Authorization: Bearer $ADMIN_JWT" -H "Idempotency-Key: $(uuidgen)" \
  -d "{\"name\":\"gpu-a\",\"role\":\"primary\",\"kubeconfig_b64\":\"$(base64 -w0 <kubeconfig)\"}"
```

프로브가 성공하면 `clu_…` id를 돌려줍니다. 시크릿 참조만 저장되며, kubeconfig는 검증에 한 번
쓰이고 이후 모든 I/O는 투영된 파일이나 오퍼레이터의 ServiceAccount를 거칩니다.

## C. Compose 제어 플레인 + 외부 GPU 클러스터

Compose는 일반 HTTP를 제공하며 앞에 TLS 종단 리버스 프록시를 기대합니다
([`docker-compose.yml`](../docker-compose.yml)의 주석 참고). 제어 플레인의 `/internal/*`
엔드포인트와 JWKS는 **외부 클러스터에서 닿아야** 합니다. `/internal`은 내부 JWT로 보호되고, JWKS는
공개이며 검증 전용입니다.

> **여기서는 세션 라우팅이 중요합니다.** 세션 URL은
> `{GSHARE_SESSION_DOMAIN}/proxy/{cr}/{code|lab|terminal}`인데, 이 토폴로지에서는 콘솔(Compose
> 프런트엔드)과 세션 앱(외부 클러스터의 ingress-nginx)이 *다른 백엔드*입니다. 따라서 리버스
> 프록시는 **`/proxy/`만** 클러스터 인그레스로, 나머지는 콘솔로 보내야 합니다. 이 분리가 없으면
> `/proxy/…`가 콘솔 SPA에 떨어져 사용자는 클라이언트 404를 봅니다. nginx라면:
>
> ```nginx
> location /proxy/ {                          # 세션 앱 → 클러스터 인그레스(NodePort 30080)
>     proxy_pass http://<cluster-node>:30080;
>     proxy_set_header Host $host;            # GSHARE_SESSION_DOMAIN과 같아야 함, 인그레스가 매칭
>     proxy_http_version 1.1;                 # code-server와 터미널은 WebSocket 사용
>     proxy_set_header Upgrade $http_upgrade;
>     proxy_set_header Connection "upgrade";
>     proxy_read_timeout 3600s;
> }
> location / { proxy_pass http://<compose-host>:8000; }   # 콘솔
> ```
>
> 더 단순한 대안은 전용 세션 도메인 — 예: `sessions.example.com` — 을 클러스터 인그레스로 직접
> 향하게 하고 `GSHARE_SESSION_DOMAIN`과 오퍼레이터의 `SESSION_DOMAIN`을 그것으로 두는 것입니다.
> 그러면 호스트로 분리되므로 경로 규칙이 필요 없습니다.
>
> **가장 쉬운 선택**은 콘솔이 중계하게 하는 것입니다. 프록시가 경로로 분리할 수 없으면 `.env`에
> `GSHARE_SESSION_INGRESS=<cluster-node>:30080`을 두세요. Compose 프런트엔드(nginx)가 `/proxy/`를
> WebSocket 포함해 그 클러스터 인그레스로 중계하고, 외부 프록시는 모든 것을 프런트엔드로
> 전달하기만 하면 됩니다. 외부 클러스터 하나를 처리하며, 클러스터 인그레스가 `/proxy/`를 직접
> 라우팅하는 올인원 Kubernetes 설치에서는 비워 둡니다.

1. **내부 콜백 활성화** — RS256 키를 생성한 뒤 시작:

   ```bash
   ./hack/gen-secrets.sh   # GSHARE_INTERNAL_JWT_PRIVATE_KEY와 KID를 .env에 기록
   make compose-up         # 키가 없으면 둘러보기 전용: 어떤 오퍼레이터도 붙을 수 없음
   ```

2. **클러스터 등록**(B절)하고 `clu_id`를 적어 둡니다.

3. **kubeconfig 제공** — 제어 플레인이 커스텀 리소스를 적용할 수 있도록:

   ```bash
   mkdir -p deploy/clusters/<clu_id> && cp <kubeconfig> deploy/clusters/<clu_id>/kubeconfig
   ```

   Compose는 그 디렉터리를 `/run/gshare/clusters`에 읽기 전용으로 마운트합니다 —
   [`deploy/clusters/README.md`](../deploy/clusters/README.md) 참고. 파일은 git 무시됩니다.

4. **GPU 클러스터에 데이터 플레인 배포.** 클러스터가 이미 [`cluster-setup.md`](./cluster-setup.md)
   대로 준비되었다고 가정합니다(`cluster-bootstrap.sh up`, 즉 GPU, HAMi, CRIU 노드 준비 완료).

   **권장 — 전체 기능의 Helm 데이터 플레인.** 올인원 설치와 같은 차트에서 제어 플레인만
   끕니다(`controlPlane.enabled=false`). 오퍼레이터, CRD, Pod Security가 적용된 네임스페이스, RBAC,
   HAMi 모니터 유휴 회수, 무손실 에이전트, lend-guard 웹훅 — 올인원과 똑같이. 이 명령은 Compose
   API로 토큰도 발급해 시크릿을 주입합니다.

   ```bash
   KUBECONFIG=<target cluster kubeconfig> \
     make deploy-dataplane CLUSTER_ID=<clu_id> CONTROL_PLANE_URL=http://<compose-host>:8080
   ```

   `CONTROL_PLANE_URL`은 **오퍼레이터 파드와 ingress-nginx 양쪽에서** 닿아야 합니다. 오퍼레이터는
   상태 콜백에, 인그레스는 세션 forward-auth에 씁니다. 세션 도메인은
   `-f deploy/values/domain.yaml` 또는 `--set global.domains.console=`로 설정합니다. 토큰 TTL
   기본값은 7일(`JWT_TTL`)이며, 만료 전에 `make dataplane-token CLUSTER_ID=<clu_id>`로 시크릿만
   갱신합니다.

   **대안 — 최소 단일 스크립트.** 유휴 회수, 무손실 일시정지, 웹훅 없이 코어 세션 + 콜드
   일시정지만 빠르게 구성할 때.
   [`hack/deploy-operator.sh`](../hack/deploy-operator.sh)가 CRD, 네임스페이스, ServiceAccount,
   RBAC, 시크릿, 디플로이먼트를 `kubectl` 한 번에 적용합니다.

   ```bash
   TOKEN=$(make -s compose-operator-token CLUSTER_ID=<clu_id>)   # 내부 JWT, 24h TTL
   CLUSTER_ID=<clu_id> SOT_ENDPOINT=https://<public control-plane URL> OPERATOR_TOKEN="$TOKEN" \
     KUBECONFIG=<target cluster kubeconfig> SESSION_DOMAIN=<제어 플레인의 GSHARE_SESSION_DOMAIN과 동일> \
     ./hack/deploy-operator.sh
   ```

   `connect-verify-url`과 `internal-jwks-url`은 `SOT_ENDPOINT`에서 도출되며, 오퍼레이터 이미지는
   `IMAGE`로 바꿉니다.

   > ⚠️ **`SESSION_DOMAIN`은 제어 플레인의 `GSHARE_SESSION_DOMAIN`과 같아야 합니다.** 세션 인그레스
   > 호스트가 여기서 생성되고, 제어 플레인도 같은 값으로 연결 URL을 만듭니다. 다르면 인그레스
   > 호스트가 절대 매칭되지 않아 모든 연결 시도가 404입니다. `SESSION_DOMAIN`을 비우면 스크립트가
   > 제어 플레인 `.env`의 `GSHARE_SESSION_DOMAIN`을 쓰므로 비워 두는 것이 가장 안전합니다. 기존
   > 세션은 만들 때의 인그레스를 유지하므로 도메인을 바꾼 뒤에는 다시 만들어야 합니다.

5. **확인** — 오퍼레이터 로그에서 콜백이 200을 돌려주고, 콘솔에서 클러스터가 `connected`로
   보이고, 노드·GPU 인벤토리가 나타나고, 세션을 만들면 그 클러스터에 커스텀 리소스가 적용됩니다.

### 토큰 회전

내부 JWT는 만료 전에 갱신해야 합니다. Compose 제어 플레인은 자동으로 회전하지 않습니다.

- Helm 데이터 플레인: `make dataplane-token CLUSTER_ID=<clu_id>` — 시크릿 재주입, 7일 TTL.
- 최소 스크립트: 새 `compose-operator-token`(24시간 TTL)으로 `./hack/deploy-operator.sh` 재실행.
  시크릿을 갱신하고 롤아웃을 재시작합니다.

```bash
# 예: Compose 호스트 crontab에서 매일 02:00 회전(Helm 데이터 플레인)
0 2 * * * cd /path/to/gShare && KUBECONFIG=<target cluster kubeconfig> make -s dataplane-token CLUSTER_ID=<clu_id>
```

## D. Kubernetes 제어 플레인 + 추가 외부 클러스터

제어 플레인 자체가 Kubernetes에서 돌 때는 external-secrets가 각 kubeconfig를
`GSHARE_CLUSTER_KUBECONFIG_DIR` 아래에 투영합니다. 추가 클러스터마다 차트로 오퍼레이터를 배포하되
`operator.clusterId`를 등록된 id로, 그리고 `operator.internalJwksUrl`과
`operator.internalJwtSecret`을 설정합니다.

## 보안과 제한

- **kubeconfig는 데이터베이스에 평문으로 저장되지 않습니다** — 마운트된 파일에서 읽습니다
  (Compose에서는 `deploy/clusters/`, git 무시).
- `/internal/*`과 모든 콜백은 `aud=gshare-internal`인 RS256 내부 JWT가 필요합니다. JWKS는 공개,
  검증 전용이며 개인 키를 절대 노출하지 않습니다.
- Compose + 외부 클러스터에서는 제어 플레인의 `/internal` 엔드포인트와 JWKS가 그 클러스터에서
  닿아야 합니다 — TLS 프록시 뒤의 공개 URL. 사내망, 방화벽, split-horizon DNS는 별도 처리(VPN, 내부
  DNS 뷰)가 필요합니다.
- 내부 JWT 자동 회전은 차트의 Job과 CronJob을 통한 Kubernetes 경로에만 있습니다. Compose에서는
  만료 전에 수동으로 재발급하세요.

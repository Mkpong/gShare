---
sidebar_position: 2
title: Helm 값
---

# Helm 값

차트는 `charts/gshare`입니다. 아래 모든 키는
[`values.yaml`](https://github.com/boanlab/gshare/blob/main/charts/gshare/values.yaml)에 인라인으로
설명되어 있고, `deploy/values/`의 오버레이가 완성된 구성을 보여 줍니다(`incluster.yaml` 올인원,
`dockerhub.yaml` 외부 데이터 계층 프로덕션, `domain.example.yaml` 모든 선택 항목).

## 최상위

| 키 | 용도 |
|---|---|
| `global.imageRegistry`, `global.imagePullSecrets` | 모든 이미지의 레지스트리 접두어와 풀 시크릿 |
| `global.namespaces` | `system`(제어 플레인)과 `sessions`(워크로드) |
| `global.domains`, `global.sessionUrlScheme` | 콘솔·세션 도메인; `https` 또는 `http` |
| `controlPlane.enabled` | 오퍼레이터만 도는 클러스터(연결된 클러스터)에서는 `false` |
| `controlPlane.nodeSelector` | api, worker, frontend, 데이터 계층, 백업 잡을 노드에 고정 |
| `images.{api,worker,operator,frontend,agent}` | 구성 요소별 `repository`, `tag`, `pullPolicy`. api와 worker는 백엔드 이미지를 공유 |
| `bootstrapAdmin.email`, `bootstrapAdmin.password` | 첫 시스템 관리자. 첫 로그인 때 비밀번호 변경 강제 |
| `bootstrapLocalCluster` | 로컬 클러스터 자동 등록(올인원) |
| `postgres.*`, `redis.*` | `inCluster`면 차트가 배포; 아니면 host, port, 자격 시크릿. `postgres.backup.*`은 매일 덤프 |
| `storage.poolCapacityGb` | 풀에 값이 없을 때의 플릿 기본 풀 크기 |
| `podDisruptionBudget.enabled` | api, worker, frontend에 minAvailable 1 |
| `secrets.generate` | 차트가 비밀번호·키를 만들게 할지, 직접 줄지 |
| `ingress.*`, `ingress.internalPlane` | 콘솔 인그레스와 연결된 오퍼레이터가 호출하는 화이트리스트 내부 플레인 |
| `serviceAccounts.*` | 이름과 어노테이션 |

## `api`

| 키 | 기본값 | 용도 |
|---|---|---|
| `replicas` | 2 | uvicorn 레플리카 |
| `dbPoolSize`, `dbMaxOverflow` | 20 / 10 | SQLAlchemy 풀 |
| `buildRegistry` | | 콘솔 빌드 이미지의 레지스트리 접두어 |
| `auditRetentionDays` | 180 | 0이면 정리 안 함 |
| `nodeStaleSec` | 300 | 노드가 오프라인이 되기까지의 침묵 시간 |
| `seedSessionImages` | true | `boanlab/gshare-session` 카탈로그 시드 |
| `gpuPacking` | binpack | 분할 배치에 `binpack` 또는 `spread` |
| `volumeReclaimGraceHours` | 24 | 삭제된 볼륨 데이터 보관 시간 |

## `worker`

`replicas`, `resources`, `gracePeriodSec`(정산 유예), `yieldReservationTtlSec`.

## `operator`

| 키 | 용도 |
|---|---|
| `clusterId` | 이 오퍼레이터가 보고하는 클러스터(올인원은 `clu_local`) |
| `controlPlaneUrl` | 제어 플레인이 다른 곳에 있을 때 콜백 주소 |
| `internalJwtSecret`, `internalJwtTokenTtlSec` | 오퍼레이터 토큰과 TTL(CronJob이 매일 재서명) |
| `hamiMonitorUrl`, `prometheusUrl` | 유휴 리퍼의 사용률 소스. [관측](../operations/observability.md) 참고 |
| `perCardMode` | 세션을 예약된 정확한 카드에 고정 — 혼합 모델 플릿에 필수 |
| `volumeStorageClass`, `volumeSyncInterval` | 풀의 StorageClass와 PVC·용량 재조정 주기 |
| `sessionImagePullPolicy` | 세션 파드용 |
| `losslessAgentImage`, `migAgentImage`, `kanikoImage` | 선택적 사이드카·빌드 이미지 |
| `webhook.*`, `hamiYieldExtender` | lend-guard 어드미션 웹훅과 HAMi yield 익스텐더 |

## `frontend`, `agent`

`frontend.replicas`, `frontend.port`, `frontend.resources`; `agent.enabled`, `agent.intervalMs`,
`agent.apiUrl`, `agent.nodeSelector`, `agent.resources` —
[관측 → 노드별 에이전트](../operations/observability.md#노드별-에이전트) 참고.

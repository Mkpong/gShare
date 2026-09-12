---
sidebar_position: 2
title: Helm 값
---

# Helm 값 (Values)

gShare 배포를 위한 Helm 차트는 `charts/gshare` 경로에 위치합니다. 아래 모든 키는 [`values.yaml`](https://github.com/boanlab/gshare/blob/main/charts/gshare/values.yaml) 파일에 주석으로 상세히 설명되어 있으며, `deploy/values/` 디렉터리에서 환경별 완성된 오버레이 예시 구성을 확인할 수 있습니다 (`incluster.yaml`: 올인원 구성, `dockerhub.yaml`: 외부 데이터 계층 기반 프로덕션 구성, `domain.example.yaml`: 모든 선택 항목 포함 구성).

## 최상위 설정 (Top-level)

| 설정 키 | 용도 및 설명 |
|---|---|
| `global.imageRegistry`, `global.imagePullSecrets` | 모든 이미지의 레지스트리 접두어 및 ImagePullSecrets 설정 |
| `global.namespaces` | 네임스페이스 정의: `system` (제어 플레인), `sessions` (사용자 워크로드), `infra` (특권 노드 작업) |
| `global.domains`, `global.sessionUrlScheme` | 콘솔 및 세션 서비스 도메인, 세션 접속 프로토콜 (`https` 또는 `http`) |
| `controlPlane.enabled` | 제어 플레인 활성화 여부 (연동된 데이터 플레인 전용 클러스터에서는 `false`) |
| `controlPlane.nodeSelector` | `api`, `worker`, `frontend`, 데이터베이스 계층, 백업 CronJob을 특정 노드에 고정 배치 |
| `images.{api,worker,operator,frontend,agent}` | 구성 요소별 `repository`, `tag`, `pullPolicy` 설정 (`api`와 `worker`는 동일한 백엔드 이미지 공유) |
| `bootstrapAdmin.email`, `bootstrapAdmin.password` | 최초 시스템 관리자 계정 정보 (최초 로그인 시 비밀번호 변경 강제) |
| `bootstrapLocalCluster` | 로컬 클러스터 자동 등록 활성화 여부 (올인원 환경) |
| `postgres.*`, `redis.*` | `inCluster: true` 시 차트가 직접 배포하며, `false` 시 외부 DB 정보 지정 (`postgres.backup.*` 설정 시 일별 DB 덤프 수행) |
| `storage.poolCapacityGb` | 스토리지 풀 등록 시 미지정 상태일 때의 기본 가용 용량 (GB) |
| `podDisruptionBudget.enabled` | `api`, `worker`, `frontend` 대상 `minAvailable: 1` PDB 설정 활성화 |
| `secrets.generate` | 차트에서 비밀번호 및 인증키 자동 생성 여부 지정 (`false` 시 직접 지정 필요) |
| `ingress.*`, `ingress.internalPlane` | 콘솔 접근용 Ingress 설정 및 데이터 플레인 오퍼레이터 호출용 화이트리스트 내부 API Ingress 설정 |
| `serviceAccounts.*` | 컨트롤러 (`api`/`worker`) 및 오퍼레이터의 서비스 계정 명칭 지정 |
| `networkPolicy.*` | 세션 네임스페이스 격리를 위한 NetworkPolicy 설정 (기본값: `false`, 상세 내용은 하단 참조) |

## api 설정

| 설정 키 | 기본값 | 용도 및 설명 |
|---|---|---|
| `replicas` | `2` | Uvicorn API 서버 파드 레플리카 수 |
| `dbPoolSize`, `dbMaxOverflow` | `20` / `10` | SQLAlchemy 데이터베이스 커넥션 풀 크기 및 오버플로우 한도 |
| `buildRegistry` | `""` | 콘솔 빌드 이미지 저장용 레지스트리 접두어 |
| `auditRetentionDays` | `180` | 감사 로그 보관 기간 (일 단위, `0` 설정 시 자동 정리 비활성화) |
| `nodeStaleSec` | `300` | 노드가 오프라인 상태로 전환되는 하트비트 타임아웃 시간 (초) |
| `seedSessionImages` | `true` | 기본 `boanlab/gshare-session` 이미지 카탈로그 자동 등록 여부 |
| `gpuPacking` | `binpack` | GPU 워크로드 분할 배치 전략 (`binpack`: 집약 배치, `spread`: 분산 배치) |
| `volumeReclaimGraceHours` | `24` | 삭제 처리된 볼륨의 데이터 임시 보관 시간 (시간 단위) |
| `forwardedAllowIps` | `*` | Uvicorn이 `X-Forwarded-*` 헤더를 신뢰할 피어 IP (`--forwarded-allow-ips`, 프로덕션 환경에서는 Ingress Controller IP 대역으로 제한 권장) |
| `trustedProxyHops` | `1` | API 서버 전면에서 `X-Forwarded-For` 헤더를 추가하는 프록시 홉 수 (`GSHARE_TRUSTED_PROXY_HOPS`, Ingress 전면에 외부 L4 로드밸런서가 존재할 경우 `2`로 설정) |

## worker 설정

| 설정 키 | 용도 및 설명 |
|---|---|
| `replicas` | 백그라운드 워커 파드 레플리카 수 |
| `resources` | 워커 파드 리소스 Limit / Request 설정 |
| `gracePeriodSec` | 크레딧 소진 시 세션 일시중지 및 자원 반환까지의 유예 시간 (초) |
| `yieldReservationTtlSec` | 세션 자원 양보 및 대기열 처리 관련 예약 유지 시간 (초) |

## operator 설정

| 설정 키 | 용도 및 설명 |
|---|---|
| `clusterId` | 오퍼레이터가 관제 및 보고하는 대상 클러스터 식별자 (올인원 환경의 경우 `clu_local`) |
| `controlPlaneUrl` | 제어 플레인이 외부에 위치할 때 오퍼레이터가 제어 플레인으로 접근할 콜백 URL 주소 |
| `internalJwtSecret`, `internalJwtTokenTtlSec` | 오퍼레이터 인증용 JWT Secret 및 TTL 설정 (CronJob을 통해 주기적 재서명 수행) |
| `hamiMonitorUrl`, `prometheusUrl` | 유휴 세션 감지(Idle Reaper)를 위한 메트릭 수집 엔드포인트 ([관측성 가이드](../operations/observability.md) 참조) |
| `perCardMode` | 세션을 지정된 정확한 물리 GPU 카드에 고정 할당하는 모드 (이종 GPU 모델이 혼재된 클러스터 필수) |
| `volumeStorageClass`, `volumeSyncInterval` | 스토리지 풀의 StorageClass 명칭 및 PVC 용량 재조정/동기화 주기 |
| `sessionImagePullPolicy` | 세션 파드 컨테이너 이미지 풀 정책 (`IfNotPresent`, `Always` 등) |
| `losslessAgentImage`, `migAgentImage`, `kanikoImage` | 무손실 스냅샷 에이전트, MIG 제어 에이전트, Kaniko 이미지 빌더용 선택적 사이드카 이미지 |
| `webhook.*`, `hamiYieldExtender` | lend-guard 어드미션 웹훅 및 HAMi yield 익스텐더 관련 상세 설정 |

## networkPolicy 설정

기본값은 비활성화 상태(`networkPolicy.enabled: false`)입니다. 활성화 시 세션 네임스페이스(`sessions`)에 전체 차단(Deny-all) 정책과 지정된 허용 목록(Allowlist)이 자동 생성됩니다.

- **Ingress**: `ingressNamespace`에서 `sessionPorts`로 들어오는 트래픽 허용
- **Egress**: `dnsNamespace`로 나가는 DNS 트래픽, `storage.cidrs` 내 `storage.ports`로 나가는 스토리지 트래픽 허용
- **CPU 워크로드 전용 Egress**: `cpuData.cidrs` 지정 시, CPU 데이터 준비 세션에만 추가 적용되는 외부 나가는 트래픽 규칙 생성

클러스터 네트워크 환경에 따라 스토리지 CIDR 대역이 달라지므로 기본값은 비어 있으며 전체 정책이 꺼져 있습니다. 스토리지 CIDR 설정 없이 NetworkPolicy를 활성화하면 세션 파드에서 DNS 조회 외 모든 외부 네트워크 통신이 차단됩니다. Helm 차트를 사용하지 않는 배포 환경을 위해 동일한 매니페스트가 `deploy/security/` 디렉터리에 별도로 제공됩니다.

해당 정책은 `gshare.io/workload=session` 라벨(CPU 전용 세션의 경우 `gshare.io/resource-class=cpu` 라벨 추가)을 기반으로 파드를 선택하며, 오퍼레이터가 생성되는 모든 세션 파드에 해당 라벨을 자동 주입합니다.

## frontend 및 agent 설정

- **`frontend`**: `frontend.replicas` (레플리카 수), `frontend.port` (서비스 포트), `frontend.resources` (파드 리소스)
- **`agent`**: `agent.enabled` (에이전트 활성화 여부), `agent.intervalMs` (수집 주기), `agent.apiUrl` (API 엔드포인트), `agent.nodeSelector`, `agent.resources` — 상세 내용은 [관측성 → 노드별 에이전트](../operations/observability.md#노드별-에이전트-daemonset) 문서를 참조하세요.
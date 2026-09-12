---
sidebar_position: 4
title: 백업과 복구
---

# 백업과 복구

gShare 플랫폼의 모든 영구 상태 데이터(사용자, 크레딧, 세션, 볼륨 메타데이터, 감사 로그 등)는 **Postgres 데이터베이스**에 저장됩니다. Redis는 휘발성 데이터(대기열 티커, 멱등성 키, 실시간 메트릭 샘플 등)만 처리하므로 별도의 백업이 필요하지 않습니다. 세션 사용자 데이터 및 볼륨은 스토리지 풀 백엔드에 위치하며, 스토리지 서버 자체의 백업 및 스냅샷 정책을 따릅니다.

## 클러스터 내 Postgres (In-Cluster Postgres)

`postgres.inCluster: true` 설정(올인원 및 단일 클러스터 설치 환경) 사용 시, Helm 차트는 자체 PVC를 생성하고 매일 `pg_dump` 백업을 수행하는 CronJob을 자동으로 구성합니다.

```yaml
postgres:
  backup:
    enabled: true
    schedule: "0 3 * * *"
    storage: 10Gi
    keep: 14          # 보관할 백업 파일 수
```

백업 덤프 파일은 `gshare-system` 네임스페이스 내 `gshare-pg-backup` PVC에 저장됩니다. 해당 PVC는 동일 노드 상의 일시적 보관용이므로, 주기적으로 외부 오프사이트 스토리지로 파일 복사를 진행하는 것을 권장합니다.

### 복구 절차

```bash
# 1. API 및 Worker 파드 축소 (데이터베이스 접근 중단)
kubectl scale deploy/gshare-api deploy/gshare-worker -n gshare-system --replicas=0

# 2. 백업 SQL 덤프 복원
kubectl exec -n gshare-system deploy/gshare-pg -- \
  sh -c 'psql -U gshare -d gshare < /backup/gshare-YYYYMMDD.sql'

# 3. API 및 Worker 파드 원복
kubectl scale deploy/gshare-api deploy/gshare-worker -n gshare-system --replicas=2
```

데이터베이스 복원 시점에 실행 중이던 세션은 데이터 플레인 오퍼레이터가 보유한 `GShareSession` 커스텀 리소스를 통해 자동으로 동기화 및 재조정(Reconcile)됩니다. 다운타임 동안 종료된 세션은 API 서비스 재개 시 헬스 체크 및 세션 검증 프로세스에 의해 정상 정산 처리됩니다.

## 외부 Postgres (External Postgres)

프로덕션 환경(`postgres.inCluster: false`)에서는 외부 매니지드 데이터베이스 서비스(AWS RDS, GCP Cloud SQL 등) 또는 CloudNativePG 오퍼레이터를 통한 데이터베이스 구성을 권장하며, 백업 및 시점 복구(PITR)는 해당 스토리지/DB 솔루션의 기능을 활용합니다. Helm 차트에는 접속 자격 증명 시크릿(`postgres.credentialsSecret`)만 지정하면 됩니다.

## 기타 백업 대상 항목

- **Helm Values 구성 파일**: 시스템 설치/배포에 사용된 Helm 설정 파일 (`deploy/values/*.yaml`, 민감 정보 제외)
- **내부 JWT 서명 시크릿**: 수동으로 관리/회전하는 경우 `operator.internalJwtSecret` 값을 백업합니다 (기본 설정 시 차트의 CronJob이 자동 재발급함).
- **CSI 스토리지 설정 파일**: 연동된 클러스터에서 사용하는 democratic-csi 가치 설정 파일 (`csi-values.yaml` 등)은 저장소 외부에 안전하게 보관하세요.
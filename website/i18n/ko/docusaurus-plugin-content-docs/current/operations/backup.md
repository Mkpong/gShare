---
sidebar_position: 4
title: 백업과 복구
---

# 백업과 복구

gShare가 아는 모든 것 — 사용자, 크레딧, 세션, 볼륨, 감사 — 은 **Postgres**에 있습니다. Redis는
일시적 상태(대기열 티커, 멱등성 키, 실시간 샘플)만 가지므로 백업이 필요 없습니다. 사용자 데이터는
스토리지 풀에 있으며 스토리지 서버 자체의 백업 정책을 따릅니다.

## 클러스터 내 Postgres

`postgres.inCluster: true`(올인원 설치)이면 차트는 자체 PVC로 매일 `pg_dump`하는 CronJob도
렌더링합니다.

```yaml
postgres:
  backup:
    enabled: true
    schedule: "0 3 * * *"
    storage: 10Gi
    keep: 14          # 보관할 덤프 수
```

덤프는 `gshare-system`의 `gshare-pg-backup` PVC에 있습니다. 정기적으로 클러스터 밖으로 복사하세요.
같은 노드의 PVC는 안전망이지 오프사이트 백업이 아닙니다.

### 복구

```bash
kubectl scale deploy/gshare-api deploy/gshare-worker -n gshare-system --replicas=0
kubectl exec -n gshare-system deploy/gshare-pg -- \
  sh -c 'psql -U gshare -d gshare < /backup/gshare-YYYYMMDD.sql'
kubectl scale deploy/gshare-api deploy/gshare-worker -n gshare-system --replicas=2
```

덤프 시점에 실행 중이던 세션은 오퍼레이터가 여전히 가진 `GShareSession` 리소스로부터 재조정되고,
그 사이에 끝난 세션은 API가 돌아올 때 생존 판정 규칙으로 정산됩니다.

## 외부 Postgres

프로덕션 설치(`postgres.inCluster: false`)는 외부 데이터베이스 — CloudNativePG, 매니지드 서비스 —
를 가리키고 그쪽의 백업과 시점 복구를 씁니다. 차트에는 연결 시크릿(`postgres.credentialsSecret`)만
필요합니다.

## 그 밖에 보관할 것

- 설치에 쓴 Helm 값(`deploy/values/*.yaml`), 시크릿 제외.
- 직접 회전한다면 **내부 JWT** 서명 시크릿(`operator.internalJwtSecret`). 그렇지 않으면 차트의
  CronJob이 재발급합니다.
- 연결된 클러스터용 democratic-csi 값 파일. 저장소 밖에 보관.

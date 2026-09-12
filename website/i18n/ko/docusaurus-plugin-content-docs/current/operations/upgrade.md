---
sidebar_position: 3
title: 업그레이드
---

# 시스템 업그레이드 (Upgrade)

gShare 플랫폼은 단일 Helm 릴리스 형태로 관리됩니다. 시스템 업그레이드는 신규 컨테이너 이미지 태그를 지정하여 `helm upgrade` 명령을 실행하는 방식으로 진행되며, 내부 스키마 마이그레이션 및 구성 요소 롤링 업데이트는 Helm 차트가 자동으로 수행합니다.

---

## 업그레이드 프로세스 동작 순서

1. **DB 스키마 마이그레이션**: 신규 API 파드가 구동되기 전, API 디플로이먼트의 init 컨테이너에서 마이그레이션이 자동 실행됩니다 (`alembic upgrade head`). 스키마 변경 사항은 하위 호환성을 보장하도록 추가형(Additive)으로 작성되므로, 롤링 업데이트 진행 중 다운타임(Downtime)이 발생하지 않습니다.
2. **API 및 Worker 파드 롤링 업데이트**: `api` 및 `worker` 디플로이먼트가 순차적으로 업데이트됩니다 (기본 각 2 레플리카, PodDisruptionBudget(PDB) 적용).
3. **오퍼레이터(Operator) 롤링 업데이트**: 리더 선출(Leader Election) 방식을 사용하며 `GShareSession` 커스텀 리소스(CRD)를 상태 원천(Source of Truth)으로 관리하므로, 업그레이드 중에도 실행 중인 세션 파드는 영향을 받지 않으며 신규 오퍼레이터가 상태 관리를 승계합니다.
4. **프론트엔드(Frontend) 롤링 업데이트**: 콘솔 UI 서비스 파드가 최신 버전으로 순차 교체됩니다.

> **CRD 업데이트 주의사항**: `charts/gshare/crds/` 내의 `GShareSession` CRD 매니페스트는 Helm 설치 시점에만 최초 적용됩니다. 신규 릴리스에서 CRD 정의가 변경된 경우, `helm upgrade` 실행 전 CRD 매니페스트를 직접 수동 적용해야 합니다.

```bash
kubectl apply -f charts/gshare/crds/
```

---

## 업그레이드 실행 명령

### 공개 이미지 기반 업그레이드

```bash
helm upgrade gshare charts/gshare -n gshare-system --reuse-values \
  --set images.api.tag=v0.2.0 --set images.worker.tag=v0.2.0 \
  --set images.operator.tag=v0.2.0 --set images.frontend.tag=v0.2.0

# API 배포 상태 확인
kubectl rollout status deploy/gshare-api -n gshare-system
```

소스 코드 체크아웃 환경에서는 최초 설치 시 사용했던 오버레이 구성 파일(`deploy/values/*.yaml`)을 지정하여 `make deploy-incluster` 또는 `make prod-deploy` 명령으로 업그레이드를 수행할 수 있습니다.

---

## 연동된 데이터 플레인 클러스터 업그레이드

연동된 데이터 플레인 클러스터에는 각 클러스터 전용 오퍼레이터 릴리스가 실행 중입니다.

1. 클러스터 연동 시 사용했던 `hack/attach-cluster.sh` 스크립트를 동일한 파라미터 옵션으로 재실행하거나,
2. 대상 클러스터의 `kubeconfig` 환경에서 신규 오퍼레이터 태그를 지정하여 `helm upgrade`를 실행합니다.

> **업그레이드 순서**: 데이터 플레인 오퍼레이터는 자신보다 높은 버전의 제어 플레인과 호환되도록 설계되어 있습니다. 반드시 **제어 플레인 클러스터를 먼저 업그레이드**한 후 데이터 플레인 클러스터의 오퍼레이터를 순차적으로 업그레이드하세요.

---

## 롤백 (Rollback)

업그레이드 이전 버전으로 복구가 필요한 경우 `helm rollback` 명령을 실행합니다.

```bash
helm rollback gshare <REVISION_NUMBER> -n gshare-system
```

`helm rollback` 명령은 컨테이너 이미지를 이전 버전으로 원복합니다. 다만 데이터베이스 스키마 마이그레이션은 자동으로 되돌려지지 않으므로, 신규 스키마에서 이전 버전 API가 동작할 수 있도록 하위 호환성이 유지됩니다.

만약의 상황에 대비하여 업그레이드 작업 수행 전 반드시 데이터베이스 **[백업](./backup.md)**을 진행하시는 것을 권장합니다.
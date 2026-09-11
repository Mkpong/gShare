---
sidebar_position: 3
title: 업그레이드
---

# 업그레이드

gShare는 Helm 릴리스 하나입니다. 업그레이드는 새 이미지 태그로 `helm upgrade`하는 것이고, 나머지는
차트가 합니다.

## 업그레이드 때 일어나는 일

1. **스키마 마이그레이션**이 새 API가 뜨기 전에 API 디플로이먼트의 init 컨테이너에서
   실행됩니다(`alembic upgrade head`). 마이그레이션은 추가형이고 이전 릴리스 파드와 호환되므로
   롤링 업데이트에 다운타임이 필요 없습니다.
2. **API**와 **워커**가 롤링됩니다(기본 각 2 레플리카, PodDisruptionBudget 적용).
3. **오퍼레이터**가 롤링됩니다. 리더 선출 방식이고 `GShareSession` 커스텀 리소스가 진실의
   원천이므로 실행 중 세션은 건드리지 않습니다 — 새 오퍼레이터가 이어받습니다.
4. **프런트엔드**가 롤링됩니다.

`charts/gshare/crds/`의 `GShareSession` CRD는 Helm이 설치 때만 적용합니다. 릴리스가 CRD를 바꿨다면
먼저 직접 적용하세요.

```bash
kubectl apply -f charts/gshare/crds/
```

## 명령

공개 이미지:

```bash
helm upgrade gshare charts/gshare -n gshare-system --reuse-values \
  --set images.api.tag=v0.2.0 --set images.worker.tag=v0.2.0 \
  --set images.operator.tag=v0.2.0 --set images.frontend.tag=v0.2.0
kubectl rollout status deploy/gshare-api -n gshare-system
```

또는 체크아웃에서 설치 때와 같은 오버레이(`deploy/values/*.yaml`)로 `make deploy-incluster` /
`make prod-deploy`.

## 연결된 클러스터

연결된 클러스터마다 자체 오퍼레이터 릴리스가 돕니다. 연결할 때 쓴 `hack/attach-cluster.sh`를 같은
인자로 다시 실행하거나, 그 클러스터의 kubeconfig로 새 오퍼레이터 태그를 `helm upgrade`하세요.
오퍼레이터는 더 새로운 제어 플레인을 허용하므로 제어 플레인을 먼저 올리세요.

## 롤백

`helm rollback gshare <revision>`이 이전 이미지를 복원합니다. 마이그레이션은 자동으로 되돌리지
않습니다. 릴리스는 이전 API가 새 스키마에서 돌도록 호환성을 유지합니다. 어쨌든 업그레이드 전에
[백업](./backup.md)을 받으세요.

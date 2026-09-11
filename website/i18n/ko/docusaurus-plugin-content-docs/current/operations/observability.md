---
sidebar_position: 2
title: 관측
---

# 관측

gShare는 모니터링 스택 없이도 동작합니다 — 제어 플레인은 모든 세션·할당·크레딧 이동을 스스로
압니다 — 하지만 세 가지에는 지표가 필요합니다. 관리자 모니터링 페이지, 세션별 사용량 이력, 그리고
유휴 리퍼의 *워크로드 인지* 유휴 판정.

## 모니터링 스택

```bash
make deploy-monitoring      # kubectl apply -f deploy/monitoring/monitoring-stack.yaml
```

`monitoring` 네임스페이스에 다음을 설치합니다.

| 구성 요소 | 위치 | 제공 |
|---|---|---|
| dcgm-exporter | 모든 GPU 노드 | 물리 카드별 `DCGM_FI_DEV_*`(UUID 라벨) |
| node-exporter | 모든 노드 | 호스트 CPU, 메모리, 디스크, 네트워크 |
| kube-state-metrics | 파드 하나 | 파드·노드 객체 상태(재시작, 단계) |
| kubelet cAdvisor | 그 자리에서 수집 | 파드별 CPU, 메모리, 네트워크, 디스크 |
| HAMi vGPU 모니터 | 그 자리에서 수집 | `hami_host_gpu_*`(`kube-system`에 이미 실행 중) |
| Prometheus | 파드 하나, 기본 StorageClass에 30일 PVC | 기록 |

Prometheus는 클러스터 밖에 노출되지 않습니다. 콘솔은 `gshare-api`를 통해 지표를 읽으며, API가
쿼리를 화이트리스트로 제한하고 시스템 관리자 권한을 강제합니다.

## 오퍼레이터 연결

유휴 리퍼는 정책의 유휴 시간 동안 카드가 놀고 있는 GPU 세션을 일시정지합니다. 사용률 소스가
필요합니다.

- `operator.hamiMonitorUrl`(기본값) — HAMi 자체 모니터. 추가 인프라 없음. GPU 노드가 둘 이상인
  클러스터에서는 모니터가 노드별 파드를 라운드로빈하므로 Prometheus를 쓰세요.
- `operator.prometheusUrl: http://prometheus.monitoring.svc:9090` — 위 스택의
  `DCGM_FI_DEV_GPU_UTIL`. 설정되면 우선합니다.

둘 다 없으면 유휴 회수는 꺼지고 최대 실행 시간 상한만 적용됩니다.

## 노드별 에이전트

`agent.enabled: true`는 각 세션의 cgroup 카운터를 1초마다 샘플링해 세션 페이지의 **실시간 사용량**
패널에 공급하는 DaemonSet을 배포합니다. Prometheus가 기록으로 남고, 에이전트는 1초 실시간 뷰일
뿐이며 아무것도 에이전트에 의존하지 않습니다.

## 헬스와 경보

- API의 `/health`는 데이터베이스와 Redis 도달 여부를 보고합니다.
- 오퍼레이터는 1분마다 노드 인벤토리를 보냅니다. `api.nodeStaleSec` 동안 침묵한 노드는
  **오프라인**이 되고 모든 시스템 관리자에게 알림이 갑니다. DCGM의 치명적 Xid 이벤트는 노드를
  차단합니다.
- 감사 로그는 `access.denied` 항목을 분당 중복 제거해 기록하므로, 잘못 동작하는 클라이언트를 로그
  긁기 없이 볼 수 있습니다.

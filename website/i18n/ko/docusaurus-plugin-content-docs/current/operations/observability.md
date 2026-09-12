---
sidebar_position: 2
title: 관측성 및 모니터링
---

# 관측성 및 모니터링

gShare는 별도의 모니터링 스택 없이도 기본 작동이 가능합니다. 제어 플레인이 모든 세션, 리소스 할당, 크레딧 변동 상태를 자체적으로 추적하기 때문입니다. 다만 아래 3가지 기능을 활용하기 위해서는 메트릭 수집 및 모니터링 스택 설정이 필요합니다.

1. 관리자 전용 통합 모니터링 대시보드
2. 세션별 상세 사용량 이력 및 모니터링
3. 유휴 리퍼(Idle Reaper)의 *워크로드 감지* 기반 유휴 상태 판정

---

## 모니터링 스택 배포

```bash
make deploy-monitoring      # kubectl apply -f deploy/monitoring/monitoring-stack.yaml
```

`monitoring` 네임스페이스에 다음 모니터링 구성 요소들이 배포됩니다.

| 구성 요소 | 배포 위치 / 수집 대상 | 제공 정보 |
|---|---|---|
| **dcgm-exporter** | 모든 GPU 노드 (DaemonSet) | 물리 카드별 GPU 메트릭 (`DCGM_FI_DEV_*`, GPU UUID 라벨 포함) |
| **node-exporter** | 모든 노드 (DaemonSet) | 호스트 노드의 CPU, 메모리, 디스크, 네트워크 메트릭 |
| **kube-state-metrics** | 단일 파드 | 파드 및 노드 Kubernetes 객체 상태 (재시작 횟수, 실행 단계 등) |
| **kubelet cAdvisor** | Kubelet 기본 제공 | 파드 단위 CPU, 메모리, 네트워크, 디스크 사용량 |
| **HAMi vGPU 모니터** | Kubelet 기본 제공 (`kube-system`) | vGPU 할당 및 사용 메트릭 (`hami_host_gpu_*`) |
| **Prometheus** | 단일 파드 (기본 StorageClass, 30일 보관 PVC) | 전체 메트릭 시계열 저장 및 시계열 데이터 관리 |

Prometheus 엔드포인트는 외부 네트워크에 직접 노출되지 않습니다. 콘솔 UI는 `gshare-api` 백엔드를 통해 메트릭을 조회하며, API 서버가 허용된 화이트리스트 쿼리만 제한적으로 수행하고 관리자 권한을 검증합니다.

---

## 오퍼레이터 메트릭 연동

유휴 리퍼(Idle Reaper) 프로세스는 자원 정책에 설정된 유휴 시간 동안 실제 작업이 없는 GPU 세션을 자동으로 감지하여 일시 중지 처리합니다. 이를 위해 GPU 사용률 데이터를 수집하는 소스 설정이 필요합니다.

- **`operator.hamiMonitorUrl` (기본값)**: HAMi 자체 모니터링 엔드포인트를 사용합니다. 별도 모니터링 스택 구축 없이 동작합니다. 단, GPU 노드가 2개 이상인 멀티 노드 환경에서는 모니터가 노드별 파드를 라운드 로빈 방식으로 수집하므로 Prometheus 사용을 권장합니다.
- **`operator.prometheusUrl`**: `http://prometheus.monitoring.svc:9090`  
  Prometheus 스택의 `DCGM_FI_DEV_GPU_UTIL` 메트릭을 기반으로 유휴 상태를 정밀하게 판정합니다. 이 설정이 지정되면 HAMi 모니터보다 우선적으로 적용됩니다.

> 두 소스가 모두 설정되어 있지 않은 경우 자동 유휴 세션 회수 기능은 비활성화되며, 최대 실행 시간 제한 정책만 적용됩니다.

---

## 노드별 에이전트 (DaemonSet)

`agent.enabled: true` 설정 시 각 노드에 에이전트 DaemonSet이 배포됩니다. 에이전트는 세션의 cgroup 카운터를 1초 간격으로 실시간 샘플링하여, 사용자 콘솔 세션 상세 페이지의 **실시간 사용량** 차트에 데이터를 제공합니다. 

Prometheus가 장기 세션 이력을 기록하는 반면, 에이전트는 1초 단위의 실시간 대시보드 시각화 전용이며 시스템 핵심 기능은 에이전트 의존성 없이 독립적으로 동작합니다.

---

## 헬스 체크 및 경보 시스템

- **API 헬스 체크**: `/healthz` 엔드포인트는 API 서버의 단순 생존 프로브(Liveness Probe)이며, 데이터베이스나 Redis 연동 상태는 별도로 다룹니다.
- **노드 헬스 체크**: 데이터 플레인 오퍼레이터는 15초 간격으로 노드 인벤터리 상태를 제어 플레인으로 전송합니다. `api.nodeStaleSec` 시간 동안 하트비트 응답이 없는 노드는 **오프라인(Offline)** 상태로 전환되며 시스템 관리자에게 즉시 알림이 발송됩니다. 또한 DCGM에서 치명적 Xid 오류가 감지되면 해당 노드는 자동으로 차단(Cordon) 처리됩니다.
- **감사 및 접근 통제 로그**: 접근 거부 이벤트(`access.denied`) 발생 시 분 단위로 중복 제거되어 감사 로그에 기록됩니다. 별도의 외부 로그 수집기 없이도 비정상 요청이나 클라이언트 이상 동작을 확인할 수 있습니다.
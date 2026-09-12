---
sidebar_position: 1
title: 스토리지
---

# 스토리지

gShare의 사용자 볼륨은 세션이 실행되는 데이터 플레인 클러스터의 오퍼레이터가 `operator.volumeStorageClass`로 지정된 StorageClass 기반으로 생성하는 PersistentVolumeClaim(PVC)입니다. gShare 플랫폼은 스토리지 계층을 직접 제어하지 않으며, **스토리지 풀** 등록, 풀 용량 기반 볼륨 할당 검증, 최초 마운트된 클러스터 대상 볼륨 고정(Pinning) 관리 역할을 수행합니다.

---

## 레퍼런스 스토리지 구성

기본 권장 구성은 단일 **ZFS + NFS 스토리지 노드**를 [democratic-csi](https://github.com/democratic-csi/democratic-csi) 드라이버를 통해 모든 클러스터에 프로비저닝하는 아키텍처입니다.

* **드라이버 배포**: `cluster-bootstrap.sh` 실행 시 `deploy/storage/democratic-csi-values.yaml` 설정을 기반으로 제어 플레인 클러스터에 CSI 드라이버를 설치하여 `gshare-data` StorageClass를 생성합니다.
* **노드 사전 조건**: 모든 Kubernetes 노드에 NFS 클라이언트 패키지(`nfs-common` 또는 `nfs-utils`)가 설치되어 있어야 하며, 스토리지 서버 간 `2049/tcp` 방화벽 포트가 개방되어야 합니다.
* **오퍼레이터 설정**: 오퍼레이터 실행 시 `--volume-storage-class gshare-data` 파라미터를 지정합니다.

> 상세한 스토리지 노드 준비 절차는 [클러스터 구축 → 스토리지 노드 구성](../cluster-setup.md#storage-node-optional-volumes-with-a-real-quota) 가이드를 참조하세요. 클러스터 내 모든 노드에서 마운트 가능한 ReadWriteMany(RWX) 볼륨 생성을 지원하는 CSI 드라이버라면 어느 것이든 동일한 방식으로 연동 가능합니다.

---

## 스토리지 풀 등록

스토리지 풀은 노드 역할에 의해 자동 추론되지 않으며, 플랫폼 관리자가 직접 등록하는 개체입니다. 콘솔 UI(**자원 → 볼륨 관리 → 스토리지 풀**, [관리자 가이드 → 스토리지](../admin/storage.md#스토리지-서버-등록-절차) 참조) 또는 `POST /api/v1/storage/pools` API를 통해 등록합니다.

| 속성 항목 | 설명 및 규격 |
|---|---|
| `cluster_id` | 스토리지 서버가 위치한 원천 클러스터 식별자 |
| `storage_class` | 해당 풀에서 프로비저닝하는 StorageClass 명칭 (오퍼레이터 설정값과 동일) |
| `share_scope` | **`all`**: 플릿 내 모든 클러스터에서 볼륨 배치 허용 (NFS 공유 일반 형태)<br/>**`selected`**: 명시적으로 지정한 허용 클러스터 목록으로 범위 제한 |
| `manual_capacity_gb` | CSI 드라이버에서 용량 메트릭을 제공하지 않을 때 사용하는 명시적 가용 용량 (GB) |

스토리지 서버가 여러 대인 경우 각각의 스토리지 풀로 등록하여 관리합니다. 단일 볼륨은 특정 스토리지 풀에 귀속되며 PVC의 StorageClass에 의해 위치가 결정되므로, 대시보드의 용량 제한 및 할당 정책 평가 시 전체 풀의 단순 합산이 아닌 사용 가능한 풀 중 **가장 가용 용량이 큰 스토리지 풀**을 기준으로 산정합니다.

---

## 용량 메트릭 산정 출처

스토리지 풀의 가용 용량 산정 시 다음 3가지 우선순위에 따라 메트릭 소스를 수집합니다.

1. **`csi` (자동 수집)**: CSI 드라이버의 `GetCapacity` 메트릭을 활용합니다. external-provisioner가 `CSIStorageCapacity` 객체로 용량을 수집하며, 오퍼레이터가 볼륨 동기화 주기마다 이를 읽어옵니다.
   * *선결 조건*: 프로비저너 옵션에 `--enable-capacity` 및 `--capacity-for-immediate-binding=true` 설정이 필요하며, CSI 드라이버가 노드 토폴로지(Topology) 정보를 정상적으로 보고해야 합니다.
2. **`manual` (수동 지정)**: 스토리지 풀 설정에 직접 입력된 명시적 용량 정보입니다. `STORAGE_POOL_CAPACITY_GB`(Helm 차트의 `storage.poolCapacityGb`) 값은 플릿 기본 설정값으로 적용됩니다.
3. **`node_disk` (대체 메트릭)**: 스토리지 노드 루트/시스템 디스크의 가용 용량을 대체 측정값으로 활용합니다.

콘솔 대시보드의 스토리지 현황 타일에서 현재 사용 중인 용량 메트릭 출처를 확인할 수 있습니다.

---

## 연동 클러스터 설정

추가 연동되는 데이터 플레인 클러스터에서도 동일한 스토리지 서버를 가리키는 동일 CSI 드라이버 설정이 필요합니다. 제어 플레인에서 드라이버 설정값을 내보낸 후 `attach-cluster.sh` 연동 스크립트에 전달합니다.

```bash
# 제어 플레인에서 CSI 설정값 추출
helm -n gshare-storage get values gshare-storage > csi-values.yaml && chmod 600 csi-values.yaml

# csi-values.yaml 내 controller.nodeSelector 항목을 신규 클러스터 노드로 수정한 후 연동 실행
./hack/attach-cluster.sh ... --storage-values csi-values.yaml
```

> **보안 주의사항**: 추출된 `csi-values.yaml` 파일에는 스토리지 서버 접속용 SSH Private Key가 포함되어 있습니다. 코드 저장소 외부에 안전하게 보관하고 클러스터 연동 완료 후 즉시 삭제하세요. 상세 내용은 [멀티 클러스터 가이드](../multi-cluster.md#볼륨-및-스토리지)를 참조하세요.

---

## 볼륨 자원 회수 (Reclaim)

사용자에 의해 삭제된 볼륨의 PVC는 `api.volumeReclaimGraceHours` 설정값(기본값: 24시간) 동안 임시 보관 상태를 유지합니다. 유예 기간 경과 후 오퍼레이터가 PVC를 최종 삭제하고 백엔드 CSI 드라이버가 실제 데이터셋을 지웁니다. 해당 값을 `0`으로 설정하면 다음 동기화 사이클에 즉시 회수 및 삭제됩니다.
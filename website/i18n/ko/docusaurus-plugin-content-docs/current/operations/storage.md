---
sidebar_position: 1
title: 스토리지
---

# 스토리지

사용자 볼륨은 세션이 배치된 클러스터의 오퍼레이터가 `operator.volumeStorageClass`로 지정된
StorageClass에서 만드는 PersistentVolumeClaim입니다. gShare 자체는 스토리지를 건드리지 않습니다.
**풀**을 등록하고, 풀 용량에 맞춰 볼륨을 승인하고, 각 볼륨을 처음 마운트된 클러스터에 고정할
뿐입니다.

## 기준 구성

기준 설치는 **ZFS + NFS 스토리지 노드** 하나를
[democratic-csi](https://github.com/democratic-csi/democratic-csi)로 모든 클러스터에 제공하는
구성입니다.

- `cluster-bootstrap.sh`가 `deploy/storage/democratic-csi-values.yaml`의 값으로 제어 플레인
  클러스터에 드라이버를 설치해 `gshare-data` StorageClass를 만듭니다.
- 모든 노드에 NFS 클라이언트(`nfs-common` / `nfs-utils`)와 스토리지 서버 2049/tcp로의 네트워크
  경로가 필요합니다.
- 오퍼레이터에 `--volume-storage-class gshare-data`를 줍니다.

노드 준비 절차는
[클러스터 구축 → 스토리지 노드](../cluster-setup.md#storage-node-optional-volumes-with-a-real-quota)에
있습니다. 클러스터의 모든 노드가 마운트할 수 있는 ReadWriteMany 볼륨을 프로비저닝하는 CSI
드라이버라면 어느 것이든 같은 방식으로 동작합니다.

## 풀 등록

풀은 노드 역할에서 추론하는 것이 아니라 등록하는 객체입니다. 콘솔(**자원 → 볼륨 관리 → 풀**) 또는
`POST /api/v1/storage/pools`로 등록합니다.

| 필드 | 의미 |
|---|---|
| `cluster_id` | 이 스토리지 서버가 속한 클러스터 |
| `storage_class` | 여기서 프로비저닝하는 StorageClass — 오퍼레이터에 준 것과 같은 이름 |
| `share_scope` | `all` — 플릿의 모든 클러스터가 볼륨을 둘 수 있음(NFS 서버 하나를 전체에 내보내는 보통의 형태); `selected` — 허용 클러스터 목록을 함께 지정 |
| `manual_capacity_gb` | 드라이버가 용량을 발행하지 않을 때 쓰는 풀 크기 |

스토리지 서버가 여러 대면 풀도 여러 개입니다. 볼륨은 정확히 하나에 존재하고 — PVC가 지정한
StorageClass가 위치를 정합니다 — 따라서 용량 게이트와 대시보드는 합계가 아니라 사용 가능한 풀 중
**가장 큰** 것을 상한으로 삼습니다.

## 용량 값의 출처

1. **`csi`** — 드라이버의 `GetCapacity`. external-provisioner가 `CSIStorageCapacity` 객체로
   발행하고 오퍼레이터가 볼륨 동기화 틱마다 읽습니다. 유일한 자동 소스입니다. 프로비저너에
   `--enable-capacity`와 `--capacity-for-immediate-binding=true`가 필요하고, 드라이버가 노드
   토폴로지를 보고해야 합니다. 토폴로지가 없으면 객체가 생성·삭제를 반복하고 쓸 만한 값이 발행되지
   않습니다.
2. **`manual`** — 풀에 적어 둔 값. `STORAGE_POOL_CAPACITY_GB`(차트의 `storage.poolCapacityGb`)는
   여전히 플릿 기본값으로 동작합니다.
3. **`node_disk`** — 스토리지 노드의 시스템 디스크. 대용으로 표시됩니다.

대시보드의 스토리지 타일은 어느 출처를 썼는지 표시합니다.

## 연결된 클러스터

연결된 클러스터에도 같은 스토리지 서버를 가리키는 같은 드라이버가 필요합니다. 제어 플레인에서
드라이버 값을 내보내 `attach-cluster.sh`에 넘기세요.

```bash
helm -n gshare-storage get values gshare-storage > csi-values.yaml && chmod 600 csi-values.yaml
# controller.nodeSelector → 새 클러스터의 노드로 수정
./hack/attach-cluster.sh ... --storage-values csi-values.yaml
```

이 값 파일에는 스토리지 서버의 SSH 키가 들어 있습니다. 저장소 밖에 두고, 연결이 끝나면 삭제하세요.
[멀티 클러스터](../multi-cluster.md#volumes-and-storage)를 참고하세요.

## 회수

삭제된 볼륨의 PVC는 `api.volumeReclaimGraceHours`(기본 24시간) 동안 보관된 뒤 오퍼레이터가
삭제하고 드라이버가 데이터셋을 지웁니다. `0`이면 다음 동기화 때 회수합니다.

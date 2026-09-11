---
sidebar_position: 1
title: Storage
---

# Storage

User volumes are PersistentVolumeClaims created by the operator of whichever cluster a session
lands on, from the StorageClass given to that operator as `operator.volumeStorageClass`. gShare
itself never touches the storage; it registers **pools**, admits volumes against their capacity,
and pins each volume to the cluster where it was first mounted.

## The reference setup

The reference installation is one **ZFS + NFS storage node** served to every cluster through
[democratic-csi](https://github.com/democratic-csi/democratic-csi):

- `cluster-bootstrap.sh` installs the driver on the control-plane cluster with the values in
  `deploy/storage/democratic-csi-values.yaml`, producing the `gshare-data` StorageClass;
- every node needs an NFS client (`nfs-common` / `nfs-utils`) and network reach to the storage
  box on 2049/tcp;
- the operator is given `--volume-storage-class gshare-data`.

The step-by-step node preparation is in
[Cluster setup → Storage node](../cluster-setup.md#storage-node-optional-volumes-with-a-real-quota).
Any other CSI driver works the same way as long as it provisions ReadWriteMany volumes that every
node of the cluster can mount.

## Registering a pool

A pool is a registered object, not something inferred from node roles. Register it in the console
(**Resources → Volumes → Pools**) or with `POST /api/v1/storage/pools`:

| Field | Meaning |
|---|---|
| `cluster_id` | The cluster whose storage server this is. |
| `storage_class` | The StorageClass that provisions from it — the same name the operator was given. |
| `share_scope` | `all` — every cluster in the fleet may place volumes on it (one NFS box exported to all, the usual shape); `selected` — plus the list of allowed clusters. |
| `manual_capacity_gb` | The pool's size, used when the driver does not publish capacity. |

Several storage servers are several pools. A volume lives on exactly one — the StorageClass its
PVC names decides where — so the capacity gate and the dashboard take the **largest** usable pool
as the bound, never the sum.

## Where the capacity number comes from

1. **`csi`** — the driver's `GetCapacity`, published by the external-provisioner as
   `CSIStorageCapacity` objects and read by the operator on its volume-sync tick. The only
   automatic source. The provisioner needs `--enable-capacity` and
   `--capacity-for-immediate-binding=true`, and the driver must report node topology; without
   topology the objects churn and nothing usable is published.
2. **`manual`** — the figure stated on the pool. `STORAGE_POOL_CAPACITY_GB`
   (`storage.poolCapacityGb` in the chart) still works as a fleet-wide default.
3. **`node_disk`** — the storage node's system drive, labelled as a stand-in.

The dashboard's storage tile names the source it used.

## Attached clusters

An attached cluster needs the same driver pointed at the same storage box. Export the driver's
values from the control plane and pass them to `attach-cluster.sh`:

```bash
helm -n gshare-storage get values gshare-storage > csi-values.yaml && chmod 600 csi-values.yaml
# edit controller.nodeSelector → a node of the new cluster
./hack/attach-cluster.sh ... --storage-values csi-values.yaml
```

The values file carries the storage box's SSH key: keep it out of the repository and delete it
when the attach is done. See [Multi-cluster](../multi-cluster.md#volumes-and-storage).

## Reclamation

A deleted volume's PVC is kept for `api.volumeReclaimGraceHours` (default 24) before the operator
deletes it and the driver destroys the dataset. Set it to `0` to reclaim on the next sync.

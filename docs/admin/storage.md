---
sidebar_position: 11
title: Storage
---

# Storage pools and volumes

**Resources → Volumes** (super_admin) has two concerns: the **pools** that back user volumes, and
the **volumes** themselves.

![Volumes](/img/screens/admin-volumes.png)

## Storage pools

A **pool** is one storage server, registered as an object: the cluster it sits in, the
StorageClass that provisions from it, and its sharing scope — **all** clusters in the fleet, or
**selected** ones. The dashboard's storage tile and the capacity gate that admits new volumes both
read the registered pools.

The pool's **capacity** comes, in order, from:

1. **csi** — the driver's own `GetCapacity`, published as `CSIStorageCapacity` objects and read by
   the operator. The only automatic source.
2. **manual** — the figure stated on the pool. Set it when the driver does not publish capacity.
3. **node disk** — the storage node's system drive, labelled as a stand-in.

Several servers are several pools. A volume lives on exactly one, so the bound the dashboard shows
is the **largest** usable pool, never the sum. Details for operators are in
[Operations → Storage](../operations/storage.md).

## Volumes

The volume list shows every volume in the fleet with owner, quota, what is stored, the cluster it
is pinned to, and whether a session has it mounted. An administrator can raise a quota, lock a
volume, or delete it (typing its name); deleted volumes are reclaimed after the grace period
configured in the chart (`api.volumeReclaimGraceHours`).

Volumes are **free** for users. The lever is the volume quota in the
[resource policy](./resources.md#resource-policies).

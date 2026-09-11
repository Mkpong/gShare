---
sidebar_position: 24
title: Storage
---

# Storage

Two things live here: the **pools** that back user volumes, and the **volumes** themselves.

## Storage pools

A pool is a registered object, not something inferred from node roles: the cluster its server
sits in, the StorageClass that provisions from it, and its sharing scope (**all** clusters, or
**selected** ones). Pools are registered through the API (`/api/v1/storage/pools`); the console
shows them on the dashboard's storage tile.

The dashboard's storage tile and the capacity gate that admits new volumes both read the
registered pools. Capacity comes, in order, from:

1. **csi** — the driver's own `GetCapacity`, published as `CSIStorageCapacity` and read by the
   operator. The only automatic source.
2. **manual** — the figure stated on the pool. Set it when the driver publishes nothing.
3. **node disk** — the storage node's system drive, labelled as the stand-in it is.

Several servers are several pools. A volume lives on exactly one, so the bound is the
**largest** usable pool, never the sum. The operator-side detail — driver flags, NFS
prerequisites, attaching a second cluster — is in
[Operations → Storage](../operations/storage.md).

## Volumes

![All volumes](/img/screens/admin-volumes.png)

Every volume in the fleet, with owner, scope, type, access mode, usage against quota, and the
cluster it is pinned to.

| Action | Effect |
|---|---|
| **Change quota** | Raise a volume's quota — within the owner's storage limit; to go beyond it, raise their [policy](./resources-policies.md) first |
| **Lock** | Refuse new mounts while keeping running sessions |
| **Delete** | Normal deletion — refused while a session has it mounted |
| **Force delete** | Terminates the sessions holding it, then deletes |

![Force delete](/img/screens/admin-volume-force-delete.png)

Force delete is the sharpest tool in the console: it ends other people's running sessions to
remove a volume. The dialog names the owner and says so, and the audit entry records which
sessions were cut. Reserve it for a storage server that is genuinely full and an owner who
cannot be reached.

## Running out of space

When the pool fills, the useful order is:

1. **Find the big ones** — sort by usage; a handful of forgotten scratch volumes is the usual
   cause.
2. **Ask the owners** — deleted-by-owner is always better than deleted-by-admin, and the console
   shows you exactly who.
3. **Lock rather than delete** while you wait: it stops the volume growing without destroying
   anything.
4. **Tighten the storage limit** in the [policy](./resources-policies.md) so the next round does
   not happen, rather than repeating the cleanup.

Deleted volumes are reclaimed after `api.volumeReclaimGraceHours` (24h by default) — within that
window the data can still be recovered by an operator.

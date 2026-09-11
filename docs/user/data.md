---
sidebar_position: 5
title: Data and volumes
---

# Data and volumes

A **volume** is persistent storage that outlives any single session. Create one, mount it into
sessions at a path such as `/data`, and the files are there the next time — on whichever node the
session lands.

![Volumes](/img/screens/data.png)

:::tip Volumes are free
Credits are charged for GPU session time only. What limits storage is the **quota** your
administrator's policy grants you, shown on each volume, not your balance.
:::

## Creating a volume

**New volume** asks for a name, the owning scope (personal or one of your groups), and the
capacity. The form checks the capacity against your policy limit before you submit. The storage
itself is provisioned lazily: the first session that mounts the volume creates it.

## Mounting

Volumes are mounted from the [session wizard](./sessions.md#creating-a-session): pick the volume,
the mode (read-only or read-write), and the mount path. A session's detail page lists what it has
mounted.

A volume that is mounted by a running session cannot be deleted; terminate the session first.
The quota of a volume can be raised while it is in use but never shrunk below what is stored.

## Sharing

Share a volume you own with another user, **read-only** or **read-write**. The recipient can
only mount it in the mode you granted, and can never delete or re-share it. Revoking access takes
effect immediately.

## Locking and deleting

**Lock** a volume to refuse any new mount — useful while you reorganise data or before handing a
dataset over. **Delete** asks you to type the volume's name, because the data is not recoverable
once the grace period your site configures has passed.

## Where the data lives

Volumes are backed by the storage pool your site registered (see
[Storage](../operations/storage.md)). A volume is created on one cluster's storage and stays
there; if your site runs several clusters, sessions that mount it are placed on that cluster.

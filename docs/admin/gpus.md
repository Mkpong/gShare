---
sidebar_position: 10
title: GPU devices
---

# GPU devices

![GPU devices](/img/screens/admin-gpus.png)

Every card the fleet reports: node, cluster, model string, VRAM, mode (fractional or exclusive),
current occupancy, the sessions bound to it, and health. The **model string** shown here is what
an [offering](./resources.md#offerings) must match exactly.

## Per-node device view

![Devices of one node](/img/screens/admin-node-devices.png)

Opening a node from the [Nodes](./clusters.md#nodes) page lists its cards with the same detail
and the per-card actions.

## Marking a card faulty

**Mark faulty** takes one card out of placement and ends every session bound to it
(`gpu_fault`, settled, owners notified) — a process whose CUDA context died cannot be resumed,
so an honest end beats a session that bills for a dead card. **Restore** puts a repaired card
back.

Fatal Xid events reported by DCGM cordon the whole node automatically; the card action is for the
case where one card of several is bad.

## Aliases

A card can carry an **alias** (for example `lab-4090-01`) that the dashboard and session detail
show instead of the driver's UUID.

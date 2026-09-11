---
sidebar_position: 2
title: Dashboard
---

# Administrator dashboard

The administrator dashboard summarises what is running within your scope.

## As an organization or group administrator

![Dashboard, organization scope](/img/screens/admin-dashboard.png)

The figures are summed over the **people you manage** — every member of your groups (for an
org_admin, every group of the organization) — never over other tenants: running and active
sessions, the VRAM they hold, and their host CPU. The panels below list the sessions themselves
and the most recent audit entries in your scope.

## As the platform administrator

![Dashboard, platform scope](/img/screens/admin-dashboard-platform.png)

A super_admin sees the fleet:

- **Active sessions, queue, GPU utilisation, VRAM occupancy, idle GPUs**, and credits consumed
  in the last 24 hours.
- **GPU devices** — one card per tile with its cluster tag, mode (fractional or exclusive), VRAM
  occupancy, and free cores.
- **Node status** — busy, ready, cordoned, offline, and open health alerts.
- **Host resources** — CPU, memory, and disk across the fleet.
- **Storage server** — the registered [storage pool](./storage.md), its cluster, whether it is
  shared across clusters, and provisioned volume quota against its capacity.
- **Recent activity** — the latest audit entries.

The **cluster selector** in the top bar narrows every figure to one cluster; the storage panel
notes when a pool is shared fleet-wide and therefore not any one cluster's own.

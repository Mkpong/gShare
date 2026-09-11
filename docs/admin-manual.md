---
sidebar_position: 6
title: Administrator guide
---

# Administrator guide

The **administrator console** is where organizations, groups, and users are managed; credits
allocated and requests decided; sessions monitored; and — for the platform administrator — the
GPU catalogue, policy, clusters, nodes, storage, images and system settings configured.

Start with [Roles and scope](./admin/roles.md): what each administrative role sees is the key to
every page that follows.

## Tenant administration

The day-to-day of an organization or group administrator.

- [Dashboard](./admin/dashboard.md) — what is running in your scope.
- [Organizations](./admin/organizations.md) — the top of the tree, its administrators and budget.
- [Groups](./admin/groups.md) — teams, members, group administrators.
- [Users](./admin/users.md) — the account list and what membership decides.
  - [Adding users](./admin/users-add.md) — one at a time, bulk CSV, approving sign-ups.
  - [Managing an account](./admin/users-manage.md) — roles, password resets, deactivation, deletion.
- [Credits](./admin/credits.md) — the hierarchy and what is billed.
  - [Allocating](./admin/credits-allocate.md) — pools, hand-downs, reclaims, monthly refills.
  - [Requests](./admin/credits-requests.md) — the request chain, approving and rejecting.
  - [Settlement report](./admin/credits-settlement.md) — what was actually consumed.
- [Session monitoring](./admin/monitoring.md) — the live view, and what ends a session by itself.
  - [Intervening](./admin/monitoring-control.md) — force-terminate, bulk clean-up, the queue.
- [Audit log](./admin/audit.md) — filters, export, and the investigations that work.

## Platform administration

Super administrator only.

- [Resources and policy](./admin/resources.md) — catalogue versus quota.
  - [Offerings](./admin/resources-offerings.md) — GPU models, model strings, rates.
  - [Presets](./admin/resources-presets.md) — compute shapes and GPU tiers.
  - [Resource policies](./admin/resources-policies.md) — quotas, timeouts, quota requests.
- [Clusters](./admin/clusters.md) — registering, session domains, deregistering.
  - [Nodes](./admin/nodes.md) — liveness, cordon, drain, delete.
  - [Node pools](./admin/node-pools.md) — dedicated hardware and the spill question.
- [GPU devices](./admin/gpus.md) — aliases, faulty cards, allocation versus utilisation.
- [Storage](./admin/storage.md) — pools, every volume, running out of space.
- [Images](./admin/images.md) — importing, building, keeping the catalogue small.
- [Metrics](./admin/platform-monitoring.md) — DCGM and host metrics, and what they tell you.
- [System settings](./admin/system.md) — branding, sign-up policy, GPU placement.

Deploying and running the platform itself — installation, storage, monitoring, upgrades,
backups — is covered under **Operations**, starting with [Getting started](./getting-started.md).

---
sidebar_position: 3
title: Session monitoring
---

# Session monitoring

**Operations → Session monitor** is the live view of every session and every queue entry within
your scope, updated over a server-sent event stream (the *LIVE* indicator).

![Session monitor](/img/screens/admin-monitor.png)

Each row shows the session, its state, owner, organization, group, resources (class, mode, VRAM,
core share), and last transition. Sort any column; search by session name, id, or owner; filter
by state, organization, and group. An organization administrator sees only their organization's
sessions and a group administrator only their group's — scope follows the **owner** of the
session, so a session created without a group still belongs to its owner's tenancy.

## Force-terminate

**Force terminate** on a row ends a session without the owner's consent: the bill is settled
like an owner-initiated stop, the GPU is released, and the owner is notified. The reason you
type lands in the audit log.

Tick several rows and the fixed toolbar buttons become active — **Force terminate (N)** and
**Bulk clean-up (N)**. A bulk termination asks for the count to be typed, since the sessions
belong to other people.

## The queue tab

The **Queue** tab lists sessions waiting for capacity, with their position, priority, and the
reason they wait. An administrator can cancel an entry or raise its priority.

## Session liveness

The operator re-reports every running session once a minute, and the control plane acts on what
it hears, never on what it assumes:

- **Crash loop** — a container that has restarted three times and sits in `CrashLoopBackOff`
  ends the session (`crash_loop`), settled and notified, instead of billing an endless restart
  cycle.
- **Pod lost** — a session whose heartbeat has been silent for five minutes while the operator is
  otherwise alive is settled (`pod_lost`). If the operator itself is silent, nothing is touched:
  an operator outage must never turn into mass termination.
- **Node offline** — a node whose kubelet stops answering goes offline at once and its running
  sessions end (`node_offline`); paused sessions are left to resume elsewhere.
- A pod deleted by hand (or evicted) while the session is still wanted is simply rebuilt.

## Monitoring page

![Monitoring](/img/screens/admin-monitoring.png)

**Operations → Monitoring** (super_admin) charts GPU utilisation, VRAM, and host metrics per node
and per card from Prometheus, when the [monitoring stack](../operations/observability.md) is
deployed.

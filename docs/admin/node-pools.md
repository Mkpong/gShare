---
sidebar_position: 22
title: Node pools
---

# Node pools

A **pool** is a named set of nodes inside a cluster. It is how a department that bought its own
machines gets first claim on them without running a separate platform.

![Node pools](/img/screens/admin-node-pools.png)

| Kind | Who may be placed there |
|---|---|
| **Dedicated** | Only organizations and groups explicitly granted access |
| **Shared** | Everyone |
| *(unassigned)* | Nodes in no pool behave as shared |

Placement is tried in order: **group grant → organization grant → shared**. CPU-only sessions
ignore pools entirely.

## Creating a pool and filling it

![New pool](/img/screens/admin-node-pool-new.png)

1. **New pool** — name, cluster, kind (dedicated or shared), description.
2. **Add grant** — the organization or group that may use it.
   ![Granting access](/img/screens/admin-node-pool-grant.png)
3. **Nodes tab** — set each node's **target pool**. The change is queued: the card stops taking
   new sessions and moves to the new pool once it is empty, so nothing running is disturbed.

## Revoking and deleting

**Revoke** a grant and that tenant's *new* sessions stop landing on the pool; running ones stay.

**Delete** a pool and its nodes return to shared, and all its grants go. It is refused while
sessions are running on the pool's nodes — cordon them first.

## The spill question

A tenant whose dedicated pool is full falls back to shared nodes **only if their
[policy](./resources-policies.md) allows the shared pool**. That switch is the whole design
decision:

- **Spill allowed** — the department always gets its own cards first but can borrow idle shared
  capacity. Best utilisation.
- **Spill denied** — the department is strictly capped at its own hardware. Predictable for
  everyone else, and the department's queue is entirely their own to manage.

Whichever you choose, say so out loud: a user whose session queues while cards sit idle
elsewhere will otherwise report it as a bug.

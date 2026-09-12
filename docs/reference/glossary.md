---
sidebar_position: 1
title: Glossary
---

# Glossary

**Allocation** — a movement of credits down the hierarchy: platform → organization → group →
user.

**Cluster** — one Kubernetes cluster running a gShare operator. The control plane may manage
several.

**Credit (C)** — the unit of billing. GPU sessions consume credits at the offering's hourly rate
times occupancy; nothing else does.

**Exclusive** — a session mode that takes a whole card (`nvidia.com/gpu: 1`), bypassing HAMi.

**Fractional** — a session mode that takes a slice of a card (VRAM and a share of cores), enforced
by HAMi.

**Group** — a team inside an organization; called `project` in the API. Has members, admins, a
credit pool, and optionally a policy.

**Hold** — credits reserved when a GPU session starts, consumed as it runs, refunded at the end.

**Idle reaper** — the operator loop that pauses a GPU session whose card has been idle past the
policy's idle timeout, returning the card.

**Node pool** — a named set of nodes that a policy can grant to a tenant exclusively.

**Occupancy** — the share of a card a session holds: `max(VRAM fraction, core fraction)`.

**Offering** — one GPU model as a product: model string, whole-card size, hourly rate, minimum
CUDA.

**Operator** — the Go controller in each cluster that turns `GShareSession` resources into pods
and reports back. Never touches credits.

**Organization** — the top of the tenancy tree.

**Pause / resume** — tear the session's pod down (GPU returned, billing stopped) and bring it back
later, keeping volumes and the hold.

**Policy (resource policy)** — quotas: concurrency, VRAM, cores, host resources, volume quota,
runtime cap, idle timeout. Resolves user → group → organization → global.

**Preset** — a compute shape plus a GPU fraction tier (XL ½ … S 1/16) or exclusive.

**Queue** — where a session waits when no card fits; admitted in priority order as capacity
returns.

**Session** — a user's working environment: one pod with a GPU or CPU allocation and an image.

**Storage pool** — a registered storage server: cluster, StorageClass, sharing scope, capacity.

**Volume** — persistent storage a user owns, mounted into sessions; free, bounded by quota.

**Wallet** — a user's personal credit balance. Sessions are billed only from the owner's wallet.

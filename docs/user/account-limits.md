---
sidebar_position: 19
title: My limits
---

# My limits

Two different things bound what you can run: **credits** (money, in your
[wallet](./wallet.md)) and **quota** (resources, set by a policy). This page is about the second.

![Applied resource policy](/img/screens/account-limits.png)

## The policy that applies to you

The card lists the effective ceilings, already resolved. Policies can be set per user, per
group, per organization, and globally, and the **most specific one wins** — you see the result,
not the four candidates.

| Limit | What it caps |
|---|---|
| **Concurrent sessions** | Sessions running, paused, or queued at once |
| **Queued sessions** | How many may wait at the same time |
| **VRAM** / **GPU cores** | Totals across all your GPU sessions |
| **CPU** / **Memory** / **Disk** | Host resources across all your sessions |
| **Storage** | Total quota of all your [volumes](./data.md) |
| **Max runtime** | After this, a session is terminated automatically |
| **Idle timeout** | After this much idleness, a GPU session is paused and its card returned |
| **CPU session limits** | The same caps applied separately to free CPU sessions |

A blank entry means **unlimited**.

The same figures, as headroom rather than ceilings, appear on the
[dashboard](./dashboard.md#resource-allocation) and at the top of the
[session wizard](./sessions-create.md#before-you-start-your-limits) — that is where you notice
them, because a tier you cannot afford is marked there.

## Requesting more {#requesting-more}

**Request resource increase** (on this page, the dashboard, and the wallet) opens a form with one
field per ceiling. Fill in **only** what you need raised, each showing its current value, and
give a reason.

![Request history](/img/screens/account-quota-history.png)

The history below tracks what you asked for:

| State | Meaning |
|---|---|
| **Pending** | With an administrator |
| **Approved** | The new ceiling is already in effect — this page shows the raised figure |
| **Rejected** | Declined, with the reason |

## Which error means which limit

| Message | Cause | Fix |
|---|---|---|
| *Quota exceeded* | A policy ceiling — VRAM, CPU, storage | Request an increase here |
| *Concurrency limit reached* | Too many sessions at once | End or pause one, or request more |
| *Insufficient credits* | Money, not quota | [Request credits](./wallet-request.md) |
| *No GPU capacity* | The cluster is full; nothing to do with your limits | Wait in the [queue](./sessions-queue.md) or take a smaller tier |

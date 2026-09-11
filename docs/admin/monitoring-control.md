---
sidebar_position: 14
title: Intervening
---

# Intervening in a session

Everything on this page acts on **other people's work**. Each action is audited with your name,
and the owner is notified.

## Force-terminating one session

![Force terminate](/img/screens/admin-monitor.png)

**Force terminate** on a row ends a session without the owner's consent:

1. The container is stopped and the GPU returned to the pool immediately.
2. The bill is settled exactly as an owner-initiated stop would be — consumed credits charged,
   the rest of the hold refunded.
3. The owner is notified, and the free-text **reason** you type lands in the
   [audit log](./audit.md) next to the session id.

The session's `status_reason` is the typed `admin_stopped`, which the console renders as a
message to the owner. Write a reason someone can act on ("blocking the 4090 for a class at
14:00"), not "cleanup".

## Bulk clean-up

Tick several rows and the toolbar buttons activate — **Force terminate (N)** and
**Bulk clean-up (N)**. The confirmation names every session it is about to end, and from five
sessions upward it asks you to type the count.

The sessions belong to other people; the count is there to make a slip impossible, not to be
tedious.

## The queue

![Queue tab](/img/screens/admin-monitor-queue.png)

The **Queue** tab lists sessions waiting for capacity with their position, priority, wait
reason, and requested resources.

| Action | Effect |
|---|---|
| **Priority** | Sets the entry's priority band (an integer; higher is dequeued first) — for a demo, a deadline, a class |
| *Removing an entry* | There is no cancel button here: **force-terminate the pending session** from the Sessions tab. The hold is released in full; a session that never ran is never billed |

Priority is the honest lever when the fleet is full. Force-terminating someone else's running
session so a queued one can start is the other one — use it knowingly, and say why.

## Before you terminate: is it actually stuck?

| Symptom | Usually |
|---|---|
| Session **pending** for a long time | The queue, not a fault — check the wait reason |
| Session **running**, GPU at 0% | An idle notebook. The idle policy will pause it; consider lowering the timeout instead |
| Session restarting repeatedly | The crash-loop rule will end it within minutes |
| Node full of sessions you need to move | [Drain the node](./nodes.md#draining) — it reschedules instead of killing |

Draining is nearly always better than terminating: it moves the work rather than destroying it.

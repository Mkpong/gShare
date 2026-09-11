---
sidebar_position: 13
title: Session monitoring
---

# Session monitoring

**Operations → Session monitor** is the live view of everything running within your scope,
updated over a server-sent event stream — the *LIVE* badge tells you the stream is connected
(it falls back to polling silently if not).

| Page | What it covers |
|---|---|
| [Intervening](./monitoring-control.md) | Force-terminating, bulk clean-up, the queue |

![Session monitor](/img/screens/admin-monitor.png)

## The table

| Column | Meaning |
|---|---|
| **Session** | Name and id. Clicking the row opens its timeline |
| **State** | running, pending (waiting), paused, terminated |
| **User / organization / group** | Whose it is — the scope columns an administrator sorts by |
| **Resources** | Class, mode, VRAM, core share |
| **Node / cluster** | Where it actually runs |
| **Last change** | When it last transitioned |

Search matches session name, id, and owner. The filters narrow by state, organization, and
group; the cluster selector in the top bar narrows by cluster.

## Scope

Scope follows the **owner** of the session, not a label on it:

- a **group_admin** sees the sessions of the members of their groups;
- an **org_admin** sees every session in their organization;
- a **super_admin** sees the fleet.

![Group administrator's view](/img/screens/admin-monitor-group.png)

A session created without an explicit group still belongs to its owner's tenancy, so it appears
for the right administrators — and only for them.

## The session timeline

![One session](/img/screens/admin-monitor-detail.png)

Opening a row shows that session's full event timeline: queued (and how long it waited),
started, paused, resumed, terminated — each with the reason recorded at the time. It is the
first place to look when a user asks "why did my session stop".

## Session liveness — what ends a session by itself

The operator re-reports every running session once a minute. The control plane acts on what it
hears, never on what it assumes:

| Rule | Trigger | Result |
|---|---|---|
| **Crash loop** | A container restarted 3 times and sits in `CrashLoopBackOff` | Session ends (`crash_loop`), settled, owner notified |
| **Pod lost** | No heartbeat for 5 minutes *while the operator is otherwise alive* | Session settled (`pod_lost`) |
| **Operator silence** | Every node of a cluster goes stale at once | **Nothing is touched** — an operator outage must never become mass termination |
| **Node offline** | A node's kubelet stops answering | Its running sessions end (`node_offline`); paused ones resume elsewhere |
| **Idle** | A GPU idle past the policy's idle timeout | Session is **paused**, card returned |
| **Max runtime** | Past the policy's cap | Session terminated |
| **Manual pod deletion** | Someone deletes the pod but the session is still wanted | Pod is simply rebuilt; the bill and reservation are untouched |

Every one of these is visible in the session's timeline and in the owner's notifications, so
nothing ends silently.

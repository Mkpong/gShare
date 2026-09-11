---
sidebar_position: 19
title: Resource policies
---

# Resource policies

A **policy** decides how much one tenant may hold at once. Credits decide what they can afford;
policy decides what they may take even when they can afford it.

![Policies](/img/screens/admin-policies.png)

## Resolution: most specific wins

```
user  →  group  →  organization  →  global
```

Resolution is **field by field**: for each limit, the most specific policy that sets it wins,
and a field a policy leaves blank falls through to the next scope. A user policy that only sets
VRAM therefore raises VRAM and leaves every other ceiling exactly where the group, organization
or global policy put it. The account page shows which scope each figure came from.

Keep a complete **global** policy as the floor; everything above it only needs the fields it
actually changes.

## What a policy sets

![New policy](/img/screens/admin-policy-new.png)

| Field | Caps |
|---|---|
| **Max concurrent** | Sessions running, paused, or queued at once |
| **Max queued** | How many may wait |
| **VRAM / GPU cores** | Totals across all the tenant's GPU sessions |
| **CPU / memory / disk** | Host resources across all their sessions |
| **Storage** | Total quota of all their volumes |
| **Max runtime** | Sessions are terminated past this |
| **Idle timeout** | GPU sessions are **paused** after this much idleness, returning the card |
| **CPU session limits** | The same caps applied separately to free CPU sessions |
| **Shared pool access** | Whether the tenant may spill onto shared nodes when their dedicated [pool](./node-pools.md) is full |
| **Privileged sessions** | Whether they may run containers as root |

Blank means unlimited.

### The two that matter most on a busy fleet

- **Idle timeout.** Without it, a forgotten notebook holds a card overnight. An hour is a
  reasonable default; the user loses nothing — the session pauses and resumes.
- **Max concurrent.** It is what stops one person queueing ten sessions and occupying the fleet
  by attrition.

## Quota requests {#quota-requests}

![Incoming requests](/img/screens/admin-quota-requests.png)

Users who hit a ceiling raise a **resource increase request** from their account page. They
arrive in the **Requests** tab here, with the fields they asked to raise, their current values,
and a reason.

**Approving writes (or updates) a user-scope policy** for that person containing the raised
fields — and only those. By the field-by-field resolution above, everything else still comes
from their group, organization and global policies. Two habits keep this tidy:

- raise only the fields they asked for, so the user policy stays small and readable;
- prefer changing the **group** policy when the whole team has the same problem — it is one
  change instead of ten, and it does not accumulate per-user exceptions nobody remembers.

Rejecting asks for a reason the requester sees. Both decisions are audited and notified.

:::tip Credits or quota?
If the user's error was *insufficient credits*, this queue is the wrong one — send them to
[credit requests](./credits-requests.md). A quota increase does not add a single credit.
:::

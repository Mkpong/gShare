---
sidebar_position: 8
title: Credits
---

# Credit allocation

Credits are allocated **down the hierarchy** — platform → organization → group → user — and no
level can hand out more than it received.

![Credit allocation](/img/screens/admin-allocations.png)

- A **super_admin** tops up an organization's pool.
- An **org_admin** allocates from the organization to its groups.
- A **group_admin** allocates from the group's pool to individual members — one at a time, or
  **to everyone** at once — and can reclaim unspent credits.

![Group administrator view](/img/screens/admin-allocations-group.png)

## Monthly refill

Each user (or all members of a group) can carry a **monthly refill**: at the start of the month
the wallet is topped up to that amount from the group's pool. It replaces the manual routine of
handing out the same allowance every month.

## Requests

The **Requests** tab lists members' credit requests with amount and reason. Approving one moves
the credits from your pool to the member's wallet and notifies them; rejecting asks for a reason
that is shown to the requester.

## What is billed

Wallets are charged for **GPU session time only**: rate × occupancy × runtime, with a hold at
start and a refund of the unused part at the end. CPU sessions and volumes cost nothing and are
bounded by [resource policies](./resources.md) instead. Every movement is a ledger row that the
[audit log](./audit.md) and the user's wallet history both show.

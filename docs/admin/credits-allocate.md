---
sidebar_position: 10
title: Allocating credits
---

# Allocating credits

**Credits → Allocation / totals** shows the pools you control and everyone one level below.

## As a group administrator

![Group pool](/img/screens/admin-credits-group.png)

The group's pool balance sits at the top; each member has a row with their balance, monthly
refill, and the controls:

| Control | What it does |
|---|---|
| **Amount + Allocate** | Moves credits from the pool to that person's wallet, immediately |
| **Reclaim** | Takes unspent credits back into the pool |
| **Monthly refill + Set** | Tops that wallet up to the figure at the start of each month |

![Bulk actions](/img/screens/admin-credits-group-pool.png)

The band above the table does the same thing for **everyone at once**: *Give all N members* and
*Set everyone's monthly refill*. For a class of thirty, that is one action instead of thirty.

A reclaim never touches credits a running session has **held** — it can only take what is free.

## As an organization administrator

![Organization pools](/img/screens/admin-credits-org.png)

The same screen one level up: the organization pool, and a row per group. Allocate to a group
and its administrator distributes onward.

The **distributed total** column is worth watching: it is the sum the groups have handed to
individuals, and a group whose members hold far more than they spend is where reclaimable
credits are hiding.

## As the platform administrator

![System totals](/img/screens/admin-credits-system.png)

The super_admin tier is the only one that **issues** credits:

| Control | Meaning |
|---|---|
| **Monthly total (auto refill)** | The platform's budget per month; organizations are refilled from it automatically |
| **Issue (top-up)** | Mint credits into the system pool right now, outside the monthly cycle |
| **Refill point** | The day and time of the month the cycle runs (shown with the next occurrence) |

The band under it reconciles the figures: system balance, monthly total, the sum allocated to
organizations, and what is left to allocate. Then one row per organization with the same
allocate / reclaim / monthly-refill controls.

:::tip Refill beats hand-outs
For anything recurring — a class, a lab, a standing budget — set a **monthly refill** rather
than allocating by hand. It keeps working when nobody is watching, and the ledger shows exactly
the same rows.
:::

## What lands in the user's wallet

Every movement here appears in the recipient's [wallet history](../user/wallet-ledger.md) as an
allocation, and in the [audit log](./audit.md) with actor, amount, and target. There is no
silent way to move credits.

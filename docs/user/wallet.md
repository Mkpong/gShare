---
sidebar_position: 9
title: Wallet and credits
---

# Wallet and credits

Every user has a **personal wallet**. GPU session time is billed from it — and only from it:
a session can never be charged to someone else's wallet or to a group.

![Wallet](/img/screens/wallet.png)

## How billing works

- A GPU session is billed as **hourly rate × occupancy × runtime**, where the rate belongs to
  the GPU model and occupancy is the share of the card you hold (VRAM or cores, whichever is
  larger). An eighth of a card costs an eighth of the rate.
- When a session starts, an amount is **held** for its expected runtime. The hold is consumed
  as the session runs and the unused part is **refunded** when the session ends.
- **CPU sessions and volumes are free.** A balance never falls while no GPU session is running.

The wallet page lists the balance, current holds, and the full history of allocations,
consumption, and refunds, each linked to the session it came from.

## Requesting credits

![Request credits](/img/screens/wallet-request.png)

If the balance runs short, **Request credits** asks your group for an allocation: enter the
amount and a short reason. A group or organization administrator approves or rejects it; when
approved, the credits land in your wallet and you get a notification.

Your administrators may also set a **monthly refill**, in which case the wallet is topped up to
that amount at the start of each month without a request.

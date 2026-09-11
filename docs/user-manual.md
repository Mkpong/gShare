---
sidebar_position: 5
title: User guide
---

# User guide

gShare lets many people share a Kubernetes GPU cluster — in **fractional** or **exclusive**
slices — and accounts for usage in credits. This guide walks through the **user console**: the
screens you use to run sessions, keep data, and manage credits.

- [Signing in](./user/signing-in.md) — first login, language, theme, the cluster selector.
- [Dashboard](./user/dashboard.md) — balance, burn rate, allocation, availability.
- [Sessions](./user/sessions.md) — what a session is, its states, the list screen.
  - [Creating a session](./user/sessions-create.md) — the five-step wizard, field by field.
  - [Connecting](./user/sessions-connect.md) — VS Code, JupyterLab, the web terminal.
  - [Managing a session](./user/sessions-manage.md) — pause, resume, restart, live usage.
  - [Waiting in the queue](./user/sessions-queue.md) — why a session waits and what to do.
  - [Ending a session](./user/sessions-end.md) — terminating, billing, what survives.
- [Wallet and credits](./user/wallet.md) — how billing works, requesting credits.
- [Data and volumes](./user/data.md) — persistent storage, mounting, sharing.
- [Account](./user/account.md) — membership, password, notifications.

Administrative features — organizations, groups, users, credits, clusters, monitoring — are in
the [Administrator guide](./admin-manual.md).

:::tip Only GPU time costs credits
CPU sessions and volumes are free. Your balance never falls while no GPU session is running.
:::

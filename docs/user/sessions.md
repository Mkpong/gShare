---
sidebar_position: 3
title: Sessions
---

# Sessions

A **session** is your working environment: a container with a GPU (fractional or exclusive) or
CPU-only allocation, an image, and optionally your volumes mounted into it. You connect to it
with VS Code, JupyterLab, or a terminal in the browser.

## Session list

![Session list](/img/screens/sessions.png)

Only your own sessions are listed, with their state, resources, mode, GPU occupancy, uptime, and
what they have cost so far. The tabs split them into **active**, **running**, and
**terminated**; every column sorts, and the search box narrows by name or id. The filter is part
of the address bar, so a view survives a reload and can be shared as a link.

Select several rows to terminate them in one go.

## Creating a session

![New session](/img/screens/session-new.png)

**New session** opens the wizard:

1. **Compute preset** — how much CPU, memory, and scratch disk the container gets.
2. **GPU** — the model and the tier: a *fractional* slice (½, ¼, ⅛ … of a card) or an
   *exclusive* whole card. Choose **CPU** for a session with no GPU at all; it is free.
3. **Image** — only images compatible with the chosen GPU's CUDA version are offered.
4. **Volumes** — mount any of your volumes, read-only or read-write, at a path of your choice.

As you choose, the form shows your policy limits and the **estimated credit cost per hour**. If
the request exceeds a limit, the wizard says which one before you submit.

When the cluster has no free slice for the GPU you picked, the session is not refused — it enters
the [queue](#queue) and starts automatically when capacity is returned.

## Session detail

![Session detail](/img/screens/session-detail.png)

The detail page shows the allocated resources, the mounted volumes, which node and card the
session runs on, and a **live usage** panel (CPU, memory, GPU cores, VRAM) updated every second.

### Pause, resume, restart, terminate

- **Pause** tears the container down, **returns the GPU** so someone else can use it, and
  **stops billing**. The session, its volumes, and the credit hold are kept.
- **Resume** re-acquires a GPU and starts the container again. If nothing is free, the resume
  waits in the queue.
- **Restart** is a pause followed by a resume.
- **Terminate** ends the session, settles the bill (the unused part of the hold is refunded),
  and releases everything. Terminating asks you to confirm, naming the session and what it has
  spent.

:::note
Idle GPU sessions may be paused automatically by your site's policy so their capacity can be
reclaimed. Nothing is lost: resume when you are back.
:::

## Connecting

![Connect](/img/screens/session-connect.png)

**Connect** issues single-use links to **VS Code**, **JupyterLab**, and a **web terminal**
inside the running container. A link that has expired is simply reissued from the same panel.

## Queue

![Queue](/img/screens/queue.png)

When the GPU you asked for is full, the session waits here. The page shows your position, the
reason the session is waiting (for example *no card with 20 GiB free*), and how long it has been
waiting. As sessions end or pause, queued sessions are admitted in priority order — you do not
need to keep the page open.

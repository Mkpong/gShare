---
sidebar_position: 7
title: Resources and policy
---

# Resources, offerings, presets, and policy

**Resources → Resource settings** (super_admin) is the catalogue that the session wizard is built
from; **Resources → Resource policy** is the set of quotas that decide what each user may ask for.

## Offerings

![Offering catalogue](/img/screens/admin-resources.png)

An **offering** is one GPU model as a billable product: the model string, the whole card's VRAM
and cores, the **hourly rate** in credits, and the minimum CUDA version an image must support.
The *in cluster* tag marks offerings whose model string matches a card the fleet currently reports.

:::caution Model strings must match exactly
The scheduler matches an offering to a card by string equality with the model the driver reports
(for example `NVIDIA GeForce RTX 4090`). Copy it from the [GPU devices](./gpus.md) page when
creating an offering. If the fleet reports a longer SKU and exactly one offering is a
word-boundary prefix of it, the offering adopts the reported string automatically (audited as
`offering.align_model`).
:::

## Presets

A **preset** pairs a compute shape (CPU, memory, scratch disk) with a GPU fraction tier —
XL ½, L ¼, M ⅛, S 1/16, SS 1/32 — or an exclusive card. Presets are what the user picks first in
the wizard; the price follows from the offering's rate times the fraction.

## Resource policies

![Resource policies](/img/screens/admin-policies.png)

A **policy** limits what its subjects may hold at once: concurrent and queued sessions, VRAM,
GPU cores, host CPU, memory, disk, volume quota, maximum session runtime, and the idle timeout
after which a GPU session is paused. Policies resolve **most-specific first**:
**user → group → organization → global**, and a policy can also grant access to a dedicated
node pool.

![New policy](/img/screens/admin-policy-new.png)

Credits apply to GPU sessions only. CPU sessions and volumes are free; cap them with the
concurrency and resource ceilings in the policy instead. Users' **quota requests** (from the
dashboard's *Request increase*) queue on this page for approval.

## Session images

The catalogue seeds `boanlab/gshare-session:<tag>` images for the CUDA 12.4/12.5 line and the
Blackwell (CUDA 12.8/12.9) line. A fleet of Blackwell cards needs the 12.8 line; older images are
refused with `incompatible_image`. See [Images](./images.md).

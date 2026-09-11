---
sidebar_position: 17
title: Offerings
---

# GPU offerings

An **offering** is one GPU model as a billable product. The session wizard is built from this
catalogue, and the scheduler prices against it.

![Offerings](/img/screens/admin-resources.png)

| Column | Meaning |
|---|---|
| **Name** | What users see, e.g. *RTX 4090* |
| **Model** | The driver's exact model string, with an **in cluster** tag when the fleet reports it |
| **VRAM · cores** | The whole card |
| **Class** | `gpu` (billed) or `cpu` (free compute offering) |
| **Rate** | Credits per hour for a whole card; a fraction costs its share |
| **Min CUDA** | Images below this version are refused for this model |
| **Status** | Active offerings appear in the wizard; inactive ones are kept for history |

## Creating one

![New offering](/img/screens/admin-offering-new.png)

:::caution The model string must match exactly
Admission matches `gpu_model` to the string the driver reports, character for character —
`NVIDIA GeForce RTX 4090`, not `RTX 4090`. **Copy it from [GPU devices](./gpus.md)** rather than
typing it.

If the fleet reports a longer SKU (`… Max-Q Workstation Edition`) and exactly one offering is a
word-boundary prefix of it, that offering adopts the reported string automatically, audited as
`offering.align_model`. When a session is still refused with `unserviceable`, the error lists
the models the fleet actually reports — copy one of them in.
:::

Setting the **rate** is a policy decision, not a technical one. Two anchors that work:

- Make the *relative* rates honest — if an H100 is worth three 4090s to your users, price it
  that way, so the cheap card is the sensible default for small work.
- Size the monthly [credit budget](./credits-allocate.md) so a typical user's typical month
  costs roughly what you intend to grant them. The absolute numbers only matter against that.

## Editing and retiring

Editing a rate affects **new sessions only** — a running session keeps the rate snapshotted when
it started, so a price change never rewrites someone's bill mid-run.

Every rate change is kept in the offering's price history (`/api/v1/offerings/{id}/price-history`),
so a bill from last term can always be explained.

Deactivate rather than delete when a model leaves the fleet: sessions and ledger rows reference
the offering, and the history stays readable.

## CPU offerings

A `cpu`-class offering has no GPU and a rate of zero. It is what makes free data-preparation
sessions possible. Cap those with [policy](./resources-policies.md) limits, not with price.

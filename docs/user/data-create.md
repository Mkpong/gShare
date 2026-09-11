---
sidebar_position: 10
title: Creating a volume
---

# Creating a volume

**Data / Volumes → New volume** opens one dialog.

![New volume](/img/screens/data-new.png)

## The fields

### Name

Lowercase letters, digits, and hyphens read best, because the name is what you will type into a
mount path later. `imagenet-2024` beats `ImageNet (final!)`.

### Owner scope

- **Personal (my account)** — yours. Nobody else sees it until you
  [share](./data-share.md) it.
- **Group share** — offered to group administrators. Every member of the chosen group can mount
  it **as soon as it is created**; no sharing step is needed.
- **Everyone** — offered to platform administrators. Every signed-in user can mount it. Keep it
  read-only unless anyone really may change the files.

**Target** follows the scope: your account, the group you pick, or everyone.

### Type

Dataset, personal workspace, group share, or scratch — see
[the table in the overview](./data.md#types). The dialog shows a one-line description of the type
you selected.

### Access mode

| Mode | Meaning |
|---|---|
| **read/write (RWX)** | Sessions can write. Several sessions may mount it at once. |
| **read-only (ROX)** | Nobody can write, not even you, from any session. |

This is the volume's ceiling. A session can always mount a read/write volume read-only
(the wizard offers the choice), but never the other way round. A dataset you want to protect
from an accidental `rm -rf` is best created read-only.

### Quota (GiB)

How much the volume may hold. Two ceilings apply, and the dialog shows both:

- **Your policy's storage limit** — *70 / 500 GiB used · 430 GiB left* in the screenshot. It is
  the total across all your volumes.
- **What the storage server physically has free**.

The larger request of the two is refused before you submit, with the number that would fit.

## After creating

The volume appears in the list at once with 0 GiB used. The storage itself is provisioned
lazily: the **first session that mounts it** creates the underlying claim. That is normal — a
volume that has never been mounted holds nothing and costs nothing.

Nothing is charged at any point: [volumes are free](./data.md), bounded by quota rather than by
credits.

## Growing it later

A quota can always be raised later ([Resizing](./data-manage.md#changing-the-quota)) and never
lowered below what is stored, so starting modestly costs you nothing.

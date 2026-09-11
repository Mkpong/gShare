---
sidebar_position: 25
title: Images
---

# Images and templates

The image catalogue is what the session wizard offers. An image that is not here (or not
compatible with the chosen card) cannot be run.

![Images](/img/screens/admin-images.png)

| Column | Meaning |
|---|---|
| **Name** | What users see |
| **Kind** | Catalogue image, or a user's own |
| **Source** | The registry reference |
| **CUDA** | The runtime inside — matched against the offering's minimum |
| **Supported GPUs** | Models verified for it |
| **Public** | Visible to everyone, or private to its owner — toggled from the row |

Two tabs: the **catalogue** itself, and **builds** — every console-driven build with its state
and log, whether it succeeded or not.

## Importing

![Import](/img/screens/admin-image-import.png)

**Import** registers an image that already exists in a registry: the reference, a display name,
its CUDA version, and which GPU models it is for.

Two things decide whether it will actually run:

- **The nodes must be able to pull it.** A private registry needs per-node trust (see
  [Cluster setup → Local registry](../cluster-setup.md#local-registry-optional)); on a
  multi-cluster fleet *every* cluster needs to reach it.
- **The CUDA version must be honest.** It is what the wizard filters on. Declaring 12.8 on an
  image built for 12.4 does not make it work on a Blackwell card — it makes the failure happen
  later and less clearly.

## Builds

![Builds tab](/img/screens/admin-image-build.png)

The **Builds** tab follows image builds run through the platform:
`queued → building → pushing → scanning → succeeded`, with the log of each.

A build is started through the API (`POST /api/v1/image-builds`, from an inline Dockerfile or a
public git repository); the console has no form for it. It also needs the chart's
`operator.kanikoImage` to be set — without it the operator fails builds immediately. The result
is pushed to `api.buildRegistry` and registered automatically.

Images a member imported or built themselves are private to that member (up to 20 each) and
tagged **My image** in the wizard.

## Seeded images

With `api.seedSessionImages` (the default) the catalogue seeds `boanlab/gshare-session` for the
CUDA 12.4/12.5 line and the Blackwell 12.8/12.9 line at startup. Those tags exist on Docker Hub
only after the publish workflow has run for a release.

A fleet of Blackwell cards needs the 12.8 line; older images are refused with
`incompatible_image` before the session starts, which is the behaviour you want — the alternative
is a container that starts and then cannot see the GPU.

## Keeping the catalogue small

Every extra image is a decision for the user and 5–15 GiB on every node that pulls it. One
maintained image per framework generation beats a dozen variants; let people build their own for
the rest.

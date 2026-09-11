---
sidebar_position: 12
title: Images
---

# Images and templates

![Images](/img/screens/admin-images.png)

The image catalogue is what the session wizard offers. Each image carries a name, its registry
reference, the **CUDA version** it was built for, and whether it is public or restricted to
certain groups. The wizard only offers images whose CUDA version the chosen GPU supports.

## Import

**Import** registers an existing image by reference (for example
`boanlab/gshare-session:ml-cuda12.8-cudnn9`) with its CUDA version. Images from a private
registry need the nodes to trust that registry (see
[Cluster setup → Local registry](../cluster-setup.md#local-registry-optional)).

## Build

**Build** starts a console-driven image build from a Dockerfile and pushes the result to the
registry configured as `api.buildRegistry`. The build's log streams into the page; the resulting
image is registered automatically.

## Seeded images

With `api.seedSessionImages: true` (the default) the catalogue seeds the
`boanlab/gshare-session` line for CUDA 12.4/12.5 and the Blackwell 12.8/12.9 line at startup. Sites
that serve session images from a private registry set it to `false` and import by hand.

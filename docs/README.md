---
sidebar_position: 0
slug: /
title: Overview
---
# GShare documentation

GShare lets several organizations, groups, and users share a Kubernetes GPU cluster —
in **fractional** or **exclusive** mode — and accounts for what they use in **credits**.

## Where to start

| If you are… | Read in this order |
|---|---|
| New to the project | [Architecture and concepts](architecture.md) → [Getting started](getting-started.md) |
| A user who wants to run sessions | [User manual](user-manual.md) |
| An administrator managing organizations and resources | [Administrator manual](admin-manual.md) |
| An operator deploying to a GPU cluster | [Getting started](getting-started.md) → [Cluster setup](cluster-setup.md) → [Connecting a cluster](cluster-connect.md) |
| An operator adding a SECOND GPU cluster | [Multi-cluster](multi-cluster.md) |
| A developer contributing code | [Contributing guide](../CONTRIBUTING.md) → the component READMEs |
| A developer adding or changing a console screen | [Console UX standards](console-ux.md) → [the persona audit](../test/e2e/ux/README.md) |

## All documents

### Understanding the system

- [**Architecture and concepts**](architecture.md) — components, data flow, and the
  vocabulary the rest of the documentation assumes: offering, preset, session, occupancy,
  credit, policy, pause. **Read this first.**
- [Overview deck](gshare.html) — single-file HTML introduction, also available as
  [PDF](gshare.pdf) and [PowerPoint](gshare.pptx). Korean.

### Using the console

- [**User manual**](user-manual.md) — login, dashboard, sessions, wallet, volumes, and
  account settings, screen by screen.
- [**Administrator manual**](admin-manual.md) — organizations, groups, users, resource
  catalogue and policy, credit allocation, clusters and nodes, session monitoring, audit.

### Deploying and operating

- [**Getting started**](getting-started.md) — from a fresh clone to a running platform,
  both the local walkthrough and the real deployment.
- [Cluster setup](cluster-setup.md) — building the prerequisite GPU Kubernetes cluster
  from scratch with kubeadm and HAMi.
- [Connecting a cluster](cluster-connect.md) — registering a cluster with the control
- [Multi-cluster](multi-cluster.md) — attaching further GPU clusters to one control
  plane: prerequisites, `hack/attach-cluster.sh`, verification and token rotation
  plane and attaching its operator.

### Developing and design

- [Contributing guide](../CONTRIBUTING.md) — environment, tests, pull request workflow.
- Components: [`backend/`](../backend/README.md) (control plane) ·
  [`operator/`](../operator/README.md) (execution plane) ·
  [`frontend/`](../frontend/README.md) (console).
- [Console UX standards](console-ux.md) — what every screen owes the user, and the shared
  components that provide it. Checked by the [persona audit](../test/e2e/ux/README.md), which
  needs only the control plane.

> The root [`README.md`](../README.md) and the code are the authority on current
> behaviour. These documents sit on top of that to help you learn, use, and operate the
> platform.

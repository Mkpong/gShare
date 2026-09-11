---
sidebar_position: 9
title: Clusters and nodes
---

# Clusters and nodes

## Clusters

![Clusters](/img/screens/admin-clusters.png)

A **cluster** is one Kubernetes cluster running a gShare operator. The control plane's own
cluster registers itself at install; further clusters are attached with `hack/attach-cluster.sh`
(see [Multi-cluster](../multi-cluster.md)). The list shows each cluster's connection state, the
domain its sessions are served on, and its node and GPU counts. Deregistering a cluster retires
its nodes, devices, and storage pools; running sessions on it are settled first.

## Nodes

![Nodes](/img/screens/admin-nodes.png)

Every node the operators report, with its cluster, role (GPU, CPU, master, storage), node pool,
GPU count, running sessions, host resources, and heartbeat age.

Node status is driven by the operator's inventory heartbeat: a node that stops reporting for
five minutes is marked **offline** automatically and returns to **ready** when reports resume.
The operator reports the node's own Ready condition, so a machine whose kubelet stops answering
goes offline at once. Every super_admin is notified on each transition.

### Per-node actions

- **Cordon / uncordon** — stop or resume new placements. Running sessions stay.
- **Drain** — cordon, then move or end the sessions on the node. *Reschedule* cold-pauses each
  running session and resumes it at once on another node with room; a session with nowhere to
  go is parked in the queue and resumes when room appears. *Force terminate* settles every
  session. The cordon is mirrored onto the Kubernetes node so nothing lands back on it.
- **Delete** — offered only on an **offline** node (a node the operator still reports would
  reappear on its next tick). Refused while any live allocation remains; billing history is
  kept.

### Node pools

The **Node pools** tab groups nodes into pools that a [resource policy](./resources.md) can grant
to a tenant. A dedicated pool's cards are invisible to everyone else's placement.

The machine-level procedure — join, labels, drain, `kubeadm reset` — is in
[Cluster setup](../cluster-setup.md#growing-or-shrinking-a-running-cluster).

---
sidebar_position: 2
title: Observability
---

# Observability

gShare works without a monitoring stack — the control plane knows every session, allocation, and
credit movement on its own — but three things need metrics: the administrator monitoring page,
per-session usage history, and the idle reaper's *workload-aware* idle detection.

## The monitoring stack

```bash
make deploy-monitoring      # kubectl apply -f deploy/monitoring/monitoring-stack.yaml
```

installs into the `monitoring` namespace:

| Component | Runs on | Provides |
|---|---|---|
| dcgm-exporter | every GPU node | `DCGM_FI_DEV_*` per physical card, UUID-labelled |
| node-exporter | every node | host CPU, memory, disk, network |
| kube-state-metrics | one pod | pod and node object state (restarts, phases) |
| kubelet cAdvisor | scraped in place | per-pod CPU, memory, network, disk |
| HAMi vGPU monitor | scraped in place | `hami_host_gpu_*` (already running in `kube-system`) |
| Prometheus | one pod, 30-day PVC on the default StorageClass | the record |

Prometheus is not exposed outside the cluster: the console reads metrics through `gshare-api`,
which whitelists the queries and enforces the super_admin gate.

## Pointing the operator at it

The idle reaper pauses GPU sessions whose card has been idle for the policy's idle timeout. It
needs a utilisation source:

- `operator.hamiMonitorUrl` (default) — HAMi's own monitor, no extra infrastructure. On a cluster
  with more than one GPU node the monitor round-robins per-node pods, so use Prometheus instead.
- `operator.prometheusUrl: http://prometheus.monitoring.svc:9090` — `DCGM_FI_DEV_GPU_UTIL` from
  the stack above. Takes precedence when set.

With neither, idle reclamation is off and only the maximum-runtime cap applies.

## The per-node agent

`agent.enabled: true` deploys a DaemonSet that samples each session's cgroup counters once a
second and feeds the **live usage** panel on the session page. Prometheus remains the record;
the agent is the one-second live view and nothing depends on it.

## Health and alerts

- `/healthz` on the API is a plain liveness probe; it does not check database or Redis reachability.
- The operator posts node inventory every 15 seconds; a node silent for `api.nodeStaleSec` goes
  **offline** and every super_admin is notified. Fatal Xid events from DCGM cordon the node.
- The audit log records `access.denied` entries, de-duplicated per minute, so a misbehaving
  client is visible without log scraping.

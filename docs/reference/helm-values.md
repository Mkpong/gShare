---
sidebar_position: 2
title: Helm values
---

# Helm values

The chart is `charts/gshare`. Every key below is documented inline in
[`values.yaml`](https://github.com/boanlab/gshare/blob/main/charts/gshare/values.yaml); the
overlays in `deploy/values/` show complete configurations (`incluster.yaml` for all-in-one,
`dockerhub.yaml` for production with external data tier, `domain.example.yaml` with every optional
knob).

## Top level

| Key | Purpose |
|---|---|
| `global.imageRegistry`, `global.imagePullSecrets` | Registry prefix and pull secrets for every image. |
| `global.namespaces` | `system` (control plane), `sessions` (workloads) and `infra` (privileged node jobs). |
| `global.domains`, `global.sessionUrlScheme` | Console and session domains; `https` or `http`. |
| `controlPlane.enabled` | `false` on a cluster that only runs an operator (attached cluster). |
| `controlPlane.nodeSelector` | Pin api, worker, frontend, data tier, and backup jobs to nodes. |
| `images.{api,worker,operator,frontend,agent}` | `repository`, `tag`, `pullPolicy` per component. api and worker share the backend image. |
| `bootstrapAdmin.email`, `bootstrapAdmin.password` | The first super_admin; password change forced on first login. |
| `bootstrapLocalCluster` | Register the local cluster automatically (all-in-one). |
| `postgres.*`, `redis.*` | `inCluster` deploys them; otherwise host, port, and credential secret. `postgres.backup.*` is the nightly dump. |
| `storage.poolCapacityGb` | Fleet-wide default pool size when no pool states one. |
| `podDisruptionBudget.enabled` | minAvailable 1 for api, worker, frontend. |
| `secrets.generate` | Let the chart create passwords and keys, or bring your own. |
| `ingress.*`, `ingress.internalPlane` | Console ingress and the whitelisted internal plane attached operators call. |
| `serviceAccounts.*` | Service-account names for the controller (api/worker) and the operator. |
| `networkPolicy.*` | Deny-all plus ingress/egress allowlists for the session namespace. Off by default — see below. |

## `api`

| Key | Default | Purpose |
|---|---|---|
| `replicas` | 2 | uvicorn replicas. |
| `dbPoolSize`, `dbMaxOverflow` | 20 / 10 | SQLAlchemy pool. |
| `buildRegistry` | | Registry prefix for console-built images. |
| `auditRetentionDays` | 180 | 0 disables pruning. |
| `nodeStaleSec` | 300 | Silence before a node goes offline. |
| `seedSessionImages` | true | Seed the `boanlab/gshare-session` catalogue. |
| `gpuPacking` | binpack | `binpack` or `spread` for fractional placement. |
| `volumeReclaimGraceHours` | 24 | Keep a deleted volume's data this long. |
| `forwardedAllowIps` | `*` | Peers uvicorn trusts to set `X-Forwarded-*` (`--forwarded-allow-ips`); narrow to the ingress controller's addresses where possible. |
| `trustedProxyHops` | 1 | Proxies that append to `X-Forwarded-For` before the api (`GSHARE_TRUSTED_PROXY_HOPS`); `2` with a load balancer in front of the ingress. |

## `worker`

`replicas`, `resources`, `gracePeriodSec` (grace window after credit exhaustion before a session is paused or yielded), `yieldReservationTtlSec`.

## `operator`

| Key | Purpose |
|---|---|
| `clusterId` | The cluster this operator reports as (`clu_local` for the all-in-one install). |
| `controlPlaneUrl` | Where callbacks go when the control plane is elsewhere. |
| `internalJwtSecret`, `internalJwtTokenTtlSec` | The operator's token and its TTL (re-signed daily by a CronJob). |
| `hamiMonitorUrl`, `prometheusUrl` | Utilisation source for the idle reaper; see [Observability](../operations/observability.md). |
| `perCardMode` | Pin each session to the exact card reserved — required for a mixed-model fleet. |
| `volumeStorageClass`, `volumeSyncInterval` | The pool's StorageClass and how often PVCs and capacity are reconciled. |
| `sessionImagePullPolicy` | For session pods. |
| `losslessAgentImage`, `migAgentImage`, `kanikoImage` | Optional sidecar and build images. |
| `webhook.*`, `hamiYieldExtender` | The lend-guard admission webhook and HAMi yield extender. |

## `networkPolicy`

Off by default (`networkPolicy.enabled: false`). Enabling it renders a deny-all policy for the
session namespace plus allowlists: ingress from `ingressNamespace` on `sessionPorts`, egress to
DNS in `dnsNamespace`, and egress to `storage.cidrs` on `storage.ports`. `cpuData.cidrs` adds a
second egress rule for CPU data-prep sessions only.

The CIDRs are cluster-specific and start empty, which is why the whole block is off: enabling it
without a storage CIDR leaves sessions able to resolve DNS and reach nothing else. The same
manifests stand alone in `deploy/security/` for installs that do not use this chart.

The policies select session pods by the `gshare.io/workload=session` label (CPU sessions also by
`gshare.io/resource-class=cpu`), which the operator stamps on every session pod.

## `frontend`, `agent`

`frontend.replicas`, `frontend.port`, `frontend.resources`; `agent.enabled`, `agent.intervalMs`,
`agent.apiUrl`, `agent.nodeSelector`, `agent.resources` — see
[Observability → The per-node agent](../operations/observability.md#the-per-node-agent).

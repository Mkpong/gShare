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
| `global.namespaces` | `system` (control plane) and `sessions` (workloads). |
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
| `serviceAccounts.*` | Names and annotations. |

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

## `worker`

`replicas`, `resources`, `gracePeriodSec` (billing settle window), `yieldReservationTtlSec`.

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

## `frontend`, `agent`

`frontend.replicas`, `frontend.port`, `frontend.resources`; `agent.enabled`, `agent.intervalMs`,
`agent.apiUrl`, `agent.nodeSelector`, `agent.resources` — see
[Observability → The per-node agent](../operations/observability.md#the-per-node-agent).

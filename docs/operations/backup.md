---
sidebar_position: 4
title: Backup and restore
---

# Backup and restore

Everything gShare knows — users, credits, sessions, volumes, audit — is in **Postgres**. Redis
holds only transient state (queue tickers, idempotency keys, live samples) and needs no backup.
User data lives on the storage pool and is the storage server's own backup story.

## In-cluster Postgres

With `postgres.inCluster: true` (the all-in-one install) the chart also renders a nightly
`pg_dump` CronJob into its own PVC:

```yaml
postgres:
  backup:
    enabled: true
    schedule: "0 3 * * *"
    storage: 10Gi
    keep: 14          # dumps to retain
```

The dumps are in the `gshare-pg-backup` PVC in `gshare-system`. Copy them off the cluster
regularly — a PVC on the same node is a safety net, not an off-site backup.

### Restoring

```bash
kubectl scale deploy/gshare-api deploy/gshare-worker -n gshare-system --replicas=0
kubectl exec -n gshare-system deploy/gshare-pg -- \
  sh -c 'psql -U gshare -d gshare < /backup/gshare-YYYYMMDD.sql'
kubectl scale deploy/gshare-api deploy/gshare-worker -n gshare-system --replicas=2
```

Sessions that were running at the time of the dump are reconciled from the `GShareSession`
resources the operator still holds; anything that ended in between is settled by the liveness
rules when the API comes back.

## External Postgres

Production installs (`postgres.inCluster: false`) point at an external database — CloudNativePG,
a managed service — and use its backup and point-in-time recovery. The chart only needs the
connection secret (`postgres.credentialsSecret`).

## What else to keep

- The Helm values you installed with (`deploy/values/*.yaml`), minus secrets.
- The **internal JWT** signing secret (`operator.internalJwtSecret`) if you rotate it by hand;
  otherwise it is re-issued by the chart's CronJob.
- The democratic-csi values file for attached clusters, kept outside the repository.

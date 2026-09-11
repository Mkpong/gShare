---
sidebar_position: 3
title: Upgrading
---

# Upgrading

gShare is one Helm release. An upgrade is a `helm upgrade` with new image tags; the chart does
the rest.

## What happens on upgrade

1. **Schema migrations** run in an init container of the API deployment (`alembic upgrade head`)
   before the new API starts. Migrations are additive and backward-compatible with the previous
   release's pods, so a rolling update does not need downtime.
2. The **API** and **worker** roll (two replicas each by default, with a PodDisruptionBudget).
3. The **operator** rolls; it is leader-elected, and a `GShareSession` custom resource is the
   source of truth, so running sessions are untouched — the new operator adopts them.
4. The **frontend** rolls.

The `GShareSession` CRD in `charts/gshare/crds/` is applied by Helm on install only; when a
release changes the CRD, apply it by hand first:

```bash
kubectl apply -f charts/gshare/crds/
```

## Commands

Public images:

```bash
helm upgrade gshare charts/gshare -n gshare-system --reuse-values \
  --set images.api.tag=v0.2.0 --set images.worker.tag=v0.2.0 \
  --set images.operator.tag=v0.2.0 --set images.frontend.tag=v0.2.0
kubectl rollout status deploy/gshare-api -n gshare-system
```

or, from a checkout, `make deploy-incluster` / `make prod-deploy` with the same overlays used at
install (`deploy/values/*.yaml`).

## Attached clusters

Each attached cluster runs its own operator release. Upgrade it with the same
`hack/attach-cluster.sh` invocation used to attach it, or `helm upgrade` against that cluster's
kubeconfig with the new operator tag. Operators tolerate a newer control plane; upgrade the
control plane first.

## Rolling back

`helm rollback gshare <revision>` restores the previous images. Migrations are not rolled back
automatically; releases keep them backward-compatible so the previous API runs against the newer
schema. Take a [backup](./backup.md) before any upgrade regardless.

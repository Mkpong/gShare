---
sidebar_position: 4
---
# Running gShare across several clusters

One control plane, many GPU clusters. The control plane holds the users, the money and the
decisions; each cluster runs an operator that turns those decisions into pods and reports what
actually happened.

This is the operator's guide: what has to be true, what to run, and how to tell it worked.

---

## What each side is responsible for

| | Control plane cluster | Data-plane cluster |
|---|---|---|
| Runs | api, worker, console, Postgres, Redis | operator only |
| Holds | users, credits, policies, session records, every cluster's credential | GPUs, session pods, its own ingress |
| Talks to | each cluster's apiserver, using the kubeconfig you register | the control plane's `/internal` routes |

Two consequences worth stating before you start:

- **Each cluster serves its own session URLs.** A session's address is the hostname of the cluster
  it runs on, because that cluster's ingress is what routes to the pod. You give that hostname per
  cluster; there is no single global one.
- **The control plane must be reachable from the data plane, and vice versa.** The operator calls
  back to report status; the control plane calls the apiserver to apply session resources.

---

Every operator token is minted as `operator:<cluster_id>` and the control plane holds each
callback to it: a status report, an inventory upsert or a batch of usage samples is accepted only
for sessions and nodes of the cluster named in the token (`403 forbidden` otherwise). A cluster
that is compromised can therefore lie about its own sessions, but not about anyone else's.

---

## Prerequisites

**On the control plane**, the internal plane has to be reachable from your data-plane clusters.
It is closed by default, which is correct for a single-cluster install:

```bash
helm upgrade gshare charts/gshare -n gshare-system --reuse-values \
  --set ingress.internalPlane.enabled=true \
  --set ingress.internalPlane.sourceRange="10.0.0.0/8"
```

That opens `/internal` and `/.well-known` and nothing else. Both already require the RS256 internal
JWT, so this is not an unauthenticated surface — but restrict `sourceRange` to the networks your
clusters actually live on anyway.

Confirm it:

```bash
curl -s https://gshare.example.com/.well-known/gshare-internal-jwks.json | head -c 40
# {"keys":[{"alg":"RS256", ...     ← a real key, not the console's HTML
```

**On each GPU node of the new cluster**, three things must already work. The attach script checks
all three and stops with the fix if any is missing, because none of them can be done remotely:

```bash
nvidia-smi                                              # driver
nvidia-ctk --version                                    # container toolkit
sudo containerd config dump | grep nvidia-container-runtime   # runtime registered with containerd
```

If the last one prints nothing:

```bash
sudo nvidia-ctk runtime configure --runtime=containerd && sudo systemctl restart containerd
```

If the driver is missing entirely, run `sudo ./hack/cluster-bootstrap.sh prereqs --gpu` on that
node. It usually needs a reboot.

**A kubeconfig** for the new cluster whose `server:` is a real network address. A kubeadm
`admin.conf` often says `127.0.0.1`, which only works from that one node — the control plane has to
reach it too. Fix it before you start:

```bash
grep server: remote.kubeconfig     # must be the node's LAN address, not localhost
```

---

## Attaching a cluster

```bash
./hack/attach-cluster.sh \
  --kubeconfig ~/remote.kubeconfig \
  --name lab-c2 \
  --control-plane https://gshare.example.com \
  --session-domain gshare.lab-c2.example.com \
  --ingress-node master-c2 \
  --storage-values ~/csi-values.yaml     # optional, see "Volumes and storage"
```

`--session-domain` is the hostname that must resolve to the node running this cluster's
ingress-nginx. Sessions on this cluster are advertised there.

Your **current kube context must point at the control plane**, because the operator's token is
signed there — the signing key never leaves it. The remote cluster is addressed only through
`--kubeconfig`.

The script is idempotent. Re-running it is the supported way to repair a half-finished attach or to
roll the operator forward. What it does:

1. Checks the kubeconfig reaches the cluster and is not pointed at localhost.
2. Checks every GPU node's driver and containerd nvidia runtime.
3. Creates the `nvidia` RuntimeClass and labels the GPU nodes (`gpu=on`, `gshare.io/gpu-mode`).
4. Installs HAMi, pinning its scheduler image to the cluster's own Kubernetes version, and waits
   until GPUs are actually advertised.
5. Installs ingress-nginx (skip with `--skip-ingress` if you already run one).
6. Registers the cluster with the control plane, which probes it before accepting.
7. Deploys the operator, mints its token on the control plane and injects it.
8. With `--storage-values`: checks every node has an NFS client, installs democratic-csi against
   the shared pool and points the operator at its StorageClass. Skipped otherwise.
9. Runs the connection test and waits for the first inventory report.

---

## Verifying

```bash
# The cluster answers, with the runtime checks the control plane cares about
curl -sX POST https://gshare.example.com/api/v1/clusters/$CID/connection-test \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
# → {"status":"connected","checks":{"runtime_class_nvidia":true,"hami_device_plugin":true,...}}
```

Then in the console: the cluster appears in the selector in the top bar, its nodes appear under
node management, and its cards appear under GPU management. Pick the cluster in the top bar and the
admin screens narrow to it.

The real test is a session. Create one, pinned to the new cluster, and open it. The URL should
carry the new cluster's hostname — if it carries the control plane's, `session_domain` was not set.

---

## Volumes and storage

gShare volumes are not tied to a cluster: a volume has an owner and a quota, and the operator of
whichever cluster a session lands on creates the PVC for it. That only works if **every cluster
mounts the same pool** — one NFS/ZFS server, one democratic-csi driver per cluster, all pointed at
it. Per-cluster storage would pin each user to the cluster their data happens to be on, which is
the opposite of what a shared fleet is for.

On the control-plane cluster the driver was installed by `cluster-bootstrap.sh`. On an attached
cluster, export its values and install the same driver there:

```bash
# On the control plane: the driver config, including the SSH key it uses on the storage box
helm -n gshare-storage get values gshare-storage > csi-values.yaml && chmod 600 csi-values.yaml
# Edit ONE thing: controller.nodeSelector → a node of the new cluster (it runs the provisioner)
./hack/attach-cluster.sh ... --storage-values csi-values.yaml
```

The values file carries the storage box's SSH key. Keep it out of the repository and delete it
when the attach is done.

### Registering a pool

A pool is a registered object, not something inferred from node roles. Register it in the console
(**Resources → Volumes → Storage pools**) or with `POST /api/v1/storage/pools`, giving:

- **cluster** — the one its storage server sits in;
- **storage class** — the class that provisions from it, the same name the operator is given as
  `--volume-storage-class`;
- **sharing** — `all` for every cluster in the fleet (one NFS box exported to all of them, the
  usual shape), or `selected` plus the clusters allowed to place volumes on it.

**Several storage servers are not one pool.** A volume lives on exactly one — the StorageClass its
PVC names decides where, and gShare chooses nothing. The capacity gate and the dashboard therefore
take the *largest* pool a placement could use as the bound, never the sum: adding two 2 TB servers
into 4 TB licensed volumes neither of them could hold.

### Where the capacity number comes from

In order, and each reading says which it used:

1. **`csi`** — the driver's own `GetCapacity`, published by the external-provisioner as
   `CSIStorageCapacity` objects and read by the operator on its volume-sync tick. This is the
   only automatic source; nothing else can see past the node's root disk.
2. **`manual`** — the figure stated on the pool (`manual_capacity_gb`). The control-plane-wide
   `STORAGE_POOL_CAPACITY_GB` still works as a fleet default for a single-pool install.
3. **`node_disk`** — the storage node's system drive. A stand-in, labelled as one: on a ZFS box it
   is a different disk from the pool and can be off by hundreds of gigabytes either way.

`attach-cluster.sh` sets `csiDriver.storageCapacity=true` so a driver that supports capacity
starts publishing. Not every driver does, and the provisioner also needs
`--enable-capacity`, `--capacity-for-immediate-binding=true` (our StorageClasses bind immediately)
and a driver that reports node topology — without topology the objects are created and removed
again on every refresh. When nothing is published the pool simply keeps its stated capacity, and
the dashboard says `manual` rather than pretending to have measured anything.

Prerequisites on the attached cluster — the script checks both and stops with the fix if missing:

- **An NFS client on every node** (`nfs-common` on Debian/Ubuntu, `nfs-utils` on RHEL): the
  driver mounts the pool on whichever node runs the session. A node without `mount.nfs` leaves
  sessions stuck in `ContainerCreating`.
- **Network reach from every node to the storage box** on 2049/tcp (and 111/tcp, 20048/tcp if the
  export is NFSv3). Nodes on another subnet also need to be listed in the export's allowed range.

The admin dashboard's storage tile reads the pool fleet-wide and says *shared across clusters*
when a cluster is selected, because the pool is not any one cluster's own. `STORAGE_POOL_CAPACITY_GB`
on the control plane states the pool's real size; without it the tile falls back to the storage
node's disk.

---

## Token rotation

The operator's token is valid for seven days. Nothing rotates it automatically today, and when it
expires the operator's callbacks start failing with 401 — the session records stop updating while
pods keep running, which is a confusing state to debug. Put this on a schedule:

```bash
# On the control plane, once a day
CID=clu_...
TOKEN=$(kubectl -n gshare-system exec deploy/gshare-api -c api -- python -c \
  "from app.auth.internal_jwt import sign_internal_jwt; print(sign_internal_jwt('operator:$CID', ttl=604800))")
printf '%s' "$TOKEN" | KUBECONFIG=~/remote.kubeconfig kubectl -n gshare-system \
  create secret generic gshare-operator-internal-jwt --from-file=internal-jwt=/dev/stdin \
  --dry-run=client -o yaml | KUBECONFIG=~/remote.kubeconfig kubectl apply -f -
```

The operator re-reads the file on every attempt, so no restart is needed.

---

## When it does not work

**The cluster registers but no nodes appear.** The operator cannot reach the control plane. Check
its logs, then check that `internalPlane` is enabled and its `sourceRange` includes the cluster:

```bash
KUBECONFIG=~/remote.kubeconfig kubectl -n gshare-system logs deploy/gshare-operator --tail=50
```

**Registration is refused with a runtime error.** The probe found no `nvidia` RuntimeClass or no
HAMi. Both are installed by the attach script; if you registered by hand, install them first.

**Registration hangs, then fails as unreachable.** The apiserver address in the kubeconfig is not
reachable *from the control plane's pods*. The probe runs there, not on your laptop. Expect it to
take a couple of minutes to give up.

**Sessions start but the URL 404s.** `session_domain` is unset or points at the wrong host, so
users are being sent to a cluster whose ingress has no route for that session:

```bash
curl -sX PATCH https://gshare.example.com/api/v1/clusters/$CID \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"session_domain":"gshare.lab-c2.example.com"}'
```

**Sessions start but connecting returns 401.** The session's ingress asks the control plane to
verify the connection token, so the *data-plane cluster's ingress controller* must also reach
`/internal/connect/verify` — not just the operator.

---

## Removing a cluster

```bash
curl -sX DELETE https://gshare.example.com/api/v1/clusters/$CID -H "Authorization: Bearer $TOKEN"
```

Refused while live sessions or allocations exist on it — terminate them first. Deregistering drops
its nodes and devices; the session history stays, because the ledger references it.

---

## Known limits

- **Prometheus is control-plane-wide, not per cluster.** The monitoring screens read one
  Prometheus; an attached cluster's nodes and cards do not appear there until you federate or add
  a second scrape target. The dashboard, node, card and session screens are unaffected — they read
  the control plane's own inventory, which is per cluster.
- **Token rotation is manual.** See above.
- **Images are per cluster.** A session image has to be pullable from the cluster the session lands
  on. Either publish to a registry every cluster can reach, or pre-load each cluster.
- **A volume stays on the cluster that first mounted it.** PersistentVolume objects are per
  cluster, so a volume whose PVC exists on cluster A cannot be mounted by a session on cluster B —
  the scheduler keeps such sessions on A and refuses an explicit request for B (`409
  volume_on_another_cluster`). The data is on the shared pool, but binding it into a second
  cluster's PVC is not automated yet.
- **The credential cannot be rotated in place.** Updating a cluster's kubeconfig means
  deregistering and registering again, which mints a new cluster id — and therefore a new operator
  token and a Helm value to update.

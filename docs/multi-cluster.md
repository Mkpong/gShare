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
  --ingress-node master-c2
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
8. Runs the connection test and waits for the first inventory report.

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

- **Token rotation is manual.** See above.
- **Images are per cluster.** A session image has to be pullable from the cluster the session lands
  on. Either publish to a registry every cluster can reach, or pre-load each cluster.
- **The credential cannot be rotated in place.** Updating a cluster's kubeconfig means
  deregistering and registering again, which mints a new cluster id — and therefore a new operator
  token and a Helm value to update.

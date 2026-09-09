#!/usr/bin/env bash
# Attach a bare Kubernetes cluster to an existing gShare control plane.
#
# Takes a cluster that has nothing but Kubernetes and the NVIDIA driver, and leaves it registered,
# reporting inventory, and able to run sessions. Every step is idempotent: re-running it is how you
# repair a half-finished attach.
#
#   ./hack/attach-cluster.sh \
#       --kubeconfig ~/remote.kubeconfig \
#       --name lab-c2 \
#       --control-plane http://gshare.10.10.0.161.nip.io \
#       --session-domain gshare.10.10.0.167.nip.io \
#       --ingress-node master-c2
#
# What it does NOT do: install the NVIDIA driver or the container toolkit. Those are OS-level and
# have to run on each GPU node (see `cluster-bootstrap.sh prereqs --gpu`); this script checks for
# them and stops with a clear message if they are missing.
set -Eeuo pipefail

die(){ echo "error: $*" >&2; exit 1; }
log(){ echo "[attach] $*"; }
step(){ echo; echo "── $* ──"; }

KUBECONFIG_FILE=""; NAME=""; CONTROL_PLANE=""; SESSION_DOMAIN=""; INGRESS_NODE=""
ADMIN_USER="${GSHARE_ADMIN_USER:-}"; ADMIN_PASS="${GSHARE_ADMIN_PASS:-}"
OPERATOR_TAG="${OPERATOR_TAG:-latest}"; HAMI_VERSION="${HAMI_VERSION:-2.10.0}"
NGINX_VERSION="${NGINX_VERSION:-4.15.1}"; ROLE="${ROLE:-primary}"
CP_NAMESPACE="${CP_NAMESPACE:-gshare-system}"     # namespace of the CONTROL PLANE, in your current kube context
SKIP_INGRESS=0

while [ $# -gt 0 ]; do
  case "$1" in
    --kubeconfig) KUBECONFIG_FILE="$2"; shift 2;;
    --name) NAME="$2"; shift 2;;
    --control-plane) CONTROL_PLANE="$2"; shift 2;;
    --session-domain) SESSION_DOMAIN="$2"; shift 2;;
    --ingress-node) INGRESS_NODE="$2"; shift 2;;
    --operator-tag) OPERATOR_TAG="$2"; shift 2;;
    --role) ROLE="$2"; shift 2;;
    --skip-ingress) SKIP_INGRESS=1; shift;;
    -h|--help) sed -n '2,30p' "$0"; exit 0;;
    *) die "unknown argument: $1";;
  esac
done

[ -n "$KUBECONFIG_FILE" ] || die "--kubeconfig is required"
[ -f "$KUBECONFIG_FILE" ] || die "kubeconfig not found: $KUBECONFIG_FILE"
[ -n "$NAME" ] || die "--name is required (the cluster's name in the console)"
[ -n "$CONTROL_PLANE" ] || die "--control-plane is required, e.g. http://gshare.example.com"
[ -n "$SESSION_DOMAIN" ] || die "--session-domain is required: the hostname THIS cluster serves sessions on"

command -v kubectl >/dev/null || die "kubectl not found"
command -v helm >/dev/null || die "helm not found"
command -v curl >/dev/null || die "curl not found"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CHART="$REPO_ROOT/charts/gshare"
[ -d "$CHART" ] || die "chart not found at $CHART — run this from a checkout"

# Everything below addresses the REMOTE cluster unless it explicitly says otherwise.
r(){ KUBECONFIG="$KUBECONFIG_FILE" "$@"; }

step "1/8  remote cluster reachable"
r kubectl version -o json >/dev/null 2>&1 || die "cannot reach the cluster with that kubeconfig.
  If its server: line points at 127.0.0.1, change it to the control-plane node's LAN address —
  the control plane has to reach this cluster too, not just you."
SERVER=$(r kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}')
log "apiserver: $SERVER"
case "$SERVER" in *127.0.0.1*|*localhost*) die "the kubeconfig points at localhost; use the node's LAN address";; esac
r kubectl get nodes -o wide

step "2/8  GPU nodes have a working driver and container runtime"
GPU_NODES=$(r kubectl get nodes -o json | python3 -c '
import json,sys
# A GPU node is one that already advertises nvidia.com/gpu, or any non-control-plane node when
# nothing advertises yet (the device plugin is what we are about to install).
d=json.load(sys.stdin)["items"]
adv=[n["metadata"]["name"] for n in d if any("nvidia" in k for k in n["status"]["capacity"])]
if adv: print(" ".join(adv))
else:
    print(" ".join(n["metadata"]["name"] for n in d
                   if "node-role.kubernetes.io/control-plane" not in n["metadata"].get("labels",{})))')
[ -n "$GPU_NODES" ] || die "no candidate GPU node found"
log "candidate GPU nodes: $GPU_NODES"
for n in $GPU_NODES; do
  POD="gshare-attach-probe-$n"
  r kubectl -n default delete pod "$POD" --ignore-not-found --wait=false >/dev/null 2>&1 || true
  cat <<EOF | r kubectl apply -f - >/dev/null
apiVersion: v1
kind: Pod
metadata: {name: $POD, namespace: default}
spec:
  nodeName: $n
  hostPID: true
  restartPolicy: Never
  tolerations: [{operator: "Exists"}]
  containers:
    - {name: probe, image: busybox:1.36, command: ["sleep","600"],
       securityContext: {privileged: true}, volumeMounts: [{name: host, mountPath: /host}]}
  volumes: [{name: host, hostPath: {path: /}}]
EOF
  r kubectl -n default wait --for=condition=Ready "pod/$POD" --timeout=120s >/dev/null
  if ! r kubectl -n default exec "$POD" -- chroot /host nvidia-smi -L >/dev/null 2>&1; then
    r kubectl -n default delete pod "$POD" --wait=false >/dev/null 2>&1 || true
    die "$n: nvidia-smi does not work. Install the NVIDIA driver on that node first:
  sudo ./hack/cluster-bootstrap.sh prereqs --gpu     (run ON the node; a reboot is usually needed)"
  fi
  if ! r kubectl -n default exec "$POD" -- chroot /host sh -c \
        'containerd config dump 2>/dev/null | grep -q nvidia-container-runtime'; then
    r kubectl -n default delete pod "$POD" --wait=false >/dev/null 2>&1 || true
    die "$n: containerd has no nvidia runtime. On that node run:
  sudo nvidia-ctk runtime configure --runtime=containerd && sudo systemctl restart containerd"
  fi
  log "$n: driver and nvidia runtime OK"
  r kubectl -n default delete pod "$POD" --wait=false >/dev/null 2>&1 || true
done

step "3/8  RuntimeClass and GPU node labels"
cat <<'EOF' | r kubectl apply -f - >/dev/null
apiVersion: node.k8s.io/v1
kind: RuntimeClass
metadata: {name: nvidia}
handler: nvidia
EOF
log "runtimeclass/nvidia ready"
for n in $GPU_NODES; do
  # HAMi's device plugin selects on gpu=on; the gshare.io labels drive placement and the default mode.
  r kubectl label node "$n" gpu=on gshare.io/gpu=true gshare.io/gpu-mode=fractional --overwrite >/dev/null
  log "$n labelled"
done

step "4/8  HAMi $HAMI_VERSION"
KUBE_VERSION=$(r kubectl version -o json | python3 -c 'import json,sys; print(json.load(sys.stdin)["serverVersion"]["gitVersion"])')
log "pinning HAMi's kube-scheduler image to the cluster version: $KUBE_VERSION"
helm repo add hami https://project-hami.github.io/HAMi/ >/dev/null 2>&1 || true
helm repo update hami >/dev/null 2>&1 || true
SCHED_NODE="${INGRESS_NODE:-$(r kubectl get nodes -l node-role.kubernetes.io/control-plane -o jsonpath='{.items[0].metadata.name}')}"
KUBECONFIG="$KUBECONFIG_FILE" helm upgrade -i hami hami/hami --version "$HAMI_VERSION" -n kube-system \
  --set scheduler.kubeScheduler.imageTag="$KUBE_VERSION" \
  --set scheduler.nodeSelector."kubernetes\.io/hostname"="$SCHED_NODE" \
  --wait --timeout 6m >/dev/null
log "waiting for the device plugin to advertise GPUs"
for _ in $(seq 1 30); do
  ADVERTISED=$(r kubectl get nodes -o json | python3 -c '
import json,sys
print(sum(int(n["status"]["capacity"].get("nvidia.com/gpu",0)) for n in json.load(sys.stdin)["items"]))')
  [ "${ADVERTISED:-0}" -gt 0 ] && break
  sleep 5
done
[ "${ADVERTISED:-0}" -gt 0 ] || die "HAMi did not advertise any GPU. Check: kubectl -n kube-system logs ds/hami-device-plugin"
log "GPUs advertised: $ADVERTISED"

if [ "$SKIP_INGRESS" -eq 0 ]; then
  step "5/8  ingress-nginx (serves this cluster's session URLs)"
  helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx >/dev/null 2>&1 || true
  helm repo update ingress-nginx >/dev/null 2>&1 || true
  KUBECONFIG="$KUBECONFIG_FILE" helm upgrade -i ingress-nginx ingress-nginx/ingress-nginx \
    --version "$NGINX_VERSION" -n ingress-nginx --create-namespace \
    --set controller.hostPort.enabled=true \
    --set controller.service.type=NodePort \
    --set controller.service.nodePorts.http=30080 \
    --set controller.service.nodePorts.https=30443 \
    ${INGRESS_NODE:+--set controller.nodeSelector."kubernetes\.io/hostname"="$INGRESS_NODE"} \
    --set controller.tolerations[0].operator=Exists \
    --wait --timeout 6m >/dev/null
  log "ingress-nginx ready; $SESSION_DOMAIN must resolve to the node it runs on"
else
  step "5/8  ingress-nginx — skipped (--skip-ingress)"
fi

step "6/8  register the cluster with the control plane"
[ -n "$ADMIN_USER" ] || read -rp "control-plane admin email: " ADMIN_USER
[ -n "$ADMIN_PASS" ] || { read -rsp "password: " ADMIN_PASS; echo; }
TOKEN=$(curl -sS -m 30 -X POST "$CONTROL_PLANE/api/v1/auth/login" \
  -H 'Content-Type: application/json' \
  -d "$(python3 -c 'import json,sys; print(json.dumps({"email":sys.argv[1],"password":sys.argv[2]}))' "$ADMIN_USER" "$ADMIN_PASS")" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin).get("access_token",""))')
[ -n "$TOKEN" ] || die "could not log in to $CONTROL_PLANE"

EXISTING=$(curl -sS -m 30 "$CONTROL_PLANE/api/v1/clusters/summary" -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import json,sys; print(next((c['id'] for c in json.load(sys.stdin)['data'] if c['name']=='$NAME'), ''))")
if [ -n "$EXISTING" ]; then
  CLUSTER_ID="$EXISTING"
  log "already registered as $CLUSTER_ID; reusing it"
else
  BODY=$(python3 -c '
import base64,json,sys
print(json.dumps({"name":sys.argv[1],"role":sys.argv[2],"session_domain":sys.argv[3],
                  "kubeconfig_b64":base64.b64encode(open(sys.argv[4],"rb").read()).decode()}))' \
    "$NAME" "$ROLE" "$SESSION_DOMAIN" "$KUBECONFIG_FILE")
  # The probe runs INSIDE the control plane, so this can take a while against an unreachable host.
  RESP=$(curl -sS -m 300 -X POST "$CONTROL_PLANE/api/v1/clusters" \
    -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
    -H "Idempotency-Key: $(python3 -c 'import uuid;print(uuid.uuid4())')" -d "$BODY")
  CLUSTER_ID=$(printf '%s' "$RESP" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("id",""))')
  [ -n "$CLUSTER_ID" ] || die "registration failed: $RESP"
  log "registered as $CLUSTER_ID"
fi

step "7/8  deploy the operator and inject its token"
r kubectl create namespace gshare-system --dry-run=client -o yaml | r kubectl apply -f - >/dev/null
r kubectl label ns gshare-system app.kubernetes.io/managed-by=Helm --overwrite >/dev/null
r kubectl annotate ns gshare-system \
  meta.helm.sh/release-name=gshare meta.helm.sh/release-namespace=gshare-system --overwrite >/dev/null
KUBECONFIG="$KUBECONFIG_FILE" helm upgrade -i gshare "$CHART" -n gshare-system \
  -f "$REPO_ROOT/deploy/values/dataplane.yaml" \
  --set global.imageRegistry=docker.io/boanlab \
  --set images.operator.tag="$OPERATOR_TAG" \
  --set operator.clusterId="$CLUSTER_ID" \
  --set operator.controlPlaneUrl="$CONTROL_PLANE" \
  --set global.domains.console="$SESSION_DOMAIN" \
  --timeout 6m >/dev/null
log "operator deployed"

# The signing key lives only in the control plane, so the token is minted there and copied here.
OP_TOKEN=$(kubectl -n "$CP_NAMESPACE" exec deploy/gshare-api -c api -- python -c \
  "from app.auth.internal_jwt import sign_internal_jwt; print(sign_internal_jwt('operator:$CLUSTER_ID', ttl=604800))" \
  2>/dev/null | tr -d '\r\n')
[ -n "$OP_TOKEN" ] || die "could not mint the operator token.
  This step runs against the CONTROL PLANE using your current kube context (namespace $CP_NAMESPACE).
  Point your context at the control-plane cluster, or set CP_NAMESPACE."
printf '%s' "$OP_TOKEN" | r kubectl -n gshare-system create secret generic gshare-operator-internal-jwt \
  --from-file=internal-jwt=/dev/stdin --dry-run=client -o yaml | r kubectl apply -f - >/dev/null
r kubectl -n gshare-system rollout restart deploy/gshare-operator >/dev/null
r kubectl -n gshare-system rollout status deploy/gshare-operator --timeout=180s >/dev/null
log "operator token injected (valid 7 days — see 'token rotation' in docs/cluster-connect.md)"

step "8/8  verify"
CHECK=$(curl -sS -m 120 -X POST "$CONTROL_PLANE/api/v1/clusters/$CLUSTER_ID/connection-test" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -H "Idempotency-Key: $(python3 -c 'import uuid;print(uuid.uuid4())')" -d '{}')
echo "$CHECK" | python3 -m json.tool 2>/dev/null || echo "$CHECK"

log "waiting for the operator's first inventory report"
for _ in $(seq 1 24); do
  N=$(curl -sS -m 30 "$CONTROL_PLANE/api/v1/nodes?page=1&size=100" -H "Authorization: Bearer $TOKEN" \
      | python3 -c "import json,sys; print(sum(1 for n in (json.load(sys.stdin).get('data') or []) if n.get('cluster_id')=='$CLUSTER_ID'))" 2>/dev/null || echo 0)
  [ "${N:-0}" -gt 0 ] && break
  sleep 5
done
if [ "${N:-0}" -gt 0 ]; then
  log "inventory arrived: $N node(s) reported by this cluster"
else
  echo "warning: no inventory yet. Check the operator's logs:" >&2
  echo "  KUBECONFIG=$KUBECONFIG_FILE kubectl -n gshare-system logs deploy/gshare-operator" >&2
  echo "and confirm this cluster can reach $CONTROL_PLANE/internal/ (the control plane must have" >&2
  echo "ingress.internalPlane.enabled=true)." >&2
fi

echo
log "done. cluster '$NAME' = $CLUSTER_ID"
log "sessions on it will be served at $SESSION_DOMAIN"

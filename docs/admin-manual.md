# Administrator manual

> 📚 [Documentation home](./README.md)

The **administrator console** is where you manage organizations, groups, and users; the
resource catalogue, offerings, and policy; credit allocation; clusters and nodes; live
session monitoring; and the audit log. The end-user screens are covered in
[`user-manual.md`](./user-manual.md).

> The screenshots are of the fictional company *Nexus AI Lab* (see
> [`screenshots/README.md`](screenshots/README.md)), captured in English. The console also ships
> in Korean — switch from the top bar.

## Switching consoles, and what each role sees

Switch to the administrator console from the top right. Menus and data are scoped to your
role:

- **`group_admin`** — their own group.
- **`org_admin`** — their own organization: its groups, users, and budget allocation.
- **`super_admin`** — everything, including organizations, offerings, policy, clusters,
  nodes, and images.

Anything that cannot be undone — deleting a user, group, organization, cluster, offering, preset
or snapshot — asks for the record's name to be typed. Anything that can be, such as removing an
administrator, applies at once and offers **Undo** for a few seconds.

---

## 1. Administrator dashboard

A summary of resources and sessions within your scope.

| Super admin (everything) | Organization admin | Group admin |
|---|---|---|
| ![Global dashboard](screenshots/16-superadmin-admin-dashboard.png) | ![Organization dashboard](screenshots/39-orgadmin-dashboard.png) | ![Group dashboard](screenshots/45-groupadmin-dashboard.png) |

---

An org_admin or group_admin sees the same page scoped to the people they manage: running and
active sessions, the VRAM those sessions hold, and their host CPU — summed over every member of
their groups (org_admin: every group of the organization), never over other tenants. Cluster-wide
figures stay super_admin-only.


## 2. Live session monitoring

Watch sessions and the queue in real time: owner, organization, group, resources, and state
(running, paused, terminated). Sort and search the list, and **force-terminate** one session or
several at once — a bulk termination asks for the count to be typed, since the sessions belong to
other people.

![Session monitoring, all scopes](screenshots/35-superadmin-admin-monitor.png)

An organization admin sees only their organization's sessions; a group admin sees only
their group's.

| Organization admin | Group admin |
|---|---|
| ![Organization monitoring](screenshots/43-orgadmin-monitor.png) | ![Group monitoring](screenshots/48-groupadmin-monitor.png) |

---

**Session liveness.** The operator re-reports every running session once a minute (a
heartbeat carrying the container's restart count and state), and the control plane acts on
what it hears — never on what it assumes:

- *Crash loop* — a container restarted `SESSION_CRASH_LOOP_RESTARTS` (3) times and sitting in
  `CrashLoopBackOff` ends the session (`crash_loop`), settled and notified, instead of billing
  an endless restart cycle.
- *Pod lost* — a session whose heartbeat has been silent for `SESSION_STALE_SEC` (5 min) while
  the operator is otherwise alive (its node inventory is fresh) is settled (`pod_lost`). If the
  operator itself is silent — every node of a cluster stale at once — nothing is touched: an
  operator outage must never turn into mass termination.
- *Node offline* — a node whose kubelet stops answering goes offline at once and its running
  sessions end (`node_offline`); paused sessions are left to resume elsewhere.
- A pod deleted by hand (or evicted) while the session is still wanted is simply rebuilt; its
  exit is not reported as the session's end, so the bill and the reservation are untouched.


## 3. Organizations (super admin)

Create organizations and appoint their administrators.

![Organization list](screenshots/17-superadmin-admin-orgs.png)
![New organization](screenshots/18-superadmin-admin-org-new.png)
![Organization admins](screenshots/19-superadmin-admin-org-admins.png)

---

## 4. Groups

Create groups under an organization and appoint their administrators. An organization admin
sees only their own organization's groups.

![Group list](screenshots/23-superadmin-admin-groups.png)
![New group](screenshots/24-superadmin-admin-group-new.png)
![Group admins](screenshots/25-superadmin-admin-group-admins.png)

| Organization admin scope | Group admin scope |
|---|---|
| ![Groups in the organization](screenshots/41-orgadmin-groups.png) | ![My group](screenshots/47-groupadmin-groups.png) |

---

## 5. Users

Add and edit users. Only users within your scope are listed.

![User list](screenshots/20-superadmin-admin-users.png)
![New user](screenshots/21-superadmin-admin-user-new.png)
![Edit user](screenshots/22-superadmin-admin-user-edit.png)

| Organization admin scope | Group admin scope |
|---|---|
| ![Organization users](screenshots/40-orgadmin-users.png) | ![Group members](screenshots/46-groupadmin-users.png) |

---

## 6. Resources, offerings, presets, and policy (super admin)

Manage GPU offerings (per-model full card, hourly rate, minimum CUDA version), presets
(compute plus a GPU fraction tier — XL ½, L ¼, M ⅛, S 1/16, SS 1/32 — or exclusive), and
resource policies (concurrency, resource ceilings, idle timeout). Policies resolve
most-specific first: **user → group → organization → global**.

The storage rate (`STORAGE_CREDIT_PER_GB_HOUR`) is deployment configuration, set through
the environment. It has no admin UI by design.

![Resources, offerings, presets](screenshots/26-superadmin-admin-resources.png)

> **`gpu_model` must equal the device's reported model string exactly** (e.g.
> `NVIDIA RTX PRO 6000 Blackwell Max-Q Workstation Edition`, not `RTX PRO 6000`): the scheduler
> matches offerings to cards by string equality. The "in cluster" tag on the catalogue row shows
> whether any card in the fleet currently reports that exact string — copy the model from the GPU
> devices screen when creating an offering.
![New offering](screenshots/27-superadmin-admin-offering-new.png)
![Edit offering](screenshots/28-superadmin-admin-offering-edit.png)
![New resource policy](screenshots/29-superadmin-admin-policy-new.png)

---

**GPU model names.** Admission matches an offering's `gpu_model` to the card's reported model
string exactly. The seeded catalogue uses marketing names ("NVIDIA RTX PRO 6000 Blackwell");
the driver may report a longer SKU ("… Max-Q Workstation Edition"). When the operator's inventory
reports a model no offering names exactly and exactly one offering is a word-boundary prefix of
it, that offering adopts the reported string automatically (audited as `offering.align_model`).
If a session is still refused with `unserviceable`, the error now lists the models the fleet
reports (`reported_models`) — copy one of them into the offering.

**Session images.** The catalogue seeds `boanlab/gshare-session:<tag>` for the CUDA 12.4/12.5
line and the Blackwell (CUDA 12.8/12.9) line. Those tags exist on Docker Hub only after the
*Publish session images* workflow has run (on a release tag, or by hand from Actions); a fleet of
Blackwell cards needs the 12.8 line — the older images are refused with `incompatible_image`.


## 7. Credit allocation and requests

Allocate credits down the hierarchy — system → organization → group → individual — and
approve or reject users' allocation requests. An organization admin allocates from the
organization to its groups; a group admin from the group to individuals.

Note that personal and group wallets are also charged continuously for **provisioned volume
capacity**, on top of session compute. A balance can therefore fall even with no session
running.

![Credit allocation, global](screenshots/34-superadmin-admin-allocations.png)
![Credit allocation, organization admin](screenshots/42-orgadmin-allocations.png)

---

## 8. Clusters and nodes (super admin)

Register clusters with a kubeconfig, and manage connection state, nodes, and GPU devices
including their occupancy and mode.

![Clusters](screenshots/30-superadmin-admin-clusters.png)
![Register a cluster](screenshots/31-superadmin-admin-cluster-new.png)
![Nodes](screenshots/32-superadmin-admin-nodes.png)
![GPU devices on a node](screenshots/33-superadmin-admin-node-devices.png)

Node status is driven by the operator's inventory heartbeat: a node that stops reporting for
`NODE_STALE_SEC` (5 minutes) is marked **offline** automatically, and returns to **ready** when
reports resume. Cordon is yours, not the heartbeat's — a cordoned node stays cordoned either way.
The operator reports the node's own Ready condition, so a machine whose kubelet stops answering
goes offline at once — a Node object that merely still exists is not liveness. Sessions that
were running on an offline node are ended (`node_offline`), their credits settled and their GPU
released; paused sessions are left to resume elsewhere. Every
super_admin gets a notification (bell and history) on each transition — *Node offline: gpu3*
and *Node back online: gpu3* — so a machine that silently drops out of the fleet is noticed
without watching the screen.

Per-node actions:

- **Cordon / uncordon** — stop or resume new placements. Sessions already running stay.
- **Drain** — cordon, then move or end the sessions on the node. *Reschedule* cold-pauses each
  running session (`drained`) and resumes it at once; a GPU session needs another card of the
  same model with room and pool access, a CPU session any other CPU node. A session with nowhere
  to go is **parked**: it stays paused and holds a place in the queue, and the queue ticker
  resumes it the moment room appears — when another session ends, or when you uncordon the node.
  *Force terminate* settles every session like an administrator stop. The cordon is mirrored onto
  the Kubernetes node within about fifteen seconds, so nothing — not even a CPU session placed by
  kube-scheduler — lands back on it; a pod that slipped in before the mirror took effect is
  replaced automatically. The node stays cordoned until you uncordon it.
- **Delete** — appears only on an **offline** node, because a node the operator still reports
  would simply reappear on its next inventory tick. It removes the node and its GPU card records
  after refusing (`node_busy`) while any live allocation or non-terminal session remains, and it
  keeps the billing history: past allocations survive, holding their `gpu_uuid`, detached from
  the card that no longer exists. Deleting a node's last card also empties any dedicated pool it
  belonged to — reassign or delete that pool.

The dashboard's **storage panel** shows provisioned volume quota against the pool that backs the
volumes. The operator can only see a storage node's root disk, so set the real pool size once in
the chart (`storage.poolCapacityGb`); until then the panel shows the nodes' disk and says so.

**GPU devices** (the per-node card list) carry a per-card health action: **Mark faulty** takes one
card out of placement and ends every session bound to it (`gpu_fault`, settled, owners notified)
— a process whose CUDA context died cannot be resumed, so an honest end beats a session that
bills for a dead card. **Restore** puts a repaired card back. Fatal Xid events from DCGM still
cordon the whole node automatically; the card action is for the case where one card of several
is bad.

The full machine-level procedure for adding or removing a node — join, labels, drain, `kubeadm
reset` — is in [cluster-setup.md](cluster-setup.md#growing-or-shrinking-a-running-cluster).

---

## 9. Images and templates (super admin)

Manage base images — CUDA version, public or private — and import new ones.

![Images and templates](screenshots/37-superadmin-admin-images.png)
![Import an image](screenshots/38-superadmin-admin-image-import.png)

---

## 10. Audit log

Trace permission, billing, and resource changes within your scope. Filter by actor, action, target
and period; the filter is in the address bar, so a query can be pasted into a ticket and reproduce
the same rows. Open an entry for the full before-and-after and the identifiers to quote.

![Audit log, global](screenshots/36-superadmin-admin-audit.png)
![Audit log, organization](screenshots/44-orgadmin-audit.png)

---

**Export CSV** downloads the current view — every page of it, with the same scope and filters —
as a UTF-8 (BOM) file Excel opens directly: time, actor, action, result, target, organization,
group, and the JSON detail. The export is itself written to the log (`audit.export`, with the
filters and the row count), so a file leaving the system is as traceable as any other action.


## Appendix — capabilities by role

| Capability | User | Group admin | Organization admin | Super admin |
|---|---|---|---|---|
| Own sessions, volumes, wallet | ✅ | ✅ | ✅ | ✅ |
| Session monitoring and audit | — | Group | Organization | Everything |
| User and group management | — | Group | Organization | Everything |
| Organizations, offerings, policy, clusters, nodes, images | — | — | Partial (own organization) | ✅ |
| Credit allocation | Request only | Group → individual | Organization → group | Top-up and everything |

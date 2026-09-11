---
sidebar_position: 1
title: Roles and scope
---

# Roles and scope

gShare has one console with two modes. Anyone with an administrative role can switch to the
**administrator console** from the top right; what it shows is scoped to the role.

| Role | Scope | Typical holder |
|---|---|---|
| **member** | Their own sessions, volumes, and wallet. | Everyone |
| **group_admin** | One group: its members, their sessions, its credit pool. | A team lead |
| **org_admin** | One organization: every group and user in it, the organization's budget. | A department or lab administrator |
| **super_admin** | Everything, plus the platform itself: organizations, offerings, policies, clusters, nodes, storage, images. | The platform operator |

Roles are **scoped**: a group_admin of *Vision* sees nothing of *NLP*, and an org_admin of one
organization sees nothing of another. A person can hold different roles in different groups.

## Capabilities by role

| Capability | member | group_admin | org_admin | super_admin |
|---|---|---|---|---|
| Own sessions, volumes, wallet | ✅ | ✅ | ✅ | ✅ |
| Session monitoring and audit log | — | group | organization | everything |
| User and group management | — | group | organization | everything |
| Credit allocation | request only | group → user | organization → group | top-up and everything |
| Organizations, offerings, policies, clusters, nodes, storage, images | — | — | — | ✅ |

## Two kinds of administrator

The [Tenant administration](./dashboard.md) pages are what an org_admin or group_admin works
with day to day: people, credits, what is running, what happened. The
[Platform administration](./resources.md) pages are super_admin only and describe the machine
side: the GPU catalogue, clusters and nodes, storage pools, images.

## Irreversible actions

Anything that cannot be undone — deleting a user, group, organization, cluster, offering,
preset, or volume — asks for the record's name to be typed. Actions that *can* be undone, such as
removing an administrator, apply at once and offer **Undo** for a few seconds.

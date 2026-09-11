---
sidebar_position: 5
title: Groups
---

# Groups

A **group** is a team inside an organization. It has members, administrators, a credit pool
from which its members' wallets are filled, and optionally its own resource policy.

![Groups](/img/screens/admin-groups.png)

An org_admin sees only their organization's groups; a group_admin sees their own. **New group**
asks for a name and the organization.

## Group administrators

![Group administrators](/img/screens/admin-group-admins.png)

**Administrators** appoints group_admins from the group's members. A group_admin can add and
remove members, allocate the group's credits to individuals, approve members' credit requests,
and monitor the group's sessions.

## Members

Members are added from the [Users](./users.md) page or in bulk. A user may belong to several
groups; sessions created under a group's context inherit that group's policy.

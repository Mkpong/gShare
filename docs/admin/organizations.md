---
sidebar_position: 4
title: Organizations
---

# Organizations

An **organization** is the top of the tenancy tree: it owns groups, groups own users, and credits
flow down the same tree. Organizations are created by the super_admin.

![Organizations](/img/screens/admin-orgs.png)

The list shows each organization with its group and user counts. **New organization** needs only
a name. Deleting one asks for the name to be typed; an organization with live sessions cannot be
deleted.

## Organization administrators

![Organization administrators](/img/screens/admin-org-admins.png)

**Administrators** appoints org_admins from the organization's users. An org_admin manages every
group and user of the organization, allocates the organization's credits to its groups, and sees
the organization's sessions and audit entries — and nothing outside it.

## Budgets

An organization can carry a **budget**: a ceiling on credits its members may consume in a period.
Session admission checks the budget after the personal wallet, so a group that has exhausted its
share is refused even if individual wallets still hold credits.

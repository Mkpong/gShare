---
sidebar_position: 6
title: Users
---

# Users

![Users](/img/screens/admin-users.png)

The list shows every user within your scope with their status, memberships, and roles. Search by
name or email; open a row to edit the display name, reset the password (the user is forced to
choose a new one at the next sign-in), change memberships, or disable the account. A disabled
user is signed out at once and cannot sign in again until re-enabled.

## Adding users

**New user** creates one account with an email, display name, initial password, and group
membership. The user must change the password on first sign-in.

## Bulk import

![Bulk import](/img/screens/admin-users-bulk.png)

**Bulk** accepts a CSV of `email,name,group,role` and creates the accounts in one go, reporting
per row what was created, what already existed, and what was rejected. Use it when onboarding a
class or a new team.

## Deleting

Deleting a user asks for the email to be typed. Their sessions are terminated and settled, their
personal volumes are scheduled for reclamation after the site's grace period, and their audit
history is kept.

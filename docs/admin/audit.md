---
sidebar_position: 15
title: Audit log
---

# Audit log

Every permission, billing, session, and resource change is written to an immutable log: who did
it, what, to which target, the result, and the before-and-after detail.

![Audit log](/img/screens/admin-audit.png)

An org_admin sees their organization's entries, a group_admin their group's, a super_admin
everything. The scope is applied in the query, not in the page — there is no view that leaks
another tenant's actions.

## Filtering

| Filter | Use |
|---|---|
| **Actor** | Name or email — everything one person did |
| **Action** | `session.force_terminate`, `credit.allocate`, `membership.update`, `user.set_global_role`, … |
| **Result** | Succeeded or denied — denials (`access.denied`) are recorded too |
| **Target id** | Everything that happened *to* one session, wallet, or user |
| **Period** | 1 hour, 24 hours, 1 week, 30 days, or a custom range |

The filter lives in the address bar, so a query pasted into a ticket reproduces exactly the same
rows for whoever opens it.

## Reading an entry

![An entry, expanded](/img/screens/admin-audit-detail.png)

Opening a row shows the full detail: the identifiers to quote, and a **before → after** diff for
anything that changed a record. A role change shows both roles; a policy edit shows every field
that moved.

## Export

**Export CSV** downloads the current view — every page of it, with the same scope and filters —
as a UTF-8 (BOM) file Excel opens directly: time, actor, action, result, target, organization,
group, and the JSON detail.

The export is itself logged (`audit.export`, with the filters and the row count), so a file
leaving the system is as traceable as any other action.

## What is recorded

Sign-ins and failures · password changes and resets · role and membership changes · every credit
movement (allocate, reclaim, approve, reject, top-up) · session create, pause, resume, terminate,
force-terminate with its reason · volume create, share, quota change, delete, force delete ·
offering, preset and policy edits · node cordon, drain, delete · cluster registration and
removal · GPU marked faulty or restored · branding, sign-up and placement changes · access
denials, de-duplicated per minute.

Retention is set in the chart (`api.auditRetentionDays`, 180 days by default); `0` keeps
everything.

## Investigations that work

| Question | Query |
|---|---|
| Why did this session end? | Target id = the session id |
| Who ended other people's sessions this week? | Action = `session.force_terminate`, period = 1 week |
| Where did this organization's credits go? | Actor = the org admin, action = `credit.*` |
| Is someone probing for access they lack? | Result = denied |
| Who changed the GPU catalogue? | Action = `offering.*` |

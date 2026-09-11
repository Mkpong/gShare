---
sidebar_position: 13
title: Audit log
---

# Audit log

![Audit log](/img/screens/admin-audit-platform.png)

Every permission, billing, session, and resource change is written to an immutable audit log:
who did it, what, to which target, the result, and the before/after detail. An org_admin sees
their organization's entries, a group_admin their group's, a super_admin everything.

## Filtering

Filter by **actor** (name or email), **action**, **result**, **target id**, and **period**. The
filter is part of the address bar, so a query pasted into a ticket reproduces the same rows.
Open an entry for the full detail and the identifiers to quote.

## Export

**Export CSV** downloads the current view — every page of it, with the same scope and filters —
as a UTF-8 (BOM) file Excel opens directly. The export is itself logged (`audit.export`, with the
filters and the row count), so a file leaving the system is as traceable as any other action.

## What is recorded

Sign-ins and failures, password changes, role and membership changes, every credit movement,
session create/pause/resume/terminate (including who forced it and why), volume create/share/
delete, offering and policy edits, node cordon/drain/delete, cluster registration, branding
changes, and access denials (`access.denied`, de-duplicated per minute).

Retention is set in the chart (`api.auditRetentionDays`, default 180).

"""Who an administrator manages — the one predicate every "managed" view is built on.

Sessions do not always carry a group (the API accepts a session without one, and the wallet is
personal), so tenant scope cannot be read off ``Session.group_id``. It follows the OWNER: a
session belongs to whoever's tenancy its owner is in. The administrator screens — dashboard,
session monitoring, force-terminate — all narrow by this predicate so they agree with each other.
"""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import Principal
from app.db.models import Membership, Project, Session


def managed_owner_filter(principal: Principal, scope: str):
    """The session-owner predicate for an administrator's view.

    ``mine`` (default) is the caller's own sessions. ``managed`` widens it to the people the caller
    administers — every user in the groups they are group_admin of, every group of the organizations
    they are org_admin of, or everyone for a super_admin (``None``: no predicate). A plain member
    asking for ``managed`` gets ``mine``: there is nothing wider to show, and the answer must never
    leak beyond their tenancy.
    """
    if scope != "managed":
        return Session.owner_user_id == principal.user_id
    if principal.global_role == "super_admin" or "super_admin" in principal.global_roles:
        return None
    group_ids = {g for g, role in principal.memberships.items() if role in ("group_admin", "org_admin")}
    org_groups = None
    if principal.org_admin_orgs:
        org_groups = select(Project.id).where(
            Project.org_id.in_(list(principal.org_admin_orgs)), Project.deleted_at.is_(None)
        )
    if not group_ids and org_groups is None:
        return Session.owner_user_id == principal.user_id
    members = select(Membership.user_id).where(Membership.group_id.is_not(None))
    if group_ids and org_groups is not None:
        members = members.where(
            or_(Membership.group_id.in_(list(group_ids)), Membership.group_id.in_(org_groups))
        )
    elif group_ids:
        members = members.where(Membership.group_id.in_(list(group_ids)))
    else:
        members = members.where(Membership.group_id.in_(org_groups))
    # The admin's own sessions count too — they are part of what they run.
    return or_(Session.owner_user_id.in_(members), Session.owner_user_id == principal.user_id)


async def session_is_managed(db: AsyncSession, principal: Principal, session_id: str) -> bool:
    """True if ``session_id`` falls under the caller's managed scope (see managed_owner_filter)."""
    pred = managed_owner_filter(principal, "managed")
    if pred is None:
        return True
    stmt = select(Session.id).where(Session.id == session_id, pred)
    return (await db.scalar(stmt)) is not None

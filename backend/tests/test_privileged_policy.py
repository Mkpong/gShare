"""Privileged (root) sessions are a per-user policy grant: `limits.allow_privileged` merges like
every other limit key (most specific scope wins) and is what the wizard and the admission gate read."""
from __future__ import annotations

import pytest

from app.api.policies_router import _policy_view
from app.core import ids
from app.db.models import ResourcePolicy
from app.domain.policy import resolve_effective_policy
from tests.fkseed import seed


@pytest.mark.asyncio
async def test_grant_resolves_most_specific_first_and_defaults_off(db):
    await seed(db, [
        ResourcePolicy(id=ids.new("policy"), scope="global", scope_id="*", max_concurrent=3, limits={}),
        ResourcePolicy(id=ids.new("policy"), scope="user", scope_id="usr_root_ok", max_concurrent=2,
                       limits={"allow_privileged": True}),
        ResourcePolicy(id=ids.new("policy"), scope="user", scope_id="usr_denied", max_concurrent=2,
                       limits={"allow_privileged": False}),
    ])
    assert (await resolve_effective_policy(db, "usr_root_ok", None)).limits.get("allow_privileged") is True
    assert not (await resolve_effective_policy(db, "usr_denied", None)).limits.get("allow_privileged")
    assert not (await resolve_effective_policy(db, "usr_plain", None)).limits.get("allow_privileged")


def test_policy_view_exposes_the_grant():
    pol = ResourcePolicy(id="pol_x", scope="user", scope_id="u", max_concurrent=1, max_queued=1,
                         limits={"cpu": 4, "allow_privileged": True})
    view = _policy_view(pol)
    assert view["allow_privileged"] is True and view["limits"]["allow_privileged"] is True
    plain = _policy_view(ResourcePolicy(id="pol_y", scope="user", scope_id="v", max_concurrent=1, max_queued=1, limits={}))
    assert plain["allow_privileged"] is False

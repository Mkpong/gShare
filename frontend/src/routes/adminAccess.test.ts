import { describe, expect, it, vi } from 'vitest';
import type { ReactElement } from 'react';

// uplot (pulled in through the session pages the router imports eagerly) reads matchMedia at
// module load; jsdom does not provide it.
vi.hoisted(() => {
  Object.defineProperty(globalThis, 'matchMedia', {
    writable: true,
    value: () => ({ matches: false, addEventListener: () => {}, removeEventListener: () => {}, addListener: () => {}, removeListener: () => {} }),
  });
});
import type { RouteObject } from 'react-router-dom';
import { router } from './router';
import { ADMIN_DASHBOARD, ADMIN_GROUPS, canSee } from '@/components/Layout';
import { ROLE_ORDER, atLeast, type Role } from '@/lib/rbac';

// Every admin nav entry a role can see must lead to a route whose guard admits that role. The two
// tables live in different files (Layout.tsx and router.tsx) and drifted once: an org_admin was
// shown "Nodes" and "GPUs" and landed on /403 for both.

type Guard = { role?: Role; min?: Role };

function guardOf(route: RouteObject): Guard {
  const el = route.element as ReactElement<Guard> | undefined;
  const props = el?.props ?? {};
  return { role: props.role, min: props.min };
}

// Walk the admin subtree: /admin -> RequireAuth -> RequireRole(min group_admin) -> pages.
function adminRoutes(): { path: string; guards: Guard[] }[] {
  const admin = router.routes.find((r) => r.path === 'admin');
  if (!admin?.children) throw new Error('admin route not found');
  const out: { path: string; guards: Guard[] }[] = [];
  const visit = (routes: RouteObject[], guards: Guard[]) => {
    for (const r of routes) {
      const g = [...guards, guardOf(r)];
      if (r.children) visit(r.children, g);
      else out.push({ path: r.index ? '/admin' : `/admin/${r.path}`, guards: g });
    }
  };
  visit(admin.children, []);
  return out;
}

function routeAdmits(guards: Guard[], globalRole: string | undefined, membershipRole: string): boolean {
  const effective = globalRole ?? membershipRole;
  return guards.every((g) => {
    if (globalRole === 'super_admin') return true;
    if (g.role) return effective === g.role;
    if (g.min) return atLeast(effective, g.min);
    return true;
  });
}

describe('admin navigation matches the route guards', () => {
  const routes = adminRoutes();
  const items = [ADMIN_DASHBOARD, ...ADMIN_GROUPS.flatMap((g) => g.items)];

  it('every nav entry has a route', () => {
    for (const item of items) expect(routes.map((r) => r.path), item.to).toContain(item.to);
  });

  for (const role of ROLE_ORDER) {
    it(`a ${role} is not shown a link that redirects to /403`, () => {
      const globalRole = role === 'super_admin' ? 'super_admin' : undefined;
      for (const item of items) {
        if (!canSee(item, globalRole, role)) continue;
        const route = routes.find((r) => r.path === item.to)!;
        expect(routeAdmits(route.guards, globalRole, role), `${role} -> ${item.to}`).toBe(true);
      }
    });
  }
});

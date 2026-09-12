import { useEffect, useState, type ReactNode } from 'react';
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '@/auth/authStore';
import { useUiStore } from '@/store/uiStore';
import { atLeast, type Role } from '@/lib/rbac';
import { formatCredit, roleLabel } from '@/lib/format';
import { useWallet } from '@/api/hooks/useWallet';
import { useAllocationRequests } from '@/api/hooks/useAllocations';
import { useTopupRequests } from '@/api/hooks/useBilling';
import { useResourceRequests } from '@/api/hooks/useResourceRequests';
import { useUsers } from '@/api/hooks/useUsers';
import {
  CaretDown,
  Coins,
  Cube,
  Database,
  Gauge,
  Gear,
  Hourglass,
  List,
  SquaresFour,
  UserCircle,
  SidebarSimple,
  ShieldCheck,
  ClipboardText,
  GraphicsCard,
  Stack,
  HardDrives,
  UsersThree,
  SlidersHorizontal,
  Buildings,
  Package,
  Pulse,
  ChartLine,
  User,
} from './icons';
import { ThemeToggle } from './ThemeToggle';
import { Brand } from './BrandMark';
import { LanguageToggle } from './LanguageToggle';
import { NotificationBell } from './NotificationBell';
import { AccountMenu } from './AccountMenu';
import { ClusterSelector } from './ClusterSelector';

export interface NavItem {
  to: string;
  /** Key into the pending-approval counts, when this destination has an inbox. */
  badge?: 'credits' | 'quota' | 'signups';
  /** Translation key under `nav.user` or `nav.admin`. */
  labelKey: string;
  /** Phosphor glyph, so a destination is recognisable before the label is read. */
  icon?: typeof SquaresFour;
  minRole?: Role;     // absent means every authenticated user
  exactGlobal?: Role; // a global role that has to match exactly, such as super_admin
}

const USER_NAV: NavItem[] = [
  { to: '/', labelKey: 'nav.user.dashboard', icon: Gauge },
  { to: '/sessions', labelKey: 'nav.user.sessions', icon: Cube },
  { to: '/queue', labelKey: 'nav.user.queue', icon: Hourglass },
  { to: '/data', labelKey: 'nav.user.data', icon: Database },
  { to: '/wallet', labelKey: 'nav.user.wallet', icon: Coins },
];

// Eleven flat rows read as a wall; the admin nav is grouped by concern instead. Routes and
// labels are unchanged — only the presentation is grouped. A group disappears entirely when the
// role can see none of its items.
export const ADMIN_DASHBOARD: NavItem = { to: '/admin', labelKey: 'nav.admin.dashboard', icon: Gauge, minRole: 'group_admin' };
export const ADMIN_GROUPS: { labelKey: string; items: NavItem[] }[] = [
  {
    labelKey: 'nav.adminGroup.tenancy',
    items: [
      { to: '/admin/orgs', labelKey: 'nav.admin.orgs', icon: Buildings, exactGlobal: 'super_admin' },
      { to: '/admin/groups', labelKey: 'nav.admin.groups', icon: UsersThree, minRole: 'group_admin' },
      { to: '/admin/users', labelKey: 'nav.admin.users', icon: User, minRole: 'group_admin', badge: 'signups' },
    ],
  },
  {
    labelKey: 'nav.adminGroup.infra',
    items: [
      { to: '/admin/clusters', labelKey: 'nav.admin.clusters', icon: Stack, exactGlobal: 'super_admin' },
      { to: '/admin/nodes', labelKey: 'nav.admin.nodes', icon: HardDrives, minRole: 'org_admin' },
      // The GPU inventory reads node.read, which is super_admin only; an org_admin has no tab there.
      { to: '/admin/gpus', labelKey: 'nav.admin.gpus', icon: GraphicsCard, exactGlobal: 'super_admin' },
    ],
  },
  {
    labelKey: 'nav.adminGroup.resources',
    items: [
      { to: '/admin/resources', labelKey: 'nav.admin.resources', icon: SlidersHorizontal, exactGlobal: 'super_admin' },
      // Group admins decide their members' quota requests (policy.create is scoped to them),
      // so hiding this page from them left the approval inbox unreachable in the console.
      { to: '/admin/policies', labelKey: 'nav.admin.policies', icon: ShieldCheck, minRole: 'group_admin', badge: 'quota' },
      { to: '/admin/images', labelKey: 'nav.admin.images', icon: Package, exactGlobal: 'super_admin' },
      { to: '/admin/volumes', labelKey: 'nav.admin.volumes', icon: Database, exactGlobal: 'super_admin' },
      { to: '/admin/allocations', labelKey: 'nav.admin.allocations', icon: Coins, minRole: 'group_admin', badge: 'credits' },
    ],
  },
  {
    labelKey: 'nav.adminGroup.ops',
    items: [
      { to: '/admin/monitor', labelKey: 'nav.admin.monitor', icon: Pulse, minRole: 'group_admin' },
      { to: '/admin/monitoring', labelKey: 'nav.admin.monitoring', icon: ChartLine, exactGlobal: 'super_admin' },
      { to: '/admin/audit', labelKey: 'nav.admin.audit', icon: ClipboardText, minRole: 'group_admin' },
      { to: '/admin/system', labelKey: 'nav.admin.system', icon: Gear, exactGlobal: 'super_admin' },
    ],
  },
];

export function canSee(item: NavItem, globalRole?: string | null, membershipRole?: string): boolean {
  const effective = globalRole ?? membershipRole;
  if (item.exactGlobal) return globalRole === item.exactGlobal || effective === item.exactGlobal;
  if (item.minRole) return atLeast(effective, item.minRole);
  return true;
}

/** Active is marked by an accent rule and full-strength text, not a filled chip: at this density a
 *  solid block per item turns the sidebar into stripes. */
function navLinkClass({ isActive }: { isActive: boolean }): string {
  return [
    'gs-nav-row relative flex items-center gap-2.5 pl-3 pr-2.5 py-[7px] rounded-ctl text-sm cursor-pointer',
    'transition-colors duration-150',
    'before:absolute before:left-0 before:top-1/2 before:-translate-y-1/2 before:w-[2px] before:rounded-full',
    isActive
      ? 'bg-surface-2 text-text font-semibold before:h-4 before:bg-primary'
      : 'text-muted font-medium hover:bg-surface-2 hover:text-text before:h-0',
  ].join(' ');
}

/** One nav row: glyph plus label, sized so the icon column stays aligned. */
function NavRow({ item, onNavigate, end, count }: {
  item: NavItem; onNavigate: () => void; end?: boolean; count?: number;
}) {
  const { t } = useTranslation();
  const Glyph = item.icon;
  return (
    <NavLink to={item.to} end={end} className={navLinkClass} onClick={onNavigate} title={t(item.labelKey)}>
      <span className="relative shrink-0">
        {Glyph ? <Glyph size={17} className="opacity-90" /> : <span className="block w-[17px]" />}
        {/* On the rail the count has no room; a dot says "something is waiting" and the tooltip
            still names the screen. */}
        {count ? <span className="gs-nav-dot absolute -top-1 -right-1 w-2 h-2 rounded-full bg-warn" aria-hidden="true" /> : null}
      </span>
      <span className="gs-nav-label truncate">{t(item.labelKey)}</span>
      {count ? (
        // Waiting-for-you count: it only clears when the request is decided, never on visiting.
        <span
          className="gs-nav-label ml-auto shrink-0 min-w-[1.25rem] px-1 rounded-tag bg-warn-soft text-warn text-2xs font-bold text-center"
          aria-label={t('nav.pendingCount', { count })}
        >
          {count > 9 ? '9+' : count}
        </span>
      ) : null}
    </NavLink>
  );
}

/** Pending approvals addressed to the viewer, per inbox. Polls with the underlying queries. */
function usePendingApprovals(isAdminConsole: boolean) {
  // The credit screen has TWO inboxes (allocation requests and top-up requests); the badge counts
  // what that screen actually asks the admin to decide.
  // These inboxes exist only in the admin console: fetched from the user console they were four
  // 403s on every page load for a member, and noise in the audit trail.
  const on = { enabled: isAdminConsole };
  const allocs = useAllocationRequests('incoming', on);
  // 페이지의 요청 관리 탭과 같은 기준: super는 전체 수신함(scope=all)을 세야
  // 사이드바 배지와 탭 카운트가 일치한다 (기본 scope=mine은 본인 요청만 본다).
  const isSuperForInbox = useAuthStore((st) => st.claims.global_role === 'super_admin');
  const topups = useTopupRequests({ status: 'pending', ...(isSuperForInbox ? { scope: 'all' as const } : {}) }, on);
  const quota = useResourceRequests('incoming', on);
  // Self-registered accounts waiting for a department and approval.
  const signups = useUsers({ status: 'pending', size: 100 }, on);
  if (!isAdminConsole) return { credits: 0, quota: 0, signups: 0 };
  const pending = (rows: { status?: string }[] | undefined) =>
    (rows ?? []).filter((r) => (r.status ?? 'pending') === 'pending').length;
  const topupRows = (topups.data as { data?: { status?: string }[] } | undefined)?.data;
  const signupRows = (signups.data as { data?: unknown[] } | undefined)?.data;
  return {
    credits: pending(allocs.data) + pending(topupRows),
    quota: pending(quota.data),
    signups: (signupRows ?? []).length,
  };
}

/** Overline above a nav section: labels the console the sidebar is showing. The `nav` element
 *  already announces the same name, so this is visual only. */
function NavSectionLabel({ text }: { text: string }) {
  return (
    <div className="gs-nav-section px-3 pb-1.5 text-2xs font-semibold uppercase tracking-[0.08em] text-muted" aria-hidden="true">
      {text}
    </div>
  );
}

/** The same overline, made a button: an administrator who never touches infrastructure folds that
 *  whole concern away. The caret is the only added ink, and it points down while the group is open. */
function NavGroupHeading({ text, open, onToggle }: { text: string; open: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      className="gs-nav-section w-full flex items-center gap-1 px-3 pb-1.5 text-2xs font-semibold uppercase tracking-[0.08em]
                 text-muted hover:text-text transition-colors duration-150"
      aria-expanded={open}
      onClick={onToggle}
    >
      <span className="truncate">{text}</span>
      <CaretDown
        size={10}
        weight="bold"
        aria-hidden="true"
        className={`shrink-0 transition-transform duration-150 ${open ? '' : '-rotate-90'}`}
      />
    </button>
  );
}

/** Available credits at a glance, one click from the wallet. Quiet chip; while the wallet is
 *  loading or failed it renders nothing rather than a spinner in the topbar. */

/** The foot of the sidebar: this month's balance (user console) above the account block. It sits
 *  OUTSIDE the scrolling list, so identity and balance hold the bottom-left corner no matter how
 *  far the navigation is scrolled. */
function SidebarFoot({ showWallet = false, compact = false }: { showWallet?: boolean; compact?: boolean }) {
  return (
    <div>
      {showWallet && <div className="gs-nav-wallet pb-2 mb-2 border-b border-border"><WalletRow /></div>}
      <AccountMenu variant="sidebar" compact={compact} />
    </div>
  );
}

/** The balance as a line rather than a chip: a label and a figure, the width of the sidebar. */
function WalletRow() {
  const { t } = useTranslation();
  const { data: wallet, isLoading, isError } = useWallet();
  const available = wallet?.available != null ? Number(wallet.available) : null;
  if (isLoading || isError || available == null || Number.isNaN(available)) return null;
  return (
    <Link
      to="/wallet"
      data-wallet-chip
      title={t('nav.walletChip')}
      className="flex items-center justify-between gap-2 px-2 py-1.5 rounded-ctl text-xs
                 hover:bg-surface-2 transition-colors duration-150"
    >
      <span className="text-muted truncate">{t('nav.walletRow')}</span>
      <span className="gs-num font-semibold whitespace-nowrap">{formatCredit(available)} C</span>
    </Link>
  );
}

export function Layout({ children, variant = 'user' }: { children: ReactNode; variant?: 'user' | 'admin' }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useTranslation();
  const isAdminConsole = variant === 'admin';
  // Below `md` the sidebar is a drawer, closed by navigation, Escape or the dimmer.
  const [navOpen, setNavOpen] = useState(false);
  // Collapsed = an icon rail. Deliberately not persisted: every visit starts expanded.
  const [collapsed, setCollapsed] = useState(false);
  useEffect(() => { setNavOpen(false); }, [location.pathname]);
  // Also closes when the destination is the current one, where the pathname does not change.
  const closeNav = () => setNavOpen(false);
  useEffect(() => {
    if (!navOpen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setNavOpen(false); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [navOpen]);
  const { claims, membershipRole, memberships, activeProjectId } = useAuthStore();
  // Folded admin groups, remembered between visits. Landing inside a folded group opens it, so a
  // page is never reachable while its own heading hides it.
  const closedGroups = useUiStore((s) => s.navGroupsClosed);
  const toggleGroup = useUiStore((s) => s.toggleNavGroup);
  const openGroup = useUiStore((s) => s.openNavGroup);
  useEffect(() => {
    const holding = ADMIN_GROUPS.find((g) => g.items.some((i) => location.pathname.startsWith(i.to)));
    if (holding) openGroup(holding.labelKey);
  }, [location.pathname, openGroup]);


  const isSuperAdmin = claims.global_role === 'super_admin';
  const activeProject = memberships.find((m) => m.group_id === activeProjectId);

  // The highest administrative role the user holds, used to label the admin-mode button.
  const memRole = activeProject?.role ?? membershipRole;
  const adminRole: Role | null = isSuperAdmin
    ? 'super_admin'
    : claims.global_role === 'org_admin' || atLeast(memRole, 'org_admin')
      ? 'org_admin'
      : atLeast(memRole, 'group_admin')
        ? 'group_admin'
        : null;
  // The inbox counts need the admin console AND the authority to read those inboxes: a member who
  // types /admin mounts this layout for the instant before the role guard redirects, and asking
  // anyway put a 403 in the log for a page they never saw.
  const pending = usePendingApprovals(isAdminConsole && adminRole !== null);

  return (
    <div className={`gs-shell grid h-full ${collapsed ? 'is-collapsed' : ''}`}>
      {/* Skip past the sidebar. */}
      <a href="#gs-main" className="gs-skip-link">{t('common.skipToContent')}</a>

      <div className={`gs-brand flex items-center gap-2.5 border-b md:border-b-0 md:border-r border-border bg-surface ${collapsed ? 'md:justify-center md:px-0' : 'px-3 md:px-5'}`}>
        <button
          type="button"
          className="md:hidden gs-btn gs-btn-sm min-w-11 justify-center"
          aria-expanded={navOpen}
          aria-controls="gs-nav"
          aria-label={navOpen ? t('nav.closeMenu') : t('nav.openMenu')}
          title={navOpen ? t('nav.closeMenu') : t('nav.openMenu')}
          data-sidebar-toggle
          onClick={() => setNavOpen((v) => !v)}
        >
          <List size={18} aria-hidden="true" />
        </button>
        {/* The wordmark is the console's home button: user shell → /, admin shell → /admin. */}
        <Link
          to={isAdminConsole ? '/admin' : '/'}
          className="flex items-center gap-2.5 min-w-0 rounded-ctl focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
          aria-label={t('nav.brandHome')}
          title={t('nav.brandHome')}
        >
          <Brand size={22} />
        </Link>
        {isAdminConsole && (
          <span className="gs-brand-text gs-pill bg-primary-soft text-primary text-2xs tracking-wide">ADMIN</span>
        )}
      </div>

      {/* Topbar */}
      {/* The bar takes the main area's ground, not the sidebar's: the console reads as one panel
          on the left and one working surface on the right, instead of an L-shaped chrome. Its
          controls are surface-filled, so they still read as raised against it. */}
      <header className="gs-topbar flex items-center gap-2 px-3 md:px-5 bg-bg border-b border-border overflow-x-auto">
        {/* Sidebar rail toggle. Desktop only: below md the sidebar is a drawer with its own button. */}
        <button
          type="button"
          className="max-md:hidden w-[34px] h-[34px] rounded-ctl border border-border bg-surface text-muted grid place-items-center
                     hover:text-text hover:bg-surface-2 transition-colors duration-150"
          aria-pressed={collapsed}
          aria-label={collapsed ? t('nav.expandSidebar') : t('nav.collapseSidebar')}
          title={collapsed ? t('nav.expandSidebar') : t('nav.collapseSidebar')}
          onClick={() => setCollapsed((v) => !v)}
        >
          <SidebarSimple size={17} aria-hidden="true" />
        </button>
        <ClusterSelector />
        <div className="ml-auto flex items-center gap-2">
          {/* Identity and balance live at the foot of the sidebar; the bar keeps the controls that
              act on the whole console. */}
          {/* Mode switch: users holding any administrative role can toggle between the consoles. */}
          {isAdminConsole ? (
            <button type="button" className="gs-btn" onClick={() => navigate('/')} title={t('nav.switchToUser')}>
              <UserCircle size={16} aria-hidden="true" />
              <span className="max-md:hidden">{t('nav.switchToUser')}</span>
            </button>
          ) : (
            adminRole && (
              <button
                type="button"
                className="gs-btn"
                onClick={() => navigate('/admin')}
                title={`${t('nav.switchToAdmin')} (${roleLabel(adminRole)})`}
              >
                <Gear size={16} aria-hidden="true" />
                <span className="max-md:hidden">{t('nav.switchToAdmin')}</span>
              </button>
            )
          )}
          <NotificationBell />
          <LanguageToggle />
          <ThemeToggle />

        </div>
      </header>

      {/* Dimmer behind the drawer. */}
      {navOpen && (
        <div className="md:hidden fixed inset-0 z-30 bg-black/40" onClick={() => setNavOpen(false)} aria-hidden="true" />
      )}

      {/* Sidebar navigation. The user console (/) and the admin console (/admin) are separate. */}
      <nav
        id="gs-nav"
        aria-label={isAdminConsole ? t('nav.adminSection') : t('nav.userSection')}
        className={[
          'gs-sidenav bg-surface border-r border-border flex flex-col min-h-0',
          'max-md:fixed max-md:inset-y-0 max-md:left-0 max-md:w-[240px] max-md:z-40 max-md:pt-16 max-md:transition-transform',
          // `invisible` as well as the transform: an off-screen drawer stays in the tab order.
          navOpen ? 'max-md:translate-x-0' : 'max-md:-translate-x-full max-md:invisible',
        ].join(' ')}
      >
        {/* Only the destinations scroll; the account block below them does not. */}
        <div className="gs-nav-scroll flex-1 min-h-0 overflow-y-auto px-2.5 py-4">
          {!isAdminConsole && (
            <>
              <NavSectionLabel text={t('nav.userSection')} />
              <div className="flex flex-col gap-0.5">
                {USER_NAV.map((i) => (
                  <NavRow key={i.to} item={i} end={i.to === '/'} onNavigate={closeNav} />
                ))}
              </div>
            </>
          )}
          {isAdminConsole && (
            <>
              <NavSectionLabel text={t('nav.adminSection')} />
              <div className="flex flex-col gap-0.5">
                {canSee(ADMIN_DASHBOARD, claims.global_role, membershipRole) && (
                  <NavRow item={ADMIN_DASHBOARD} end onNavigate={closeNav} />
                )}
              </div>
              {ADMIN_GROUPS.map((g) => {
                const visible = g.items.filter((i) => canSee(i, claims.global_role, membershipRole));
                if (visible.length === 0) return null;
                // On the rail the headings are hidden, so there is nothing to fold with: every
                // glyph stays reachable.
                const open = collapsed || !closedGroups.includes(g.labelKey);
                // A folded group still shows a dot when something inside it is waiting.
                const waiting = visible.reduce((n, i) => n + (i.badge ? pending[i.badge] : 0), 0);
                return (
                  <div key={g.labelKey} className="mt-3">
                    <div className="relative">
                      <NavGroupHeading text={t(g.labelKey)} open={open} onToggle={() => toggleGroup(g.labelKey)} />
                      {!open && waiting > 0 && (
                        <span className="absolute top-0 right-2 w-2 h-2 rounded-full bg-warn"
                          aria-label={t('nav.pendingCount', { count: waiting })} />
                      )}
                    </div>
                    {open && (
                      <div className="flex flex-col gap-0.5">
                        {visible.map((i) => (
                          <NavRow key={i.to} item={i} onNavigate={closeNav}
                            count={i.badge ? pending[i.badge] : undefined} />
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </>
          )}
        </div>
        <div className="gs-nav-foot shrink-0 border-t border-border px-2.5 py-3">
          <SidebarFoot showWallet={!isAdminConsole} compact={collapsed} />
        </div>
      </nav>

      <main id="gs-main" tabIndex={-1} className="gs-main overflow-y-auto bg-bg flex flex-col">
        {/* flex column + mt-auto footer: a short page pins the footer to the bottom of the
            viewport, a long page pushes it below the content — never floating mid-screen. */}
        <div className="mx-auto w-full max-w-[1440px] 2xl:max-w-[1800px] min-[2200px]:max-w-[2000px] px-4 py-5 md:px-8 md:py-7 flex-1">{children}</div>
        <AppFooter />
      </main>
    </div>
  );
}


/** The lab footer, at the bottom of every console screen (and the login page). */
export function AppFooter() {
  return (
    <footer className="mt-auto pt-10 pb-6 text-center text-2xs text-muted leading-relaxed">
      <div>
        Licensed under the{' '}
        <a href="https://www.apache.org/licenses/LICENSE-2.0" target="_blank" rel="noreferrer noopener" className="underline hover:text-text">
          Apache License, Version 2.0
        </a>.
      </div>
    </footer>
  );
}

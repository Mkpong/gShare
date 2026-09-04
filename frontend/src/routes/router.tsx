import { createBrowserRouter } from 'react-router-dom';
import { RequireAuth } from '@/auth/RequireAuth';
import { RequireRole } from '@/auth/RequireRole';

import { Login, ChangePassword, Forbidden, NotFound, SystemError } from '@/features/auth/AuthPages';
import { Dashboard } from '@/features/Dashboard';
import { SessionList } from '@/features/session/SessionList';
import { SessionDetail } from '@/features/session/SessionDetail';
import { ConnectPage } from '@/features/session/ConnectModal';
import { QueuePage } from '@/features/queue/QueuePage';
import { VolumePage } from '@/features/volume/VolumePage';
import { WalletPage, CreditRequestPage } from '@/features/wallet/WalletPage';
import { AccountPage } from '@/features/account/AccountPage';
import { PasswordPage } from '@/features/account/PasswordPage';
import { type ComponentType, lazy, Suspense } from 'react';
import { TableSkeleton } from '@/components/EmptyState';

// Route-level code splitting: the admin console, the boards and the session wizard load on first
// visit instead of riding in the entry bundle every user downloads to reach their dashboard.
// Each module still becomes ONE chunk, so sibling pages of a feature share the download.
function RouteFallback() {
  return <div className="gs-card"><TableSkeleton rows={4} columns={3} /></div>;
}
function lazyPage<M extends Record<string, unknown>>(loader: () => Promise<M>, name: keyof M) {
  const C = lazy(async () => ({ default: (await loader())[name] as ComponentType }));
  return <Suspense fallback={<RouteFallback />}><C /></Suspense>;
}


// Route map. The SPA is served from / (see vite.config): the user console at / and the admin
// console at /admin.
export const router = createBrowserRouter(
  [
    { path: '/login', element: <Login /> },
    { path: '/change-password', element: <ChangePassword /> }, // forced password change at first login

    // ===== User console (/) =====
    {
      element: <RequireAuth variant="user" />, // JWT guard plus the user app shell
      children: [
        { index: true, element: <Dashboard /> },
        { path: 'sessions/new', element: lazyPage(() => import('@/features/session/SessionWizard'), 'SessionWizard') },
        { path: 'sessions', element: <SessionList /> },
        { path: 'sessions/:id', element: <SessionDetail /> },
        { path: 'sessions/:id/connect', element: <ConnectPage /> },
        { path: 'queue', element: <QueuePage /> },
        { path: 'wallet', element: <WalletPage /> },
        { path: 'wallet/request', element: <CreditRequestPage /> },
        { path: 'data', element: <VolumePage /> },
        { path: 'notices', element: lazyPage(() => import('@/features/boards/Boards'), 'NoticesPage') },
        { path: 'support', element: lazyPage(() => import('@/features/boards/Boards'), 'InquiriesPage') },
        { path: 'account', element: <AccountPage /> },
        { path: 'account/password', element: <PasswordPage /> },
      ],
    },

    // ===== Admin console (/admin), with its own entry point and layout =====
    {
      path: 'admin',
      element: <RequireAuth variant="admin" />, // JWT guard plus the admin app shell
      children: [
        {
          element: <RequireRole min="group_admin" />,
          children: [
            { index: true, element: lazyPage(() => import('@/features/admin/Dashboard'), 'AdminDashboard') },
            { path: 'orgs', element: <RequireRole role="super_admin">{lazyPage(() => import('@/features/admin/Orgs'), 'AdminOrgs')}</RequireRole> }, // organizations
            { path: 'orgs/:orgId/admins', element: <RequireRole role="super_admin">{lazyPage(() => import('@/features/admin/Orgs'), 'OrgAdminsPage')}</RequireRole> },
            { path: 'users', element: <RequireRole min="group_admin">{lazyPage(() => import('@/features/admin/Users'), 'AdminUsers')}</RequireRole> },
            { path: 'users/bulk', element: <RequireRole min="group_admin">{lazyPage(() => import('@/features/admin/UsersBulkImport'), 'UsersBulkImportPage')}</RequireRole> },
            { path: 'users/:userId/delete', element: <RequireRole min="group_admin">{lazyPage(() => import('@/features/admin/Users'), 'DeleteUserPage')}</RequireRole> },
            { path: 'groups', element: <RequireRole min="group_admin">{lazyPage(() => import('@/features/admin/Groups'), 'AdminGroups')}</RequireRole> },
            { path: 'groups/:groupId/admins', element: <RequireRole min="group_admin">{lazyPage(() => import('@/features/admin/Groups'), 'GroupAdminsPage')}</RequireRole> },
            { path: 'groups/:groupId/delete', element: <RequireRole min="group_admin">{lazyPage(() => import('@/features/admin/Groups'), 'DeleteGroupPage')}</RequireRole> },
            { path: 'resources', element: <RequireRole role="super_admin">{lazyPage(() => import('@/features/admin/Resources'), 'AdminResources')}</RequireRole> },
            { path: 'policies', element: <RequireRole min="group_admin">{lazyPage(() => import('@/features/admin/Resources'), 'AdminPolicies')}</RequireRole> },
            { path: 'policies/new', element: <RequireRole role="super_admin">{lazyPage(() => import('@/features/admin/Resources'), 'CreatePolicyPage')}</RequireRole> },
            { path: 'policies/:policyId/edit', element: <RequireRole role="super_admin">{lazyPage(() => import('@/features/admin/Resources'), 'EditPolicyPage')}</RequireRole> },
            { path: 'clusters', element: <RequireRole role="super_admin">{lazyPage(() => import('@/features/admin/Clusters'), 'AdminClusters')}</RequireRole> },
            // org_admin reaches this page for the node-pools tab only (pool.read); the node inventory
            // itself is super_admin.
            { path: 'nodes', element: <RequireRole min="org_admin">{lazyPage(() => import('@/features/admin/Nodes'), 'AdminNodes')}</RequireRole> },
            { path: 'gpus', element: <RequireRole min="org_admin">{lazyPage(() => import('@/features/admin/Gpus'), 'AdminGpus')}</RequireRole> },
            { path: 'nodes/:nodeId/drain', element: <RequireRole role="super_admin">{lazyPage(() => import('@/features/admin/Nodes'), 'DrainNodePage')}</RequireRole> },
            { path: 'nodes/:nodeId/devices', element: <RequireRole role="super_admin">{lazyPage(() => import('@/features/admin/Nodes'), 'NodeDevicesPage')}</RequireRole> },
            { path: 'allocations', element: lazyPage(() => import('@/features/admin/CreditAllocation'), 'AdminCreditAllocation') }, // credit allocation and requests, group_admin and above
            { path: 'monitor', element: lazyPage(() => import('@/features/admin/Monitor'), 'AdminMonitor') },
            { path: 'monitoring', element: <RequireRole role="super_admin">{lazyPage(() => import('@/features/admin/Monitoring'), 'AdminMonitoring')}</RequireRole> },
            { path: 'monitor/sessions/:sessionId/terminate', element: lazyPage(() => import('@/features/admin/Monitor'), 'ForceTerminatePage') },
            { path: 'audit', element: <RequireRole min="group_admin">{lazyPage(() => import('@/features/admin/Audit'), 'AdminAudit')}</RequireRole> },
            { path: 'notices', element: <RequireRole min="group_admin">{lazyPage(() => import('@/features/boards/Boards'), 'AdminNoticesPage')}</RequireRole> },
            { path: 'inquiries', element: <RequireRole min="group_admin">{lazyPage(() => import('@/features/boards/Boards'), 'AdminInquiriesPage')}</RequireRole> },
            { path: 'images', element: <RequireRole role="super_admin">{lazyPage(() => import('@/features/admin/Images'), 'AdminImages')}</RequireRole> },
            { path: 'volumes', element: <RequireRole role="super_admin">{lazyPage(() => import('@/features/admin/Volumes'), 'AdminVolumes')}</RequireRole> },
          ],
        },
      ],
    },

    { path: '/403', element: <Forbidden /> },
    { path: '/error', element: <SystemError /> },
    { path: '*', element: <NotFound /> },
  ],
);

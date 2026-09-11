import type { SidebarsConfig } from '@docusaurus/plugin-content-docs';

// One sidebar per reader, one navbar tab each. The files all live under ../docs; only the
// tables of contents are split, so a student opening the user guide never scrolls past cluster
// administration, and an administrator is not handed the sign-in walkthrough.
const sidebars: SidebarsConfig = {
  // Students and researchers: what you can do from the console, screen by screen.
  user: [
    'user-manual',
    'user/signing-in',
    'user/dashboard',
    {
      // Sessions are what the console is for, and they have a life: created, connected to,
      // paused, queued, ended. One page each, under a heading that stays open.
      type: 'category',
      label: 'Sessions',
      link: { type: 'doc', id: 'user/sessions' },
      collapsed: false,
      items: [
        'user/sessions-create', 'user/sessions-connect', 'user/sessions-manage',
        'user/sessions-queue', 'user/sessions-end',
      ],
    },
    {
      type: 'category',
      label: 'Data and volumes',
      link: { type: 'doc', id: 'user/data' },
      collapsed: false,
      items: ['user/data-create', 'user/data-mount', 'user/data-share', 'user/data-manage'],
    },
    {
      type: 'category',
      label: 'Wallet and credits',
      link: { type: 'doc', id: 'user/wallet' },
      collapsed: false,
      items: ['user/wallet-ledger', 'user/wallet-request'],
    },
    {
      type: 'category',
      label: 'Account',
      link: { type: 'doc', id: 'user/account' },
      collapsed: false,
      items: ['user/account-password', 'user/account-limits', 'user/account-notifications'],
    },
  ],

  // Administrators. Tenant administration is what an organization or group administrator does
  // day to day; platform administration is the system administrator's fleet.
  admin: [
    'admin-manual',
    'admin/roles',
    {
      type: 'category',
      label: 'Tenant administration',
      collapsed: false,
      items: [
        'admin/dashboard',
        'admin/organizations',
        'admin/groups',
        {
          type: 'category',
          label: 'Users',
          link: { type: 'doc', id: 'admin/users' },
          items: ['admin/users-add', 'admin/users-manage'],
        },
        {
          type: 'category',
          label: 'Credits',
          link: { type: 'doc', id: 'admin/credits' },
          items: ['admin/credits-allocate', 'admin/credits-requests', 'admin/credits-settlement'],
        },
        {
          type: 'category',
          label: 'Session monitoring',
          link: { type: 'doc', id: 'admin/monitoring' },
          items: ['admin/monitoring-control'],
        },
        'admin/audit',
      ],
    },
    {
      type: 'category',
      label: 'Platform administration',
      collapsed: false,
      items: [
        {
          type: 'category',
          label: 'Resources and policy',
          link: { type: 'doc', id: 'admin/resources' },
          items: ['admin/resources-offerings', 'admin/resources-presets', 'admin/resources-policies'],
        },
        {
          type: 'category',
          label: 'Clusters and nodes',
          link: { type: 'doc', id: 'admin/clusters' },
          items: ['admin/nodes', 'admin/node-pools'],
        },
        'admin/gpus',
        'admin/storage',
        'admin/images',
        'admin/platform-monitoring',
        'admin/system',
      ],
    },
  ],

  // Whoever installs and runs it: from an empty machine to a second cluster.
  operations: [
    'getting-started',
    {
      type: 'category',
      label: 'Clusters',
      collapsed: false,
      items: ['cluster-setup', 'cluster-connect', 'multi-cluster'],
    },
    {
      type: 'category',
      label: 'Running the platform',
      collapsed: false,
      items: ['operations/storage', 'operations/observability', 'operations/upgrade', 'operations/backup'],
    },
  ],

  // The parts you look up rather than read through.
  reference: [
    'README',
    'architecture',
    'reference/glossary',
    'reference/helm-values',
    'reference/api',
    'console-ux',
  ],
};

export default sidebars;

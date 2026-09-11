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
    'user/wallet', 'user/data', 'user/account',
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
      items: ['admin/dashboard', 'admin/organizations', 'admin/groups', 'admin/users', 'admin/credits',
              'admin/monitoring', 'admin/audit'],
    },
    {
      type: 'category',
      label: 'Platform administration',
      collapsed: false,
      items: ['admin/resources', 'admin/clusters', 'admin/gpus', 'admin/storage', 'admin/images'],
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

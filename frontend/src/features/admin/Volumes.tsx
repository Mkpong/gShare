import { useState } from 'react';
import { Select } from '@/components/Select';
import { useUrlFilters, distinct } from '@/hooks/useUrlFilters';
import { useProjects } from '@/api/hooks/useGroups';
import { useTranslation } from 'react-i18next';
import { useAllVolumes, useDeleteVolume } from '@/api/hooks/useVolumes';
import { Table, TableToolbar, Pagination, type Column } from '@/components/Table';
import { VolumeMountsPanel } from '@/features/volume/VolumePage';
import { EmptyState, NoResults, TableSkeleton, ErrorState } from '@/components/EmptyState';
import { useTableState, sortRows } from '@/hooks/useTableState';
import { PageHeader } from '@/components/PageHeader';
import { useConfirm } from '@/components/ConfirmDialog';
import { useUiStore } from '@/store/uiStore';
import { useAuthStore } from '@/auth/authStore';
import { humanizeError, asApiError } from '@/lib/errors';
import { BlockGauge } from '@/components/BlockGauge';
import { CopyButton } from '@/components/CopyButton';
import { Database } from '@/components/icons';
import { formatGiB, accessModeLabel } from '@/lib/format';

type Vol = Record<string, unknown> & {
  id: string; name?: string; scope?: string; scope_id?: string; type?: string;
  access_mode?: string; quota_gb?: number; used_gb?: number; mount_locked?: boolean;
  owner_id?: string | null; owner_name?: string | null;
};

const VOL_FILTERS = ['scope', 'mode', 'type', 'group'] as const;

// Fleet volume administration (/admin/volumes): every user's volumes with owner names — the
// user-facing /data page shows only the caller's own world, super_admin included.
export function AdminVolumes() {
  const { t } = useTranslation();
  const { data, isLoading, isError, error, refetch } = useAllVolumes();
  const del = useDeleteVolume();
  const confirm = useConfirm();
  const pushToast = useUiStore((s) => s.pushToast);
  const isSuper = useAuthStore((st) => (st.claims as { global_role?: string }).global_role === 'super_admin');
  const table = useTableState('', { sort: 'owner', dir: 'asc' });
  // Select filters beside the search box, all in the URL like the search itself. The option lists
  // are what the fleet actually holds, so an empty pool never offers a choice that matches nothing.
  const filters = useUrlFilters(VOL_FILTERS);
  const { scope, mode, type, group } = filters.values;
  const projects = useProjects().data ?? [];
  const groupName = (id: string) => projects.find((p) => p.id === id)?.name ?? id;
  const clearAll = () => { table.clear(); filters.clear(); };
  const [selVol, setSelVol] = useState<Vol | null>(null);

  const all = (data ?? []) as Vol[];
  const modes = distinct(all, (v) => v.access_mode);
  const types = distinct(all, (v) => v.type);
  const groups = distinct(all.filter((v) => v.scope === 'group'), (v) => v.scope_id);
  const matched = all.filter((v) => {
    if (scope && v.scope !== scope) return false;
    if (mode && v.access_mode !== mode) return false;
    if (type && v.type !== type) return false;
    if (group && !(v.scope === 'group' && v.scope_id === group)) return false;
    const q = table.query.trim().toLowerCase();
    if (!q) return true;
    return [v.name, v.id, v.owner_name, v.scope_id, v.type].some((x) => String(x ?? '').toLowerCase().includes(q));
  });
  const rows = sortRows(matched, {
    name: (v: Vol) => v.name || v.id,
    owner: (v: Vol) => v.owner_name ?? v.scope_id ?? '',
    scope: (v: Vol) => v.scope ?? '',
    quota: (v: Vol) => (v.quota_gb ? (v.used_gb ?? 0) / v.quota_gb : 0),
  }[table.sort ?? 'owner'] ?? null, table.dir);
  const pageRows = rows.slice((table.page - 1) * 25, table.page * 25);

  const onDelete = async (v: Vol) => {
    const ok = await confirm({
      title: t('volume.confirmDeleteTitle', { name: v.name || v.id }),
      body: t('volume.confirmDelete'),
      consequences: [t('admin.volumes.consequenceOwner', { owner: v.owner_name ?? v.scope_id ?? '-' })],
      confirmLabel: t('common.delete'),
      destructive: true,
      confirmText: v.name || v.id,
    });
    if (!ok) return;
    del.mutate(v.id, {
      onSuccess: () => { pushToast('success', t('volume.deleted')); refetch(); },
      onError: async (e) => {
        const err = asApiError(e);
        // Still mounted: the system administrator may cut the mounting sessions off and delete
        // anyway — the answer to a mount that keeps a shared volume alive against its owner.
        if (err.code === 'volume_mounted' && isSuper) {
          const force = await confirm({
            title: t('admin.volumes.forceDeleteTitle', { name: v.name || v.id }),
            body: t('admin.volumes.forceDeleteBody'),
            consequences: [t('admin.volumes.forceDeleteConsequence')],
            confirmLabel: t('admin.volumes.forceDelete'),
            destructive: true,
          });
          if (!force) return;
          del.mutate({ id: v.id, force: true }, {
            onSuccess: () => { pushToast('success', t('admin.volumes.forceDeleted')); refetch(); },
            onError: (e2) => pushToast('error', humanizeError(asApiError(e2))),
          });
          return;
        }
        pushToast('error', humanizeError(err));
      },
    });
  };

  const columns: Column<Vol>[] = [
    {
      key: 'name',
      header: t('volume.colVolume'),
      sortBy: (v) => v.name || v.id,
      render: (v) => (
        <span className="inline-flex items-center gap-1.5 min-w-0">
          <b className="truncate">{v.name || v.id}</b>
          {v.mount_locked && <span className="gs-tag shrink-0 text-warn">{t('volume.lockedTag')}</span>}
          <CopyButton value={v.id} label={t('common.copy')} />
        </span>
      ),
    },
    {
      key: 'owner',
      header: t('admin.volumes.colOwner'),
      sortBy: (v) => v.owner_name ?? v.scope_id ?? '',
      render: (v) => v.owner_name
        ? <span className="truncate" title={v.owner_id ?? undefined}>{v.owner_name}</span>
        : <span className="font-mono text-xs">{v.scope_id ?? '-'}</span>,
    },
    {
      key: 'scope',
      header: t('volume.colScope'),
      hideOnMobile: true,
      sortBy: (v) => v.scope ?? '',
      render: (v) => <span className="gs-tag">{t(`enum.scope.${v.scope}`, { defaultValue: v.scope ?? '-' })}</span>,
    },
    {
      key: 'access_mode',
      header: t('volume.colAccessMode'),
      hideOnMobile: true,
      render: (v) => accessModeLabel(v.access_mode),
    },
    {
      key: 'quota',
      header: t('volume.colQuota'),
      align: 'right',
      sortBy: (v) => (v.quota_gb ? (v.used_gb ?? 0) / v.quota_gb : 0),
      render: (v) => {
        const pct = v.quota_gb ? Math.min(100, Math.round(((v.used_gb ?? 0) / v.quota_gb) * 100)) : 0;
        return (
          <span className="inline-flex items-center gap-2.5" title={t('volume.usagePercent', { percent: pct })}>
            <span className="gs-num">{formatGiB(v.used_gb ?? 0)} / {formatGiB(v.quota_gb ?? 0)}</span>
            <BlockGauge value={pct} label={t('volume.usagePercent', { percent: pct })} />
          </span>
        );
      },
    },
    {
      key: 'actions',
      header: '',
      align: 'right',
      sortable: false,
      render: (v) => (
        <button type="button" className="gs-btn gs-btn-sm gs-btn-danger" disabled={del.isPending} onClick={() => onDelete(v)}>
          {t('common.delete')}
        </button>
      ),
    },
  ];

  return (
    <div>
      <PageHeader title={t('admin.volumes.title')} description={t('admin.volumes.subtitle')} />
      <TableToolbar
        query={table.query}
        onQueryChange={table.setQuery}
        placeholder={t('admin.volumes.searchPlaceholder')}
        total={all.length}
        shown={matched.length}
        onClear={clearAll}
      >
        <Select className="gs-input w-auto" data-url-state value={scope} aria-label={t('admin.volumes.allScopes')} onChange={(e) => filters.set('scope', e.target.value)}>
          <option value="">{t('admin.volumes.allScopes')}</option>
          {(['user', 'group', 'global'] as const).map((v) => <option key={v} value={v}>{t(`enum.scope.${v}`)}</option>)}
        </Select>
        <Select className="gs-input w-auto" data-url-state value={mode} aria-label={t('admin.volumes.allModes')} onChange={(e) => filters.set('mode', e.target.value)}>
          <option value="">{t('admin.volumes.allModes')}</option>
          {modes.map((v) => <option key={v} value={v}>{accessModeLabel(v)}</option>)}
        </Select>
        <Select className="gs-input w-auto" data-url-state value={type} aria-label={t('admin.volumes.allTypes')} onChange={(e) => filters.set('type', e.target.value)}>
          <option value="">{t('admin.volumes.allTypes')}</option>
          {types.map((v) => <option key={v} value={v}>{t(`volume.type.${v}`, { defaultValue: v })}</option>)}
        </Select>
        <Select className="gs-input w-auto" data-url-state value={group} aria-label={t('admin.volumes.allGroups')} onChange={(e) => filters.set('group', e.target.value)}>
          <option value="">{t('admin.volumes.allGroups')}</option>
          {groups.map((v) => <option key={v} value={v}>{groupName(v)}</option>)}
        </Select>
      </TableToolbar>
      <div className="gs-card">
        {isError ? (
          <ErrorState error={error} onRetry={() => refetch()} />
        ) : isLoading ? (
          <TableSkeleton rows={4} columns={5} />
        ) : rows.length === 0 ? (
          (table.isFiltered || filters.any)
            ? <NoResults query={table.query} onClear={clearAll} />
            : <EmptyState icon={<Database size={26} />} title={t('admin.volumes.empty')} description={t('admin.volumes.emptyDescription')} />
        ) : (
          <Table
            caption={t('admin.volumes.title')}
            columns={columns}
            rows={pageRows}
            rowKey={(v) => v.id}
            onRowClick={(v) => setSelVol((cur) => (cur?.id === v.id ? null : v))}
            expandedKey={selVol?.id ?? null}
            renderExpansion={(v) => <VolumeMountsPanel vol={{ id: v.id, name: (v as { name?: string | null }).name }} />}
            sort={table.sort}
            dir={table.dir}
            onSort={table.toggleSort}
          />
        )}
      </div>
      <Pagination page={table.page} pageSize={25} total={rows.length} onPage={table.setPage} />
    </div>
  );
}

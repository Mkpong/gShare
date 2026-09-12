import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Select } from '@/components/Select';
import { Dialog } from '@/components/Dialog';
import { Field, DisabledReason } from '@/components/Field';
import { Table, type Column } from '@/components/Table';
import { EmptyState, TableSkeleton, ErrorState } from '@/components/EmptyState';
import { CopyButton } from '@/components/CopyButton';
import { Timestamp } from '@/components/Timestamp';
import { useConfirm } from '@/components/ConfirmDialog';
import { useUiStore } from '@/store/uiStore';
import { humanizeError, asApiError } from '@/lib/errors';
import { useClusterSummary } from '@/api/hooks/useClusters';
import { useNodes } from '@/api/hooks/useNodes';
import {
  useStoragePools, useCreateStoragePool, useUpdateStoragePool, useDeleteStoragePool,
  type StoragePool, type PoolShareScope, type StoragePoolCreateBody,
} from '@/api/hooks/useStoragePools';
import { HardDrives, Plus } from '@/components/icons';

// Storage pools (/admin/volumes?tab=pools): the registered storage servers behind user volumes.
// A pool is (cluster, StorageClass) plus how it is shared and how big it is. The list is what the
// capacity gate and the dashboard read, so this is where an operator makes a new server count.
export function StoragePoolsPanel() {
  const { t } = useTranslation();
  const { data: pools = [], isLoading, isError, error, refetch } = useStoragePools();
  const del = useDeleteStoragePool();
  const confirm = useConfirm();
  const pushToast = useUiStore((s) => s.pushToast);
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<StoragePool | null>(null);

  const onDelete = async (p: StoragePool) => {
    const ok = await confirm({
      title: t('admin.storagePools.confirmDeleteTitle', { name: p.name }),
      body: t('admin.storagePools.confirmDeleteBody'),
      consequences: [t('admin.storagePools.consequenceVolumes'), t('admin.storagePools.consequenceGate')],
      confirmLabel: t('common.delete'),
      destructive: true,
      confirmText: p.name,
    });
    if (!ok) return;
    del.mutate(p.id, {
      onSuccess: () => pushToast('success', t('admin.storagePools.deleted', { name: p.name })),
      onError: (e) => pushToast('error', humanizeError(asApiError(e))),
    });
  };

  const sourceLabel = (s: StoragePool['capacity_source']) =>
    s ? t(`admin.storagePools.source.${s}`, { defaultValue: s }) : t('admin.storagePools.source.none');

  const columns: Column<StoragePool>[] = [
    {
      key: 'name',
      header: t('admin.storagePools.colPool'),
      sortBy: (p) => p.name,
      render: (p) => (
        <span className="inline-flex items-center gap-1.5 min-w-0">
          <b className="truncate">{p.name}</b>
          <CopyButton value={p.id} label={t('common.copy')} />
        </span>
      ),
    },
    { key: 'cluster', header: t('common.cluster'), sortBy: (p) => p.cluster_name ?? p.cluster_id, render: (p) => <span className="gs-tag">{p.cluster_name ?? p.cluster_id}</span> },
    { key: 'storage_class', header: t('admin.storagePools.colClass'), sortBy: (p) => p.storage_class, render: (p) => <code className="font-mono text-xs">{p.storage_class}</code> },
    { key: 'node', header: t('admin.storagePools.colNode'), hideOnMobile: true, sortBy: (p) => p.node_hostname ?? '', render: (p) => p.node_hostname ?? <span className="text-muted">-</span> },
    {
      key: 'share',
      header: t('admin.storagePools.colShare'),
      hideOnMobile: true,
      sortBy: (p) => p.share_scope,
      render: (p) => p.share_scope === 'all'
        ? <span className="gs-tag">{t('admin.storagePools.shareAll')}</span>
        : <span className="text-xs">{p.shared_with_names.length ? p.shared_with_names.join(', ') : t('admin.storagePools.shareNone')}</span>,
    },
    {
      key: 'capacity',
      header: t('admin.storagePools.colCapacity'),
      align: 'right',
      sortBy: (p) => p.capacity_gb ?? 0,
      render: (p) => (
        <span className="inline-flex items-center gap-2 justify-end">
          <span className="gs-num">{p.capacity_gb != null ? `${p.capacity_gb} GB` : '-'}</span>
          <span className="gs-tag" title={p.capacity_source === 'csi' && p.capacity_reported_at ? t('admin.storagePools.reportedAt') : undefined}>
            {sourceLabel(p.capacity_source)}
          </span>
          {p.capacity_source === 'csi' && p.capacity_reported_at && <Timestamp value={p.capacity_reported_at} compact className="text-muted text-xs" />}
        </span>
      ),
    },
    {
      key: 'actions',
      header: '',
      align: 'right',
      sortable: false,
      render: (p) => (
        <span className="inline-flex gap-2">
          <button type="button" className="gs-btn gs-btn-sm" onClick={() => setEditing(p)}>{t('common.edit')}</button>
          <button type="button" className="gs-btn gs-btn-sm gs-btn-danger" disabled={del.isPending} onClick={() => onDelete(p)}>{t('common.delete')}</button>
        </span>
      ),
    },
  ];

  return (
    <div>
      <div className="flex items-center justify-end gap-3 mb-3 flex-wrap">
        <button type="button" className="gs-btn gs-btn-primary" onClick={() => setCreateOpen(true)}>
          <Plus size={15} weight="bold" aria-hidden="true" />{t('admin.storagePools.register')}
        </button>
      </div>
      <Dialog open={createOpen} wide title={t('admin.storagePools.registerTitle')} onClose={() => setCreateOpen(false)}>
        <PoolForm onDone={() => setCreateOpen(false)} />
      </Dialog>
      <Dialog open={!!editing} wide title={`${t('admin.storagePools.editTitle')} - ${editing?.name ?? ''}`} onClose={() => setEditing(null)}>
        {editing && <PoolForm pool={editing} onDone={() => setEditing(null)} />}
      </Dialog>
      <div className="gs-card">
        {isError ? (
          <ErrorState error={error} onRetry={() => refetch()} />
        ) : isLoading ? (
          <TableSkeleton rows={2} columns={6} />
        ) : pools.length === 0 ? (
          <EmptyState
            icon={<HardDrives size={26} />}
            title={t('admin.storagePools.empty')}
            description={t('admin.storagePools.emptyDescription')}
            action={<button type="button" className="gs-btn gs-btn-primary" onClick={() => setCreateOpen(true)}>{t('admin.storagePools.register')}</button>}
          />
        ) : (
          <Table caption={t('admin.storagePools.title')} columns={columns} rows={pools} rowKey={(p) => p.id} />
        )}
      </div>
    </div>
  );
}

// One form for both registering and editing. On edit the cluster is fixed — a pool belongs to
// the cluster its server sits in — and everything else can change.
function PoolForm({ pool, onDone }: { pool?: StoragePool; onDone: () => void }) {
  const { t } = useTranslation();
  const pushToast = useUiStore((s) => s.pushToast);
  const create = useCreateStoragePool();
  const update = useUpdateStoragePool();
  const clusters = useClusterSummary().data ?? [];
  const [name, setName] = useState(pool?.name ?? '');
  const [clusterId, setClusterId] = useState(pool?.cluster_id ?? '');
  const [storageClass, setStorageClass] = useState(pool?.storage_class ?? '');
  const [nodeId, setNodeId] = useState(pool?.node_id ?? '');
  const [shareScope, setShareScope] = useState<PoolShareScope>(pool?.share_scope ?? 'all');
  const [sharedWith, setSharedWith] = useState<string[]>(pool?.shared_with ?? []);
  const [manualGb, setManualGb] = useState(pool?.manual_capacity_gb != null ? String(pool.manual_capacity_gb) : '');
  const [serverError, setServerError] = useState<string | null>(null);
  const effectiveCluster = clusterId || clusters[0]?.id || '';
  // Only this cluster's nodes can be the pool's server; storage-role nodes are what an operator
  // labelled for the job, so they lead the list.
  const { data: nodes = [] } = useNodes(effectiveCluster ? { cluster_id: effectiveCluster } : {}, { enabled: !!effectiveCluster });
  const nodeOptions = useMemo(
    () => [...nodes].sort((a, b) => Number(b.role === 'storage') - Number(a.role === 'storage') || a.hostname.localeCompare(b.hostname)),
    [nodes],
  );
  const otherClusters = clusters.filter((c) => c.id !== effectiveCluster);
  const manualNum = manualGb.trim() === '' ? null : Number(manualGb);

  const linkedNode = nodeOptions.find((n) => n.id === nodeId);
  const blockers: string[] = [];
  if (!linkedNode && !name.trim()) blockers.push(t('admin.storagePools.name'));
  if (!effectiveCluster) blockers.push(t('common.cluster'));
  if (!storageClass.trim()) blockers.push(t('admin.storagePools.storageClass'));
  if (shareScope === 'selected' && sharedWith.length === 0) blockers.push(t('admin.storagePools.blockerSharedWith'));
  if (manualNum != null && (!Number.isFinite(manualNum) || manualNum < 0)) blockers.push(t('admin.storagePools.blockerCapacity'));

  const submit = () => {
    if (blockers.length) return;
    setServerError(null);
    const body: StoragePoolCreateBody = {
      name: linkedNode ? linkedNode.hostname : name.trim(),
      cluster_id: effectiveCluster,
      storage_class: storageClass.trim(),
      node_id: nodeId || null,
      share_scope: shareScope,
      shared_with: shareScope === 'selected' ? sharedWith : [],
      manual_capacity_gb: manualNum,
    };
    const onError = (e: unknown) => { const m = humanizeError(asApiError(e)); setServerError(m); pushToast('error', m); };
    if (pool) {
      const { cluster_id: _omit, ...patch } = body;
      void _omit;
      update.mutate({ id: pool.id, body: patch }, {
        onSuccess: () => { pushToast('success', t('admin.storagePools.updated', { name: body.name })); onDone(); },
        onError,
      });
    } else {
      create.mutate(body, {
        onSuccess: () => { pushToast('success', t('admin.storagePools.registered', { name: body.name })); onDone(); },
        onError,
      });
    }
  };
  const busy = create.isPending || update.isPending;

  return (
    <form className="gs-card" noValidate onSubmit={(e) => { e.preventDefault(); submit(); }}>
      <div className="grid grid-cols-2 gap-3 max-[640px]:grid-cols-1">
        <Field label={t('common.cluster')} required hint={pool ? t('admin.storagePools.clusterFixed') : t('admin.storagePools.clusterHint')}>
          {(ids) => (
            <Select {...ids} className="gs-input w-full" value={effectiveCluster} disabled={!!pool} onChange={(e) => { setClusterId(e.target.value); setNodeId(''); setSharedWith([]); }}>
              {clusters.length === 0 && <option value="">-</option>}
              {clusters.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
          )}
        </Field>
        <Field label={t('admin.storagePools.storageClass')} required hint={t('admin.storagePools.storageClassHint')}>
          {(ids) => <input {...ids} className="gs-input w-full font-mono" value={storageClass} maxLength={200} autoComplete="off" placeholder="gshare-data" onChange={(e) => setStorageClass(e.target.value)} />}
        </Field>
        <Field label={t('admin.storagePools.node')} hint={t('admin.storagePools.nodeHint')}>
          {(ids) => (
            <Select {...ids} className="gs-input w-full" value={nodeId} onChange={(e) => setNodeId(e.target.value)}>
              <option value="">{t('admin.storagePools.nodeNone')}</option>
              {nodeOptions.map((n) => (
                <option key={n.id} value={n.id}>{n.hostname}{n.role === 'storage' ? ` · ${t('admin.storagePools.nodeStorageTag')}` : ''}</option>
              ))}
            </Select>
          )}
        </Field>
        {/* Named after its server: the hostname while a node is linked, typed only for a pool the
            cluster never sees as a node (an external appliance). */}
        <Field label={t('admin.storagePools.name')} required={!linkedNode} hint={linkedNode ? t('admin.storagePools.nameFromNode') : t('admin.storagePools.nameHint')}>
          {(ids) => <input {...ids} className="gs-input w-full" value={linkedNode ? linkedNode.hostname : name} disabled={!!linkedNode} maxLength={80} autoComplete="off" placeholder={t('admin.storagePools.namePlaceholder')} onChange={(e) => setName(e.target.value)} />}
        </Field>
        <Field label={t('admin.storagePools.manualCapacity')} hint={t('admin.storagePools.manualCapacityHint')}>
          {(ids) => <input {...ids} className="gs-input w-full" type="number" inputMode="numeric" min={0} step={1} value={manualGb} autoComplete="off" placeholder={t('admin.storagePools.manualCapacityPlaceholder')} onChange={(e) => setManualGb(e.target.value)} />}
        </Field>
        <Field label={t('admin.storagePools.share')} hint={t('admin.storagePools.shareHint')} className="sm:col-span-2">
          {(ids) => (
            <Select {...ids} className="gs-input w-full" value={shareScope} onChange={(e) => setShareScope(e.target.value as PoolShareScope)}>
              <option value="all">{t('admin.storagePools.shareAll')}</option>
              <option value="selected">{t('admin.storagePools.shareSelected')}</option>
            </Select>
          )}
        </Field>
        {shareScope === 'selected' && (
          <fieldset className="sm:col-span-2 border border-border rounded-card p-3">
            <legend className="text-xs font-semibold text-muted px-1">{t('admin.storagePools.sharedWith')}</legend>
            {otherClusters.length === 0 ? (
              <p className="text-muted text-xs">{t('admin.storagePools.noOtherClusters')}</p>
            ) : (
              <div className="flex flex-wrap gap-x-5 gap-y-2">
                {otherClusters.map((c) => (
                  <label key={c.id} className="inline-flex items-center gap-2 text-sm cursor-pointer">
                    <input type="checkbox" checked={sharedWith.includes(c.id)} onChange={(e) => setSharedWith((cur) => e.target.checked ? [...cur, c.id] : cur.filter((x) => x !== c.id))} />
                    {c.name}
                  </label>
                ))}
              </div>
            )}
          </fieldset>
        )}
      </div>
      {serverError && <p role="alert" className="text-danger text-xs mt-3">{serverError}</p>}
      <div className="flex justify-end items-center gap-3 mt-4 flex-wrap">
        <DisabledReason reasons={blockers} />
        <button type="submit" className="gs-btn gs-btn-primary disabled:opacity-50" disabled={blockers.length > 0 || busy}>
          {busy ? t('common.saving') : pool ? t('common.save') : t('admin.storagePools.register')}
        </button>
        <button type="button" className="gs-btn" onClick={onDone}>{t('common.cancel')}</button>
      </div>
    </form>
  );
}

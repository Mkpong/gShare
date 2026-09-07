import { useState } from 'react';
import { Link } from 'react-router-dom';
import { PageHeader } from '@/components/PageHeader';
import { CopyButton } from '@/components/CopyButton';
import { useTranslation } from 'react-i18next';
import { useSessions } from '@/api/hooks/useSessions';
import { useDashboardSummary } from '@/api/hooks/useDashboard';
import { formatCredit, runwayLabel, sessionBurnPerHour, sessionStatusLabel } from '@/lib/format';
import { StatusPill } from '@/components/StatusPill';
import { ArrowRight, Database, GraphicsCard, Plus } from '@/components/icons';
import { Figure } from '@/components/Figure';
import { HelpTip } from '@/components/HelpTip';
import { Meter } from '@/components/Meter';
import { Dialog } from '@/components/Dialog';
import { NewVolumeForm } from '@/features/volume/VolumePage';
import { QuotaRequestForm } from '@/features/account/QuotaRequestPage';

interface DashboardPool {
  id: string | null;
  name: string;
  kind: 'shared' | 'dedicated';
  tier: 'group' | 'org' | 'shared';
}

const pct = (used?: number | null, total?: number | null) =>
  total && total > 0 ? Math.min(100, Math.round(((used ?? 0) / total) * 100)) : 0;
const gb = (mb?: number | null) => Math.round(((mb ?? 0) / 1024) * 10) / 10;

/**
 * Coarse congestion per GPU model, from the share of VRAM still free. Users get a traffic light —
 * "can I start something on this model right now?" — not the meter and card counts the admin
 * screens show. The thresholds here are the one place to tune it.
 */
type Congestion = 'free' | 'moderate' | 'congested' | 'unavailable';
const congestion = (freeMb?: number | null, totalMb?: number | null): Congestion => {
  const free = freeMb ?? 0;
  const total = totalMb ?? 0;
  if (total <= 0 || free <= 0) return 'unavailable';
  const share = free / total;
  if (share >= 0.6) return 'free';
  if (share >= 0.3) return 'moderate';
  return 'congested';
};

/**
 * A quota line: the reading on one line, the fill as a hairline under it. The percentage is only
 * spelled out once there is something to report — an idle account read as seven "0%" columns and
 * seven dividing rules, which is a lot of ink for "nothing is in use".
 */
function QuotaRow({ label, used, limit, unit, variant }: {
  label: string;
  used: number;
  /** null means the policy sets no ceiling for this dimension. */
  limit?: number | null;
  unit?: string;
  variant?: 'primary' | 'warn' | 'free';
}) {
  const { t } = useTranslation();
  const bounded = limit != null && limit > 0;
  const meter = bounded ? pct(used, limit) : 0;
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-xs font-semibold text-muted truncate">{label}</span>
        <span className="gs-num text-sm font-semibold whitespace-nowrap">
          {used}
          <span className="text-muted font-medium">
            {bounded ? ` / ${limit}` : ''}{unit ? ` ${unit}` : ''}
          </span>
          {bounded && meter >= 1 && (
            <span className="ml-1.5 text-2xs text-muted font-medium">{Math.round(meter)}%</span>
          )}
          {!bounded && <span className="ml-1.5 text-2xs text-muted font-medium">{t('dashboard.noLimit')}</span>}
        </span>
      </div>
      {bounded && <Meter value={meter} variant={variant} className="mt-1.5" />}
    </div>
  );
}

// The user dashboard: a summary of the caller's resources, credits, and GPU availability.
export function Dashboard() {
  const { t } = useTranslation();
  const { data: s } = useDashboardSummary();
  const [newVolOpen, setNewVolOpen] = useState(false);
  const [quotaOpen, setQuotaOpen] = useState(false);
  const { data: sessions } = useSessions();

  const credit = s?.credit ?? { available: null, balance: null, reserved: null };
  const running = s?.sessions?.running ?? 0;
  const active = s?.sessions?.active ?? 0;
  const instLimit = s?.allocation?.instances?.total ?? Math.max(active, 1);
  // MY VRAM vs MY policy limit - distinct from the cluster-wide `vram` above.
  const myVram = s?.allocation?.vram ?? { used_mb: 0, limit_mb: null };
  const gpuCores = (s?.allocation as { gpu_cores?: { used: number; limit: number | null } } | undefined)?.gpu_cores ?? { used: 0, limit: null };
  const compute = s?.compute;
  // The preview answers "what do I have running right now", so it lists the ACTIVE set (the
  // statuses that still hold a slot against the concurrency limit) and leaves finished sessions
  // to the full list.
  const ACTIVE_STATUSES = ['pending', 'preparing', 'running', 'paused', 'terminating'];
  const mySessions = (sessions ?? []).filter((x) => ACTIVE_STATUSES.includes(x.status)).slice(0, 5);
  // Burn rate over MY running sessions — the same figure the wallet page shows, so the two never
  // disagree; the foot answers the question the number raises ("how long do I have left?").
  const burn = sessionBurnPerHour(sessions);
  const runwayHours = burn > 0 && credit.available != null ? credit.available / burn : null;
  const regions = s?.regions ?? [];
  // Node pools the caller may be placed on, in preference order (group-granted, org-granted,
  // shared). Typed locally until the generated schema carries the field.
  const pools = ((s as { pools?: DashboardPool[] } | undefined)?.pools ?? []);

  return (
    <div>
      <PageHeader
        title={t('dashboard.title')}
        description={t('dashboard.subtitle')}
        actions={
          <>
            <button type="button" className="gs-btn" onClick={() => setNewVolOpen(true)}>
              <Database size={15} aria-hidden="true" />
              {t('dashboard.quickDataTitle')}
            </button>
            <Link to="/sessions/new" className="gs-btn gs-btn-primary">
              <Plus size={15} weight="bold" aria-hidden="true" />
              {t('session.new')}
            </Link>
          </>
        }
      />

      <Dialog open={newVolOpen} wide title={t('volume.new')} onClose={() => setNewVolOpen(false)}>
        <NewVolumeForm onDone={() => setNewVolOpen(false)} />
      </Dialog>
      <Dialog open={quotaOpen} title={t('quota.title')} onClose={() => setQuotaOpen(false)}>
        <QuotaRequestForm onDone={() => setQuotaOpen(false)} />
      </Dialog>
      {/* Headline figures. One panel, hairline-divided, so the eye reads left to right instead of
          scanning four competing boxes. */}
      <section className="gs-panel grid md:grid-cols-2 lg:grid-cols-4 mb-5" aria-label={t('dashboard.title')}>
        <Figure
          label={t('dashboard.creditBalance')}
          value={credit.available != null ? formatCredit(credit.available) : '-'}
          unit={t('dashboard.available')}
          bar={{ value: pct(credit.available, credit.balance) }}
        />
        <Figure
          label={t('wallet.burnRate')}
          value={formatCredit(Math.round(burn * 10) / 10)}
          unit="C/h"
          foot={runwayHours != null ? t('wallet.runwayFor', { duration: runwayLabel(runwayHours) }) : t('wallet.noBurn')}
        />
        <Figure
          label={t('dashboard.activeSessions')}
          value={active}
          unit={`/ ${instLimit}`}
          bar={{ value: pct(active, instLimit), variant: 'warn' }}
        />
        <Figure
          label={t('dashboard.runningSessions')}
          value={running}
          unit={t('dashboard.running')}
          bar={{ value: pct(running, instLimit), variant: 'free' }}
        />
      </section>

      {/* Everything the caller is allowed to hold, GPU and host compute together: one policy,
          one place to read it. Three columns because they are three different ceilings — how many
          sessions, how much GPU, how much host compute — and side by side they compare at a glance
          instead of stacking into one long list. */}
      <section className="gs-panel p-5">
        <div className="flex items-center justify-between gap-2">
          <h2 className="gs-h2 inline-flex items-center gap-1.5">{t('dashboard.quota')}<HelpTip text={t('dashboard.computeSubtitle')} /></h2>
          <button type="button" className="text-primary text-xs font-semibold hover:underline" onClick={() => setQuotaOpen(true)}>{t('quota.requestLink')}</button>
        </div>
        <div className="mt-4 grid md:grid-cols-3 gap-x-10 gap-y-6">
          <div className="flex flex-col gap-3.5">
            <div className="gs-quota-band">{t('dashboard.bandSessions')}</div>
            <QuotaRow label={t('dashboard.instances')} used={active} limit={instLimit} unit={t('dashboard.instanceUnit')} variant="warn" />
            <QuotaRow label={t('dashboard.runningLabel')} used={running} limit={instLimit} unit={t('dashboard.instanceUnit')} variant="free" />
          </div>
          <div className="flex flex-col gap-3.5">
            <div className="gs-quota-band">{t('dashboard.bandGpu')}</div>
            <QuotaRow label={t('dashboard.myVram')} used={gb(myVram.used_mb)} limit={myVram.limit_mb ? gb(myVram.limit_mb) : null} unit="GB" variant="primary" />
            <QuotaRow label={t('dashboard.gpuCores')} used={gpuCores.used} limit={gpuCores.limit} unit="%" variant="primary" />
          </div>
          {compute && (
            <div className="flex flex-col gap-3.5">
              <div className="gs-quota-band">{t('dashboard.bandHost')}</div>
              <QuotaRow label="CPU" used={compute.cpu.used} limit={compute.cpu.limit} unit={t('dashboard.coreUnit')} />
              <QuotaRow label={t('dashboard.memLabel')} used={compute.mem_gb.used} limit={compute.mem_gb.limit} unit="GiB" />
              <QuotaRow label={t('dashboard.diskLabel')} used={compute.disk_gb.used} limit={compute.disk_gb.limit} unit="GB" />
            </div>
          )}
        </div>
      </section>

      {/* What is free to run on right now: one card per GPU model, in a row under the quota. */}
      <section className="gs-panel p-5 mt-5">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <h2 className="gs-h2 inline-flex items-center gap-1.5">{t('dashboard.regionAvailability')}<HelpTip text={t('dashboard.availabilityHelp')} /></h2>
          {pools.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5 text-xs" aria-label={t('dashboard.pools.label')}>
              <span className="text-muted">{t('dashboard.pools.label')}</span>
              {pools.map((p) => (
                <span key={p.id ?? 'shared'} className="gs-tag" title={t(`dashboard.pools.tier_${p.tier}`)}>
                  {p.tier === 'shared' && p.id == null ? t('dashboard.pools.shared') : p.name}
                </span>
              ))}
            </div>
          )}
        </div>
        {regions.length === 0 ? (
          <p className="text-muted text-sm py-3">{t('dashboard.noDevices')}</p>
        ) : (
          /* One card per model with a single traffic-light reading. Exact VRAM and idle-card
             counts are operator detail; to a user they read as "the GPU is being watched". */
          <ul className="mt-3 grid grid-cols-[repeat(auto-fill,minmax(320px,1fr))] gap-3">
            {regions.map((r) => {
              const level = congestion(r.free_mb, r.total_mb);
              // Per-card VRAM is a SPEC (helps pick a model), not live state — card counts and
              // exact free GB stay hidden by design.
              const cardGb = r.total > 0 ? Math.round((r.total_mb ?? 0) / r.total / 1024) : 0;
              return (
                <li key={r.model} className="gs-card p-4 flex items-center gap-3">
                  <GraphicsCard size={17} className="shrink-0 text-muted" aria-hidden="true" />
                  <span className="min-w-0 flex-1 truncate font-medium text-sm" title={r.model}>{r.model}</span>
                  {cardGb > 0 && <span className="gs-tag shrink-0 gs-num">{cardGb} GB</span>}
                  <StatusPill kind={level} label={t(`dashboard.congestion.${level}`)} />
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section className="gs-panel p-5 mt-5">
        <div className="flex items-center justify-between gap-3">
          <h2 className="gs-h2">{t('dashboard.mySessions')}</h2>
          <Link to="/sessions" className="text-primary text-xs font-semibold inline-flex items-center gap-1 hover:underline">
            {t('dashboard.viewAll')}
            <ArrowRight size={13} aria-hidden="true" />
          </Link>
        </div>
        {/* A preview of the live few, not the list itself: "See all" is the way to find one,
            which is why the table carries no search box or sort of its own. */}
        {mySessions.length === 0 ? (
          <p className="text-muted text-sm py-3">
            {t('dashboard.noSessions')}{' '}
            <Link to="/sessions/new" className="text-primary font-semibold hover:underline">{t('dashboard.startOne')}</Link>
          </p>
        ) : (
          <table data-preview className="w-full text-sm mt-2" aria-label={t('dashboard.mySessions')}>
            <thead className="text-muted text-xs text-left">
              <tr>
                <th className="py-2 font-semibold">{t('dashboard.colStatus')}</th>
                <th className="font-semibold">{t('dashboard.colName')}</th>
                <th className="font-semibold">{t('dashboard.colResource')}</th>
                <th className="font-semibold">{t('dashboard.colMode')}</th>
              </tr>
            </thead>
            <tbody>
              {mySessions.map((x) => (
                <tr key={x.id} className="border-t border-border">
                  <td className="py-2.5 pr-3">
                    <StatusPill kind={x.status} label={sessionStatusLabel(x.status)} />
                  </td>
                  <td className="pr-3">
                    {/* The name the user typed identifies the session; the id is a copy target. */}
                    <Link to={`/sessions/${x.id}`} className="font-semibold text-primary hover:underline">
                      {x.name || x.id}
                    </Link>
                    <CopyButton value={x.id} label={t('session.copyId')} className="ml-1.5 align-middle" />
                  </td>
                  <td className="pr-3">
                    {x.resource_class === 'gpu'
                      ? (x.gpu_model ?? t('dashboard.gpuGeneric'))
                      : t('dashboard.cpuGeneric')}
                  </td>
                  <td>{x.mode ?? '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}

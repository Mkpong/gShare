import { useTranslation } from 'react-i18next';
import { SelectMenu } from '@/components/SelectMenu';
import { Stack } from '@/components/icons';
import { useClusterSummary } from '@/api/hooks/useClusters';
import { useUiStore } from '@/store/uiStore';

// The cluster the console looks at, next to the sidebar toggle. It filters every list and
// dashboard and becomes the wizard's default (the wizard keeps an "automatic" choice). Shown as
// soon as the platform has a cluster at all, even the single one most installs run: hiding the
// control until a second cluster appears left no way to see which cluster the console is reading,
// and no way to find the switch before it was needed.
//
// Deliberately not shaped like the form selects below it. This does not edit a value on the page —
// it changes what the whole console is looking at, and wearing the same bordered box as a filter
// field said otherwise. A pill with the fleet icon reads as context; the accent fill is state, not
// decoration: it is on exactly while the console is narrowed to one cluster, so "why am I only
// seeing two nodes" has a visible answer in the bar.
export function ClusterSelector() {
  const { t } = useTranslation();
  const { data: clusters = [] } = useClusterSummary();
  const active = useUiStore((s) => s.activeClusterId);
  const set = useUiStore((s) => s.setActiveCluster);
  // Nothing to name while the summary is still loading, or on an install with no cluster yet.
  if (clusters.length === 0) return null;
  const value = active && clusters.some((c) => c.id === active) ? active : '';
  const narrowed = value !== '';
  return (
    <SelectMenu
      value={value}
      onChange={(v) => set(v || null)}
      options={[
        { value: '', label: t('nav.allClusters') },
        ...clusters.map((c) => ({ value: c.id, label: c.name })),
      ]}
      ariaLabel={t('nav.clusterSelector')}
      bare
      leading={
        <Stack
          size={15}
          weight={narrowed ? 'fill' : 'regular'}
          className={narrowed ? 'text-primary' : 'text-muted'}
          aria-hidden="true"
        />
      }
      buttonClassName={`h-8 pl-2.5 pr-2 rounded-full text-sm font-semibold max-w-[13rem]
        border transition-colors duration-150 outline-none
        focus-visible:ring-2 focus-visible:ring-primary/40
        ${narrowed
          ? 'bg-primary-soft border-primary/35 text-text hover:border-primary/60'
          : 'bg-surface-2 border-transparent text-text hover:border-border-strong'}`}
    />
  );
}

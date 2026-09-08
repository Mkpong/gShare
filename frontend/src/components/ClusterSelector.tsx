import { useTranslation } from 'react-i18next';
import { Select } from '@/components/Select';
import { useClusterSummary } from '@/api/hooks/useClusters';
import { useUiStore } from '@/store/uiStore';

// The cluster the console looks at, next to the sidebar toggle. It filters every list and
// dashboard and becomes the wizard's default (the wizard keeps an "automatic" choice). Shown as
// soon as the platform has a cluster at all, even the single one most installs run: hiding the
// control until a second cluster appears left no way to see which cluster the console is reading,
// and no way to find the switch before it was needed.
export function ClusterSelector() {
  const { t } = useTranslation();
  const { data: clusters = [] } = useClusterSummary();
  const active = useUiStore((s) => s.activeClusterId);
  const set = useUiStore((s) => s.setActiveCluster);
  // Nothing to name while the summary is still loading, or on an install with no cluster yet.
  if (clusters.length === 0) return null;
  const value = active && clusters.some((c) => c.id === active) ? active : '';
  return (
    <Select
      className="gs-input w-auto text-sm py-1"
      value={value}
      aria-label={t('nav.clusterSelector')}
      onChange={(e) => set(e.target.value || null)}
    >
      <option value="">{t('nav.allClusters')}</option>
      {clusters.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
    </Select>
  );
}

import { useTranslation } from 'react-i18next';
import { Select } from '@/components/Select';
import { useClusterSummary } from '@/api/hooks/useClusters';
import { useUiStore } from '@/store/uiStore';

// The cluster the console looks at, next to the sidebar toggle. Hidden while the platform has one
// cluster — most installs — so the bar stays as it is; with two or more it filters every list and
// dashboard and becomes the wizard's default (the wizard keeps an "automatic" choice).
export function ClusterSelector() {
  const { t } = useTranslation();
  const { data: clusters = [] } = useClusterSummary();
  const active = useUiStore((s) => s.activeClusterId);
  const set = useUiStore((s) => s.setActiveCluster);
  if (clusters.length < 2) return null;
  const value = active && clusters.some((c) => c.id === active) ? active : '';
  return (
    <Select
      className="gs-input w-auto text-sm py-1"
      data-cluster-selector
      value={value}
      aria-label={t('nav.clusterSelector')}
      onChange={(e) => set(e.target.value || null)}
    >
      <option value="">{t('nav.allClusters')}</option>
      {clusters.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
    </Select>
  );
}

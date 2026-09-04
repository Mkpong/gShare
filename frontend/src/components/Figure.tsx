import { Meter, type MeterVariant } from './Meter';
import { HelpTip } from './HelpTip';

/**
 * One figure in a headline band. The band is a single `gs-panel` divided by hairlines rather
 * than a row of identical cards: four boxes of equal weight say nothing about which number
 * matters. Usage: `<section className="gs-panel grid md:grid-cols-4"><Figure … /></section>`.
 */
export function Figure({ label, value, unit, foot, bar, hero, help }: {
  /** Already-translated annotation above the number. */
  label: string;
  value: string | number;
  unit?: string;
  foot?: string;
  /** Explanatory sentence, shown as a ? tooltip beside the label instead of a foot line —
   *  descriptions belong on demand; the foot stays for DATA (a live figure, a runway). */
  help?: string;
  bar?: { value: number; variant?: MeterVariant };
  /** The one figure the band leads with: same size, accent ink. */
  hero?: boolean;
}) {
  return (
    <div className="min-w-0 px-5 py-4 border-border md:border-l first:md:border-l-0 max-md:border-t max-md:first:border-t-0">
      <div className="text-muted text-xs font-semibold inline-flex items-center gap-1">
        {label}
        {help && <HelpTip text={help} />}
      </div>
      {/* Wraps and steps down below lg: a 7-digit balance in a quarter-width tile overran its
          neighbour at tablet widths. */}
      <div className="mt-2 flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5">
        <span className={`gs-num text-kpi max-lg:text-2xl leading-none tracking-[-0.03em] break-all ${hero ? 'text-primary' : ''}`}>{value}</span>
        {unit && <span className="text-muted text-xs font-semibold">{unit}</span>}
      </div>
      {bar && <Meter value={bar.value} variant={bar.variant} />}
      {foot && <div className="text-muted text-2xs mt-2">{foot}</div>}
    </div>
  );
}

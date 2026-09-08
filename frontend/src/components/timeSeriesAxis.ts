/**
 * Pure axis helpers for TimeSeriesChart: per-unit value formatting, the minimum y span a chart is
 * drawn over, and the gridline labels. They live outside the chart component so they can be tested
 * without a DOM — uPlot reaches for `matchMedia` the moment it is imported.
 */

export function formatValue(v: number | null | undefined, unit: string): string {
  if (v == null || Number.isNaN(v)) return '-';
  switch (unit) {
    case 'percent': return `${v.toFixed(v < 10 ? 1 : 0)}%`;
    case 'cores': return `${v.toFixed(v < 10 ? 2 : 1)}`;
    case 'mib': return v >= 1024 ? `${(v / 1024).toFixed(1)} GiB` : `${v.toFixed(0)} MiB`;
    case 'celsius': return `${v.toFixed(0)}°C`;
    case 'watt': return `${v.toFixed(0)} W`;
    case 'mhz': return `${v.toFixed(0)} MHz`;
    case 'bytes_per_sec': {
      const u = ['B/s', 'KiB/s', 'MiB/s', 'GiB/s'];
      let n = v, i = 0;
      while (n >= 1024 && i < u.length - 1) { n /= 1024; i += 1; }
      return `${n.toFixed(n < 10 ? 1 : 0)} ${u[i]}`;
    }
    default: return v.toFixed(0);
  }
}

/**
 * The smallest y span a zero-anchored chart is drawn over, by unit.
 *
 * uPlot's default is to fit the axis to the data, which magnifies an idle line until noise fills
 * the panel: a session holding a hundredth of a core was drawn as a violent sawtooth, and memory
 * moving within 0.06 MiB as a staircase. Anchoring at zero and keeping at least this much span
 * makes a flat line look flat, which is what is actually happening.
 */
export const MIN_SPAN: Record<string, number> = {
  cores: 0.1,
  percent: 10,
  mib: 64,
  bytes_per_sec: 1024,
  count: 4,
};

/** The y range for a zero-anchored chart: from zero to the data's peak, never narrower than the
 *  unit's minimum span. `max` is whatever uPlot derived from the data. */
export function zeroAnchoredRange(max: number, unit: string): [number, number] {
  const top = Number.isFinite(max) ? Math.max(max, 0) : 0;
  return [0, Math.max(top * 1.15, MIN_SPAN[unit] ?? 1)];
}

/**
 * Axis labels: the precision follows the tick spacing, so a memory line that moves within one
 * mebibyte does not print the same rounded figure on every gridline ("122 MiB" × 4). The decimals
 * come from the spacing itself rather than a fixed cap — capped at two places, an idle CPU axis
 * printed "0.00" on all five gridlines and carried no information at all.
 */
export function formatAxis(vals: number[], unit: string): string[] {
  const step = vals.length > 1 ? Math.abs(vals[1] - vals[0]) : 1;
  const dec = (s: number) =>
    s >= 1 || s <= 0 ? 0 : Math.min(6, Math.max(1, Math.ceil(-Math.log10(s))));
  return vals.map((v) => {
    switch (unit) {
      case 'mib':
        return v >= 1024 || (vals[vals.length - 1] ?? 0) >= 1024
          ? `${(v / 1024).toFixed(dec(step / 1024) || 1)} GiB`
          : `${v.toFixed(dec(step))} MiB`;
      case 'cores': return v.toFixed(dec(step));
      case 'percent': return `${v.toFixed(dec(step))}%`;
      default: return formatValue(v, unit);
    }
  });
}

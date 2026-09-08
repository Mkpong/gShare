import { describe, expect, it } from 'vitest';
import { formatAxis, zeroAnchoredRange } from './timeSeriesAxis';

/**
 * The axis has to say something different on each gridline. An idle session's CPU sits far below
 * one hundredth of a core, and the old two-decimal cap printed "0.00" on every line — five labels
 * carrying no information at all.
 */
describe('formatAxis', () => {
  it('gives every gridline a distinct label when the ticks are tiny', () => {
    const labels = formatAxis([0, 0.002, 0.004, 0.006, 0.008], 'cores');
    expect(new Set(labels).size).toBe(labels.length);
  });

  it('does not spend decimals it does not need', () => {
    expect(formatAxis([0, 25, 50, 75, 100], 'percent')).toEqual(['0%', '25%', '50%', '75%', '100%']);
    expect(formatAxis([0, 1, 2], 'cores')).toEqual(['0', '1', '2']);
  });

  it('keeps a memory line readable when it moves within a mebibyte', () => {
    const labels = formatAxis([144.34, 144.36, 144.38, 144.4], 'mib');
    expect(new Set(labels).size).toBe(labels.length);
    expect(labels[0]).toContain('MiB');
  });
});

describe('zeroAnchoredRange', () => {
  it('starts at zero and keeps a minimum span, so an idle line reads as idle', () => {
    // an idle session: hundredths of a core out of two
    expect(zeroAnchoredRange(0.008, 'cores')).toEqual([0, 0.1]);
    // memory drifting within a mebibyte
    expect(zeroAnchoredRange(144.4, 'mib')).toEqual([0, 144.4 * 1.15]);
  });

  it('leaves room above a real peak', () => {
    const [min, max] = zeroAnchoredRange(80, 'percent');
    expect(min).toBe(0);
    expect(max).toBeGreaterThan(80);
  });

  it('survives a chart with no data', () => {
    expect(zeroAnchoredRange(Number.NaN, 'cores')).toEqual([0, 0.1]);
    expect(zeroAnchoredRange(-5, 'percent')).toEqual([0, 10]);
  });
});

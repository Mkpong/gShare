import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';

export interface UrlFilters<K extends string> {
  values: Record<K, string>;
  set: (name: K, value: string) => void;
  /** True when at least one filter narrows the list — drives the "no results" vs "empty" choice. */
  any: boolean;
  clear: () => void;
}

/**
 * A handful of select-style filters kept in the query string next to the table state (search, sort,
 * page), so a narrowed view survives a reload and travels in a link. Empty string means "all".
 * Changing a filter restarts paging, as a search does.
 */
export function useUrlFilters<K extends string>(names: readonly K[], prefix = ''): UrlFilters<K> {
  const [params, setParams] = useSearchParams();
  const k = (name: string) => (prefix ? `${prefix}_${name}` : name);

  const values = useMemo(() => {
    const out = {} as Record<K, string>;
    for (const n of names) out[n] = params.get(k(n)) ?? '';
    return out;
  }, [params, names]); // eslint-disable-line react-hooks/exhaustive-deps

  const set = useCallback((name: K, value: string) => {
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      if (value) next.set(k(name), value); else next.delete(k(name));
      next.delete(k('page'));
      return next;
    }, { replace: true });
  }, [setParams]); // eslint-disable-line react-hooks/exhaustive-deps

  const clear = useCallback(() => {
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      for (const n of names) next.delete(k(n));
      next.delete(k('page'));
      return next;
    }, { replace: true });
  }, [setParams, names]); // eslint-disable-line react-hooks/exhaustive-deps

  return useMemo(() => ({
    values, set, clear,
    any: names.some((n) => !!values[n]),
  }), [values, set, clear, names]);
}

/** Distinct, non-empty values of a field, sorted — the option list a filter offers is what the data holds. */
export function distinct<T>(rows: T[], pick: (row: T) => string | null | undefined): string[] {
  return [...new Set(rows.map(pick).filter((v): v is string => !!v))].sort();
}

/** Distinct id/label pairs, sorted by label — for filters whose value is an id but whose face is a name. */
export function distinctPairs<T>(
  rows: T[], id: (row: T) => string | null | undefined, label: (row: T) => string | null | undefined,
): { value: string; label: string }[] {
  const m = new Map<string, string>();
  for (const r of rows) { const v = id(r); if (v && !m.has(v)) m.set(v, label(r) || v); }
  return [...m].map(([value, label]) => ({ value, label })).sort((a, b) => a.label.localeCompare(b.label));
}

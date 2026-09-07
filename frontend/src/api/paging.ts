import { api } from '@/api/client';

/** The server's cap. `Pagination` in the backend defaults to 20 rows and refuses more than 100. */
export const PAGE_MAX = 100;

/**
 * Append every page after the first.
 *
 * The API returns 20 rows unless asked otherwise, so a screen that filters, sorts, counts or pages
 * client-side has to hold the whole collection — otherwise its own "N건" total is really "the first
 * page", and rows beyond it do not exist as far as that screen is concerned. That is not
 * hypothetical: the session monitor showed 20 of 43 sessions, and a running session was missing
 * from the list yet appeared the moment a filter narrowed the result below one page.
 *
 * Callers fetch page 1 themselves (which keeps the generated response types) and hand the rows and
 * the reported total here; the element type is carried through unchanged.
 */
export async function fetchRestOfPages<T>(
  path: string,
  query: Record<string, unknown>,
  first: T[],
  total: number | undefined,
  maxPages = 20,
): Promise<T[]> {
  if (total == null || first.length >= total || first.length < PAGE_MAX) return first;
  const client = api as unknown as {
    GET: (p: string, o?: { params?: { query?: Record<string, unknown> } }) => Promise<{ data?: unknown }>;
  };
  const out = [...first];
  for (let page = 2; page <= maxPages; page += 1) {
    const { data } = await client.GET(path, { params: { query: { ...query, page, size: PAGE_MAX } } });
    const env = data as { data?: T[] } | T[] | undefined;
    const rows = Array.isArray(env) ? env : env?.data ?? [];
    out.push(...rows);
    if (rows.length < PAGE_MAX || out.length >= total) break;
  }
  return out;
}

/** The `total` a paginated envelope reports, when it carries one. */
export function pageTotal(data: unknown): number | undefined {
  const env = data as { pagination?: { total?: number } } | undefined;
  return env?.pagination?.total;
}

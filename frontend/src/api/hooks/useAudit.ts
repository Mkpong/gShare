import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import { useAuthStore } from '@/auth/authStore';

// The audit log viewer, with filters and pagination.
// The response envelope is { data, pagination }, sorted by created_at descending.

export interface AuditFilter {
  actor_id?: string;
  actor_q?: string;   // search by actor name or email
  action?: string;
  target?: string;
  'at[gte]'?: string;
  'at[lt]'?: string;
  page?: number;
  size?: number;
  sort?: string;
}

export const auditKeys = {
  all: ['audit-logs'] as const,
  list: (f: AuditFilter) => ['audit-logs', 'list', f] as const,
};

// GET /audit-logs — audit events across permissions, credits, sessions, and policy.
export function useAuditLogs(filter: AuditFilter = {}) {
  return useQuery({
    queryKey: auditKeys.list(filter),
    queryFn: async () => {
      const { data } = await api.GET('/api/v1/audit-logs', { params: { query: filter } });
      return data ?? { data: [], pagination: { page: 1, size: 20, total: 0, total_pages: 0 } };
    },
    placeholderData: (prev) => prev, // keeps the table from flashing between pages
  });
}

// GET /audit-logs/export — the current view as a CSV file. A bearer-authenticated fetch (no cookie
// session exists to lean on for a plain link), handed to the browser as a download.
export async function exportAuditCsv(filter: AuditFilter): Promise<void> {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(filter)) {
    if (v == null || v === '' || k === 'page' || k === 'size' || k === 'sort') continue;
    q.set(k, String(v));
  }
  const { accessToken, activeProjectId } = useAuthStore.getState();
  const headers: Record<string, string> = {};
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  if (activeProjectId) headers['X-Project-Id'] = activeProjectId;
  const res = await fetch(`/api/v1/audit-logs/export?${q.toString()}`, { headers });
  if (!res.ok) throw new Error(`export failed (${res.status})`);
  const blob = await res.blob();
  const name = /filename="([^"]+)"/.exec(res.headers.get('content-disposition') ?? '')?.[1]
    ?? `gshare-audit-${new Date().toISOString().slice(0, 10)}.csv`;
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = name; a.click();
  URL.revokeObjectURL(url);
}

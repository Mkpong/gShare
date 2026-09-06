import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';

// Instance-wide system settings. Branding is the only section today; the shape (one query per
// section, one mutation per section) is what a later section slots into.
const raw = api as unknown as {
  GET: (p: string) => Promise<{ data?: unknown }>;
  PUT: (p: string, o?: { body?: unknown }) => Promise<{ data?: unknown; error?: unknown }>;
};

export interface Branding {
  service_name: string;
  /** data: URI of an uploaded logo, or null when the generated letter mark is used. */
  logo?: string | null;
}

export const DEFAULT_SERVICE_NAME = 'gShare';

const keys = { branding: ['system', 'branding'] as const };

/** Readable signed out — the sign-in screen renders the name before anyone has a token. */
export function useBranding() {
  return useQuery({
    queryKey: keys.branding,
    queryFn: async () => (await raw.GET('/api/v1/system/branding')).data as Branding,
    staleTime: 5 * 60_000,
    // Branding rarely changes and a failure must never blank the wordmark.
    placeholderData: { service_name: DEFAULT_SERVICE_NAME, logo: null } as Branding,
  });
}

export function useSetBranding() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { service_name?: string; logo?: string; clear_logo?: boolean }) => {
      const { data, error } = await raw.PUT('/api/v1/system/branding', { body });
      if (error) throw error;
      return data as Branding;
    },
    onSuccess: (data) => { qc.setQueryData(keys.branding, data); },
  });
}

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';

// Instance-wide system settings. Branding is the only section today; the shape (one query per
// section, one mutation per section) is what a later section slots into.
const raw = api as unknown as {
  GET: (p: string) => Promise<{ data?: unknown }>;
  POST: (p: string, o?: { body?: unknown }) => Promise<{ data?: unknown; error?: unknown }>;
  PUT: (p: string, o?: { body?: unknown }) => Promise<{ data?: unknown; error?: unknown }>;
};

export interface Branding {
  service_name: string;
  /** data: URI of an uploaded logo, or null when the generated letter mark is used. */
  logo?: string | null;
}

export const DEFAULT_SERVICE_NAME = 'gShare';

// Branding is fetched, so the first frame would otherwise show the default name and mark and then
// swap — a visible flash on every load. The last answer is kept in the browser and used as the
// starting value; the fetch corrects it if an administrator changed it meanwhile.
const CACHE_KEY = 'gshare.branding';

export function cachedBranding(): Branding {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (raw) {
      const b = JSON.parse(raw) as Branding;
      if (typeof b?.service_name === 'string' && b.service_name) return b;
    }
  } catch {
    // Private mode, blocked storage, corrupt value: fall through to the default.
  }
  return { service_name: DEFAULT_SERVICE_NAME, logo: null };
}

function rememberBranding(b: Branding): void {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(b));
  } catch { /* nothing to do: the cache is an optimisation, not state */ }
}

export type SignupMode = 'approval' | 'open' | 'closed';

export interface SignupPolicy {
  mode: SignupMode;
  allowed_domains: string[];
}

const keys = {
  branding: ['system', 'branding'] as const,
  signup: ['system', 'signup'] as const, placement: ['system', 'placement'] as const };

/** Readable signed out — the sign-in screen renders the name before anyone has a token. */
export function useBranding() {
  return useQuery({
    queryKey: keys.branding,
    queryFn: async () => {
      const b = (await raw.GET('/api/v1/system/branding')).data as Branding;
      rememberBranding(b);
      return b;
    },
    staleTime: 5 * 60_000,
    // The last known branding, so the wordmark is right on the first frame; a failure leaves it
    // standing rather than blanking it.
    placeholderData: cachedBranding(),
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
    onSuccess: (data) => { rememberBranding(data); qc.setQueryData(keys.branding, data); },
  });
}

/** Readable signed out: the sign-in screen offers its sign-up tab only when this is not closed. */
export function useSignupPolicy() {
  return useQuery({
    queryKey: keys.signup,
    queryFn: async () => (await raw.GET('/api/v1/system/signup')).data as SignupPolicy,
    staleTime: 5 * 60_000,
    placeholderData: { mode: 'closed', allowed_domains: [] } as SignupPolicy,
  });
}

export function useSetSignupPolicy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { mode?: SignupMode; allowed_domains?: string[] }) => {
      const { data, error } = await raw.PUT('/api/v1/system/signup', { body });
      if (error) throw error;
      return data as SignupPolicy;
    },
    onSuccess: (data) => { qc.setQueryData(keys.signup, data); },
  });
}

/** Self-service registration. Resolves with the new account's status. */
export function useSignup() {
  return useMutation({
    mutationFn: async (body: { email: string; name: string; password: string }) => {
      const { data, error } = await raw.POST('/api/v1/auth/signup', { body });
      if (error) throw error;
      return data as { status: 'pending' | 'active' };
    },
  });
}

export type GpuPacking = 'binpack' | 'spread';
export interface Placement { gpu_packing: GpuPacking }

/** Where a fractional slice lands when several cards fit. Was deploy-time only until now. */
export function usePlacement() {
  return useQuery({
    queryKey: keys.placement,
    queryFn: async () => (await raw.GET('/api/v1/system/placement')).data as Placement,
    staleTime: 60_000,
  });
}

export function useSetPlacement() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { gpu_packing: GpuPacking }) => {
      const { data, error } = await raw.PUT('/api/v1/system/placement', { body });
      if (error) throw error;
      return data as Placement;
    },
    onSuccess: (data) => { qc.setQueryData(keys.placement, data); },
  });
}

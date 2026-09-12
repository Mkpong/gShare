import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, idemKey } from '@/api/client';

// Storage pools: the registered storage servers that back user volumes — one per (cluster,
// StorageClass). The capacity gate on volume creation and the dashboard's storage tile read these
// rows, never the node inventory, so a server only counts once an administrator has registered
// it. These endpoints use the loose accessor and type their envelopes locally.
const raw = api as unknown as {
  GET: (path: string, init?: { params?: { query?: Record<string, unknown> } }) => Promise<{ data?: unknown }>;
  POST: (path: string, init?: { body?: unknown; headers?: Record<string, string> }) => Promise<{ data?: unknown }>;
  PATCH: (path: string, init?: { body?: unknown; params?: { path?: Record<string, string> }; headers?: Record<string, string> }) => Promise<{ data?: unknown }>;
  DELETE: (path: string, init?: { params?: { path?: Record<string, string> }; headers?: Record<string, string> }) => Promise<{ data?: unknown }>;
};

export type PoolShareScope = 'all' | 'selected';
/** Where the capacity figure came from, best source first: the CSI driver, the stated figure, the node's disk. */
export type PoolCapacitySource = 'csi' | 'manual' | 'node_disk' | null;

export interface StoragePool {
  id: string;
  name: string;
  cluster_id: string;
  cluster_name?: string | null;
  node_id?: string | null;
  node_hostname?: string | null;
  storage_class: string;
  share_scope: PoolShareScope;
  shared_with: string[];
  shared_with_names: string[];
  capacity_gb?: number | null;
  capacity_source?: PoolCapacitySource;
  capacity_reported_at?: string | null;
  manual_capacity_gb?: number | null;
  created_at?: string | null;
}

export interface StoragePoolCreateBody {
  name: string;
  cluster_id: string;
  storage_class: string;
  node_id?: string | null;
  share_scope: PoolShareScope;
  shared_with?: string[];
  manual_capacity_gb?: number | null;
}

export type StoragePoolPatchBody = Partial<Omit<StoragePoolCreateBody, 'cluster_id'>>;

export const storagePoolKeys = {
  all: ['storage-pools'] as const,
  list: (clusterId?: string) => ['storage-pools', clusterId ?? 'all'] as const,
};

// GET /storage/pools — every registered pool (super_admin). The list is small (one row per storage
// server), so it is fetched whole.
export function useStoragePools(clusterId?: string, opts?: { enabled?: boolean }) {
  const query: Record<string, unknown> = {};
  if (clusterId) query.cluster_id = clusterId;
  return useQuery({
    queryKey: storagePoolKeys.list(clusterId),
    enabled: opts?.enabled ?? true,
    queryFn: async () => {
      const { data } = await raw.GET('/api/v1/storage/pools', { params: { query } });
      return (data as { data?: StoragePool[] } | undefined)?.data ?? [];
    },
  });
}

// Registering, editing or removing a pool changes what the dashboard's storage tile and the volume
// capacity gate see, so those caches are invalidated alongside the pool list.
function useInvalidatePools() {
  const qc = useQueryClient();
  return () => Promise.all([
    qc.invalidateQueries({ queryKey: storagePoolKeys.all }),
    qc.invalidateQueries({ queryKey: ['metrics', 'cluster'] }),
    qc.invalidateQueries({ queryKey: ['volumes'] }),
  ]);
}

// POST /storage/pools — register a storage server. Idempotency key required.
export function useCreateStoragePool() {
  const invalidate = useInvalidatePools();
  return useMutation({
    mutationFn: async (body: StoragePoolCreateBody) => {
      const { data } = await raw.POST('/api/v1/storage/pools', { body, headers: { 'Idempotency-Key': idemKey() } });
      return data as StoragePool;
    },
    onSuccess: () => invalidate(),
  });
}

// PATCH /storage/pools/{id} — rename, move the node link, change the class, sharing or the stated
// capacity. The cluster itself cannot change: a pool belongs to the cluster its server sits in.
export function useUpdateStoragePool() {
  const invalidate = useInvalidatePools();
  return useMutation({
    mutationFn: async ({ id, body }: { id: string; body: StoragePoolPatchBody }) => {
      const { data } = await raw.PATCH('/api/v1/storage/pools/{pool_id}', {
        params: { path: { pool_id: id } }, body, headers: { 'Idempotency-Key': idemKey() },
      });
      return data as StoragePool;
    },
    onSuccess: () => invalidate(),
  });
}

// DELETE /storage/pools/{id} — stop counting the pool. Volumes already on it keep working through
// their StorageClass; only the capacity gate and the dashboard forget the server.
export function useDeleteStoragePool() {
  const invalidate = useInvalidatePools();
  return useMutation({
    mutationFn: async (id: string) => {
      await raw.DELETE('/api/v1/storage/pools/{pool_id}', { params: { path: { pool_id: id } }, headers: { 'Idempotency-Key': idemKey() } });
    },
    onSuccess: () => invalidate(),
  });
}

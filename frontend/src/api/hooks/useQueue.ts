import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';

// Poll the caller's queue every 5 seconds. `clusterId` narrows it the way the top bar narrows
// every other list; positions stay global, because the queue is.
export function useQueue(clusterId?: string) {
  return useQuery({
    queryKey: ['queue', 'mine', clusterId ?? ''],
    queryFn: async () => {
      const { data } = await api.GET('/api/v1/queue/mine', {
        params: { query: clusterId ? { cluster_id: clusterId } : {} },
      });
      return data?.data ?? [];
    },
    refetchInterval: 5000,
  });
}

// DELETE /queue/{id} — leave the queue, releasing the credit hold.
export function useCancelQueueEntry() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (entryId: string) => {
      await api.DELETE('/api/v1/queue/{queue_entry_id}', {
        params: { path: { queue_entry_id: entryId } },
      });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['queue', 'mine'] }),
  });
}

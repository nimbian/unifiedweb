import { useQuery } from '@tanstack/react-query';
import { progressApi } from '@/api/progress';

export function useProgress(did: number | string) {
  return useQuery({
    queryKey: ['progress', String(did)],
    queryFn: () => progressApi.get(did),
    enabled: did !== undefined && did !== '',
  });
}

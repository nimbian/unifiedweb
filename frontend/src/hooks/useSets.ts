import { useQuery } from '@tanstack/react-query';
import { setsApi } from '@/api/sets';

export function useSidebar() {
  return useQuery({
    queryKey: ['sets', 'sidebar'],
    queryFn: setsApi.sidebar,
    staleTime: 5 * 60 * 1000, // tab lists rarely change
  });
}

export function useSetView(did: number | string, slug: string | null) {
  return useQuery({
    queryKey: ['set', String(did), slug],
    queryFn: () => setsApi.setView(did, slug as string),
    enabled: Boolean(did) && Boolean(slug),
  });
}

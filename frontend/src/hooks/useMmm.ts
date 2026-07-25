import { useQuery } from '@tanstack/react-query';
import { mmmApi } from '@/api/mmm';

// The badge catalog is effectively static — cache it hard.
export function useMmmBadges() {
  return useQuery({
    queryKey: ['mmm', 'badges'],
    queryFn: mmmApi.badges,
    staleTime: Infinity,
  });
}

export function useMmmDonors() {
  return useQuery({
    queryKey: ['mmm', 'donors'],
    queryFn: mmmApi.donors,
    staleTime: 60 * 1000,
  });
}

export function useMmmDonor(name: string) {
  return useQuery({
    queryKey: ['mmm', 'donor', name.toLowerCase()],
    queryFn: () => mmmApi.donor(name),
    enabled: name.length > 0,
    retry: false, // a missing donor is a 404, not a transient error
  });
}

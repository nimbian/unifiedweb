import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { usersApi } from '@/api/users';

export function useUsers() {
  return useQuery({
    queryKey: ['users'],
    queryFn: usersApi.list,
  });
}

export function useUserProfile(did: number | string) {
  return useQuery({
    queryKey: ['user', String(did)],
    queryFn: () => usersApi.profile(did),
    enabled: did !== undefined && did !== '',
  });
}

// The roles the signed-in user can pick (their completed sets).
export function useMyRoles(enabled = true) {
  return useQuery({
    queryKey: ['me', 'roles'],
    queryFn: usersApi.myRoles,
    enabled,
    staleTime: 5 * 60 * 1000,
  });
}

// Set/clear the caller's role. Refreshes the profile so the displayed role updates.
export function useSetRole(did: number | string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (roleid: number | null) => usersApi.setRole(roleid),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['user', String(did)] });
    },
  });
}

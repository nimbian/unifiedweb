import { apiClient } from './client';
import type { RoleOption, RoleResult, UserProfile, UserSummary } from '@/types';

export const usersApi = {
  list: async (): Promise<UserSummary[]> => {
    const { data } = await apiClient.get<UserSummary[]>('/users');
    return data;
  },

  profile: async (did: number | string): Promise<UserProfile> => {
    const { data } = await apiClient.get<UserProfile>(`/users/${did}`);
    return data;
  },

  // The roles the signed-in caller may choose from (their completed sets).
  myRoles: async (): Promise<RoleOption[]> => {
    const { data } = await apiClient.get<RoleOption[]>('/me/roles');
    return data;
  },

  // Set (rwid) or clear (null) the caller's displayed role.
  setRole: async (roleid: number | null): Promise<RoleResult> => {
    const { data } = await apiClient.put<RoleResult>('/me/role', { roleid });
    return data;
  },
};

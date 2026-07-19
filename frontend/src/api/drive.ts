import { apiClient } from './client';
import type { DriveImage } from '@/types';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api';

export const driveApi = {
  images: async (): Promise<DriveImage[]> => {
    const { data } = await apiClient.get<DriveImage[]>('/drive/images');
    return data;
  },

  // Direct URL for <img src>; the backend streams the bytes.
  imageUrl: (fileId: string): string => `${BASE_URL}/drive/image/${fileId}`,
};

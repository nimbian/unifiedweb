import { useQuery } from '@tanstack/react-query';
import { driveApi } from '@/api/drive';

export function useDriveImages() {
  return useQuery({
    queryKey: ['drive', 'images'],
    queryFn: driveApi.images,
  });
}

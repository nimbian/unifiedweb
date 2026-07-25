import type { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { Center, Loader } from '@mantine/core';
import { useAuth } from '@/hooks/useAuth';

// Gate a route behind portal-admin access (the backend enforces it too, via the
// admin_discord_ids allowlist). Signed-out users go to /login; signed-in
// non-admins are bounced back to the public MMM wall.
export function AdminRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading, user } = useAuth();

  if (isLoading) {
    return (
      <Center h="60vh">
        <Loader />
      </Center>
    );
  }
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  if (!user?.is_admin) {
    return <Navigate to="/mmm" replace />;
  }
  return <>{children}</>;
}

import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { Center, Loader } from '@mantine/core';
import { useAuth } from '@/hooks/useAuth';

// Replaces Flask's @login_required: gate a route behind authentication.
export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <Center h="60vh">
        <Loader />
      </Center>
    );
  }
  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }
  return <>{children}</>;
}

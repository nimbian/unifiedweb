// Active/Inactive pill — a user is active if their most recent card is < 1 month
// old. Shared by the All Users and Search tables.

import { Badge } from '@mantine/core';
import { isActive } from '@/utils/format';

export function ActivePill({ lastActive }: { lastActive: string | null }) {
  const active = isActive(lastActive);
  return (
    <Badge color={active ? 'green' : 'gray'} variant="light">
      {active ? 'Active' : 'Inactive'}
    </Badge>
  );
}

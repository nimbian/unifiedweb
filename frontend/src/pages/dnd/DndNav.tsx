// Secondary navigation shared by every DnD-adventure page.

import { Tabs, Title } from '@mantine/core';
import { IconSword } from '@tabler/icons-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';

const TABS = [
  { value: '/dnd', label: 'Adventurers' },
  { value: '/dnd/leaderboard', label: 'Leaderboard' },
  { value: '/dnd/worldboss', label: 'World Boss' },
  { value: '/dnd/achievements', label: 'Achievements' },
];

export function DndNav() {
  const loc = useLocation();
  const navigate = useNavigate();
  const { user } = useAuth();
  // "My DnD Adventure" is only meaningful (and routable) when logged in.
  const tabs = user ? [...TABS, { value: '/dnd/mine', label: 'My DnD Adventure' }] : TABS;
  // The non-root tabs win by prefix (so a character sheet keeps "Adventurers" lit).
  const active = tabs.slice(1).find((t) => loc.pathname.startsWith(t.value))?.value ?? '/dnd';

  return (
    <>
      <Title order={2} mb="sm">
        <IconSword size={26} style={{ verticalAlign: 'text-bottom', marginRight: 8 }} />
        DnD Adventure
      </Title>
      <Tabs value={active} onChange={(v) => v && navigate(v)} mb="lg">
        <Tabs.List>
          {tabs.map((t) => (
            <Tabs.Tab key={t.value} value={t.value}>
              {t.label}
            </Tabs.Tab>
          ))}
        </Tabs.List>
      </Tabs>
    </>
  );
}

// Mantine colour for an item/gear rarity.
export function rarityColor(rarity: string | null | undefined): string {
  switch (rarity) {
    case 'legendary':
      return 'orange';
    case 'epic':
      return 'grape';
    case 'rare':
      return 'blue';
    case 'uncommon':
      return 'teal';
    default:
      return 'gray';
  }
}

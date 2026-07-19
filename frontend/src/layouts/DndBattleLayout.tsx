// AppShell layout for the DnD Battle (arena) section of the portal. Mirrors the
// Satchemon MainLayout but with its own branding and nav. Read pages (Arena,
// Leaderboard, Hall of Fame) are public; authed pages (roster/shop) come later.

import { AppShell, Box, Burger, Button, Group, NavLink, Text, Tooltip } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconCrown, IconLogin, IconLogout, IconSwords, IconTrophy } from '@tabler/icons-react';
import { NavLink as RouterNavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';

const NAV = [
  { to: '/dndbattle', label: 'Live Arena', icon: IconSwords, end: true },
  { to: '/dndbattle/leaderboard', label: 'Leaderboard', icon: IconTrophy, end: false },
  { to: '/dndbattle/hof', label: 'Hall of Fame', icon: IconCrown, end: false },
];

export function DndBattleLayout() {
  const [opened, { toggle }] = useDisclosure();
  const { isAuthenticated, user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <AppShell
      header={{ height: 60 }}
      navbar={{ width: 240, breakpoint: 'sm', collapsed: { mobile: !opened } }}
      padding="md"
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group wrap="nowrap" gap="xs">
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" />
            <Tooltip label="Back to MooreDnD home">
              <Text
                fw={800}
                c="grape.5"
                size="lg"
                style={{ letterSpacing: '0.05em', cursor: 'pointer' }}
                onClick={() => navigate('/')}
              >
                DND BATTLE
              </Text>
            </Tooltip>
          </Group>
          <Group wrap="nowrap" gap="xs">
            {isAuthenticated ? (
              <>
                <Text size="sm" c="dimmed" visibleFrom="xs">
                  {user?.name ?? user?.did}
                </Text>
                <Tooltip label="Sign out">
                  <Button
                    variant="subtle"
                    color="gray"
                    leftSection={<IconLogout size={16} />}
                    onClick={() => logout()}
                  >
                    Sign out
                  </Button>
                </Tooltip>
              </>
            ) : (
              <Button
                color="grape"
                leftSection={<IconLogin size={16} />}
                onClick={() => navigate('/login')}
              >
                <Box component="span">Sign in</Box>
              </Button>
            )}
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="md">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            component={RouterNavLink}
            to={to}
            end={end}
            label={label}
            leftSection={<Icon size={18} />}
          />
        ))}
      </AppShell.Navbar>

      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}

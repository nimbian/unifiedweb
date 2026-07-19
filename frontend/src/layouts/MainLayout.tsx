// AppShell layout — replaces the legacy base.j2 topnav.
//
// Header with brand + sign-in/out; Navbar with the primary links (All users,
// Search, My Cards). The Slideshow page is intentionally not linked here — it
// stays reachable only by navigating directly to /slideshow. Responsive: the
// navbar collapses to a burger on mobile.

import { AppShell, Box, Burger, Button, Group, NavLink, Text, Tooltip } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import {
  IconCards,
  IconChartBar,
  IconLogin,
  IconLogout,
  IconSearch,
  IconShoppingCart,
  IconSword,
  IconTrophy,
  IconUser,
  IconUsers,
} from '@tabler/icons-react';
import { NavLink as RouterNavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';
import { useUserProfile } from '@/hooks/useUsers';
import { formatValue } from '@/utils/format';

const NAV = [
  { to: '/satchemon', label: 'All Users', icon: IconUsers, end: true },
  { to: '/search', label: 'Search', icon: IconSearch, end: false },
  { to: '/leaderboard', label: 'Leaderboard', icon: IconTrophy, end: false },
  // The "shop" is the system user's collection (uid 0) — cards sold back to it.
  { to: '/shop', label: 'Shop', icon: IconShoppingCart, end: false },
  { to: '/dnd', label: 'DnD Adventure', icon: IconSword, end: false },
];

export function MainLayout() {
  const [opened, { toggle }] = useDisclosure();
  const { isAuthenticated, user, logout } = useAuth();
  const navigate = useNavigate();
  // Live GP for the signed-in user (buy/sell invalidate ['user', did], so it stays current).
  const { data: profile } = useUserProfile(isAuthenticated ? (user?.did ?? '') : '');

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
                c="red.5"
                size="lg"
                style={{ letterSpacing: '0.05em', cursor: 'pointer' }}
                onClick={() => navigate('/')}
              >
                SATCHEMON
              </Text>
            </Tooltip>
          </Group>
          <Group wrap="nowrap" gap="xs">
            {isAuthenticated ? (
              <>
                <Text size="sm" c="dimmed" visibleFrom="xs">
                  {profile && (
                    <Text component="span" c="yellow.5" fw={600} mr={6}>
                      {formatValue(profile.gp, 0)} GP
                    </Text>
                  )}
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
              <Button leftSection={<IconLogin size={16} />} onClick={() => navigate('/login')}>
                {/* Full label on wider screens; short label on phones so it sits
                    next to the title instead of wrapping below it. */}
                <Box component="span" visibleFrom="xs">
                  Sign in
                </Box>
                <Box component="span" hiddenFrom="xs">
                  Sign in
                </Box>
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
        {isAuthenticated && (
          <>
            <NavLink
              label="My Cards"
              leftSection={<IconCards size={18} />}
              onClick={() => navigate(`/user/${user?.did}`)}
            />
            <NavLink
              label="My Progress"
              leftSection={<IconChartBar size={18} />}
              onClick={() => navigate(`/user/${user?.did}/progress`)}
            />
            <NavLink
              label="Account"
              leftSection={<IconUser size={18} />}
              onClick={() => navigate('/account')}
            />
          </>
        )}
      </AppShell.Navbar>

      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}

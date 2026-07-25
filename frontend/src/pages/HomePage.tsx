// MooreDnD portal homepage.
//
// The umbrella landing for the community: two big tiles routing users to the two
// games — Satchemon (the TCG) and DnD Battle (the Twitch arena). DnD Adventure
// lives *under* Satchemon (its progress pages), so it is not a separate tile.
//
// Both games are now ported in-app (Phase 2), so both tiles navigate internally.
// (The external-link glyph + VITE_*_URL fallback remain in case a tile is pointed
// back out at a standalone site during a transition.)

import {
  Anchor,
  Badge,
  Box,
  Button,
  Card,
  Center,
  Group,
  Image,
  SimpleGrid,
  Stack,
  Text,
  ThemeIcon,
  Title,
  Tooltip,
} from '@mantine/core';
import { IconCards, IconExternalLink, IconSwords } from '@tabler/icons-react';
import { Link } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';
import { useMmmBadges, useMmmDonors } from '@/hooks/useMmm';
import { badgeIcon, formatPoints, ordinal } from '@/pages/mmm/mmmShared';

interface Tile {
  title: string;
  tagline: string;
  description: string;
  to?: string;    // internal SPA route (in-app pages)
  href?: string;  // external URL (page not yet ported)
  color: string;
  icon: typeof IconCards;
}

const TILES: Tile[] = [
  {
    title: 'Satchemon',
    tagline: 'The trading-card game',
    description:
      'Collect, grade and trade cards, track set completion, and follow your DnD Adventure progress.',
    to: '/satchemon',
    color: 'red',
    icon: IconCards,
  },
  {
    title: 'DnD Battle',
    tagline: 'The Twitch arena',
    description:
      'Watch the live arena, climb the leaderboards, and visit the Hall of Fame.',
    to: '/dndbattle',
    color: 'grape',
    icon: IconSwords,
  },
];

function TileBody({ tile }: { tile: Tile }) {
  const { icon: TileIcon } = tile;
  return (
    <Stack gap="md" h="100%">
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <ThemeIcon size={56} radius="md" variant="light" color={tile.color}>
          <TileIcon size={32} />
        </ThemeIcon>
        {tile.href && <IconExternalLink size={18} opacity={0.5} />}
      </Group>
      <Box>
        <Title order={2}>{tile.title}</Title>
        <Text c={`${tile.color}.5`} fw={600} size="sm">
          {tile.tagline}
        </Text>
      </Box>
      <Text c="dimmed" size="sm">
        {tile.description}
      </Text>
    </Stack>
  );
}

function GameTile({ tile }: { tile: Tile }) {
  // Internal tiles use the router (client-side nav); external ones a plain anchor.
  if (tile.to) {
    return (
      <Card component={Link} to={tile.to} withBorder radius="lg" padding="xl" shadow="sm" style={{ height: '100%' }}>
        <TileBody tile={tile} />
      </Card>
    );
  }
  return (
    <Card component="a" href={tile.href} withBorder radius="lg" padding="xl" shadow="sm" style={{ height: '100%' }}>
      <TileBody tile={tile} />
    </Card>
  );
}

// Medal colours for the top-3 supporters (gold/silver/bronze).
const RANK_COLORS = ['yellow', 'gray', 'orange'];

// Compact Midweek Monster Mash supporter teaser: the badge tiers + the top few
// supporters, linking through to the full /mmm wall. Renders nothing until the
// badge catalog is ready so the landing page stays clean.
function HomeSupporters() {
  const { data: badges } = useMmmBadges();
  const { data: donors } = useMmmDonors();
  if (!badges || badges.length === 0) return null;
  const top = (donors ?? []).slice(0, 5);

  return (
    <Card withBorder radius="lg" p="lg" shadow="sm" w="100%">
      <Group justify="space-between" wrap="nowrap" mb="sm">
        <Box>
          <Title order={3}>Midweek Monster Mash</Title>
          <Text c="dimmed" size="sm">
            Supporter badge wall
          </Text>
        </Box>
        <Anchor component={Link} to="/mmm" fw={600} size="sm">
          View all →
        </Anchor>
      </Group>

      <Group gap="xs" justify="center" mb={top.length ? 'md' : 0} wrap="wrap">
        {badges.map((tier) => (
          <Tooltip key={tier.key} label={`${tier.title} · ${formatPoints(tier.points)} pts`} withArrow>
            <Image src={badgeIcon(tier.key)} alt={tier.title} w={40} h={40} loading="lazy" />
          </Tooltip>
        ))}
      </Group>

      {top.length > 0 ? (
        <Stack gap={6}>
          {top.map((d) => (
            <Group key={d.name} justify="space-between" wrap="nowrap">
              <Group gap="xs" wrap="nowrap">
                <Badge
                  color={RANK_COLORS[d.rank - 1] ?? 'blue'}
                  variant="light"
                  w={44}
                  style={{ justifyContent: 'center' }}
                >
                  {ordinal(d.rank)}
                </Badge>
                <Anchor component={Link} to={`/mmm/donor/${encodeURIComponent(d.name)}`} size="sm">
                  {d.name}
                </Anchor>
              </Group>
              <Text size="sm" c="dimmed">
                {formatPoints(d.points)} pts
              </Text>
            </Group>
          ))}
        </Stack>
      ) : (
        <Text c="dimmed" size="sm" ta="center">
          Support the stream to claim your first badge.
        </Text>
      )}
    </Card>
  );
}

function HomeHeader() {
  const { isAuthenticated, user, logout } = useAuth();
  return (
    <Box style={{ position: 'absolute', top: 16, right: 16 }}>
      {isAuthenticated ? (
        <Group gap="xs" wrap="nowrap">
          <Text size="sm" c="dimmed" visibleFrom="xs">
            {user?.name ?? user?.did ?? 'Signed in'}
          </Text>
          <Button variant="subtle" size="compact-sm" component={Link} to="/account">
            Account
          </Button>
          <Button variant="light" color="gray" size="compact-sm" onClick={() => logout()}>
            Sign out
          </Button>
        </Group>
      ) : (
        <Button size="compact-sm" component={Link} to="/login">
          Sign in
        </Button>
      )}
    </Box>
  );
}

export function HomePage() {
  return (
    <Center mih="100vh" p="md">
      <HomeHeader />
      <Stack align="center" gap="xl" w="100%" maw={760}>
        <Stack align="center" gap={4}>
          <Title
            order={1}
            size="3rem"
            fw={800}
            style={{ letterSpacing: '0.02em' }}
            ta="center"
          >
            Moore
            <Text component="span" inherit c="red.5">
              DnD
            </Text>
          </Title>
          <Text c="dimmed" ta="center">
            One sign-in for the whole community. Pick a game to jump in.
          </Text>
        </Stack>

        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="lg" w="100%">
          {TILES.map((tile) => (
            <GameTile key={tile.title} tile={tile} />
          ))}
        </SimpleGrid>

        <HomeSupporters />

        <Text c="dimmed" size="xs" ta="center">
          Trouble signing in? Play the Discord bot?{' '}
          <Anchor component={Link} to="/login" size="xs">
            Sign in with Discord first
          </Anchor>{' '}
          and link the rest from your Account page afterward.
        </Text>
      </Stack>
    </Center>
  );
}

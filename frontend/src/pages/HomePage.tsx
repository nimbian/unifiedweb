// MooreDnD portal homepage.
//
// The umbrella landing for the community: two big tiles routing users to the two
// games — Satchemon (the TCG) and DnD Battle (the Twitch arena). DnD Adventure
// lives *under* Satchemon (its progress pages), so it is not a separate tile.
//
// Both games are now ported in-app (Phase 2), so both tiles navigate internally.
// (The external-link glyph + VITE_*_URL fallback remain in case a tile is pointed
// back out at a standalone site during a transition.)

import { Anchor, Box, Card, Center, Group, SimpleGrid, Stack, Text, ThemeIcon, Title } from '@mantine/core';
import { IconCards, IconExternalLink, IconSwords } from '@tabler/icons-react';
import { Link } from 'react-router-dom';

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

export function HomePage() {
  return (
    <Center mih="100vh" p="md">
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

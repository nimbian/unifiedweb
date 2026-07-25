// MMM donor profile: a supporter's standing (points / rank / total badges) over
// a board of every badge they've earned — highest tier first, one emblem per
// badge. Ports the original donor.html + initProfile.

import { useMemo } from 'react';
import {
  Alert,
  Anchor,
  Box,
  Center,
  Group,
  Image,
  Loader,
  Paper,
  SimpleGrid,
  Stack,
  Text,
  Title,
  Tooltip,
} from '@mantine/core';
import { IconArrowLeft } from '@tabler/icons-react';
import { Link, useParams } from 'react-router-dom';
import { useMmmBadges, useMmmDonor } from '@/hooks/useMmm';
import type { MmmBadgeTier } from '@/types';
import { badgeIcon, formatPoints, ordinal } from './mmmShared';

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Stack gap={0} align="center">
      <Text size="xl" fw={700}>
        {value}
      </Text>
      <Text size="xs" c="dimmed" tt="uppercase" style={{ letterSpacing: '0.06em' }}>
        {label}
      </Text>
    </Stack>
  );
}

function BackLink() {
  return (
    <Anchor component={Link} to="/mmm" c="dimmed">
      <Group gap={4} wrap="nowrap">
        <IconArrowLeft size={16} />
        <Text component="span" inherit size="sm">
          Back to all supporters
        </Text>
      </Group>
    </Anchor>
  );
}

export function MmmDonorPage() {
  const { name = '' } = useParams();
  const { data: donor, isLoading, isError } = useMmmDonor(name);
  const { data: tiers } = useMmmBadges();

  // Every earned badge as a flat list, highest tier first (repeated by count).
  const earned = useMemo(() => {
    if (!donor || !tiers) return [];
    const out: MmmBadgeTier[] = [];
    for (const tier of [...tiers].reverse()) {
      for (let i = 0; i < (donor.badges[tier.key] ?? 0); i += 1) out.push(tier);
    }
    return out;
  }, [donor, tiers]);

  if (isLoading) {
    return (
      <Center h="40vh">
        <Loader />
      </Center>
    );
  }

  if (isError || !donor) {
    return (
      <Stack gap="md">
        <Alert color="red" title="Supporter not found">
          No supporter named “{name}” is currently listed.
        </Alert>
        <BackLink />
      </Stack>
    );
  }

  return (
    <Stack gap="lg">
      <BackLink />

      <Stack gap="xs" align="center">
        <Text size="xs" c="dimmed" tt="uppercase" style={{ letterSpacing: '0.1em' }}>
          Midweek Monster Mash Supporter
        </Text>
        <Title order={1} ta="center">
          {donor.name}
        </Title>
        <Group gap="xl" mt="xs">
          <Stat label="Points" value={`${formatPoints(donor.points)}`} />
          <Stat label="Leaderboard" value={ordinal(donor.rank)} />
          <Stat label="Total Badges" value={donor.total_badges.toLocaleString()} />
        </Group>
      </Stack>

      <Paper withBorder radius="md" p="lg">
        {earned.length === 0 ? (
          <Text c="dimmed" ta="center" py="lg">
            No badges have been recorded yet.
          </Text>
        ) : (
          <SimpleGrid cols={{ base: 3, xs: 4, sm: 6, md: 8 }} spacing="md">
            {earned.map((badge, i) => (
              <Tooltip key={`${badge.key}-${i}`} label={badge.title} withArrow>
                <Box>
                  <Image
                    src={badgeIcon(badge.key)}
                    alt={badge.title}
                    loading="lazy"
                    style={{ filter: 'drop-shadow(0 2px 6px rgba(0,0,0,0.35))' }}
                  />
                </Box>
              </Tooltip>
            ))}
          </SimpleGrid>
        )}
      </Paper>
    </Stack>
  );
}

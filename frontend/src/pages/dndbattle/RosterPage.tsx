// My Characters — the signed-in player's living + retired arena roster.
// Characters are created in Twitch chat (!create); this page is read + links
// through to each sheet, where rename/retire/gear live.

import { Alert, Badge, Card, Center, Code, Group, Loader, SimpleGrid, Stack, Text, Title } from '@mantine/core';
import { Link } from 'react-router-dom';
import { useRoster } from '@/hooks/useArena';
import { arenaErrorMessage, isArenaUnauthorized } from '@/api/arena';
import type { ArenaCharacter } from '@/types/arena';
import { PlayGate } from './PlayGate';

function CharCard({ ch }: { ch: ArenaCharacter }) {
  return (
    <Card
      component={Link}
      to={`/dndbattle/character/${ch.id}`}
      withBorder
      radius="md"
      padding="md"
      style={{ height: '100%' }}
    >
      <Group justify="space-between" wrap="nowrap" align="flex-start">
        <Text fw={700}>{ch.name}</Text>
        <Badge variant="light" color="grape">
          Lv{ch.level}
        </Badge>
      </Group>
      <Text c="dimmed" size="sm">
        {ch.personality && `${ch.personality} `}
        {ch.race} {ch.class_name}
      </Text>
      <Text c="dimmed" size="sm" mt={6}>
        {ch.wins}W / {ch.losses}L · {ch.lifetime_damage.toLocaleString()} dmg
        {!ch.is_retired && ` · ${ch.battles_left} battles left`}
      </Text>
    </Card>
  );
}

export function RosterPage() {
  const { data, isLoading, error } = useRoster();

  if (isLoading) {
    return (
      <Center h="60vh">
        <Loader color="grape" />
      </Center>
    );
  }
  if (error && isArenaUnauthorized(error)) {
    return <PlayGate what="your characters" />;
  }
  if (error || !data) {
    return (
      <Alert color="red" title="Couldn't load your roster">
        {arenaErrorMessage(error, 'Please try again.')}
      </Alert>
    );
  }

  const { living, retired } = data;

  return (
    <Stack gap="lg">
      <Title order={2}>My Characters</Title>

      {living.length === 0 ? (
        <Text c="dimmed">
          No living characters — type <Code>!create &lt;class&gt; &lt;race&gt; &lt;name&gt;</Code> in
          chat to make one.
        </Text>
      ) : (
        <SimpleGrid cols={{ base: 1, xs: 2, md: 3 }} spacing="md">
          {living.map((ch) => (
            <CharCard key={ch.id} ch={ch} />
          ))}
        </SimpleGrid>
      )}

      {retired.length > 0 && (
        <>
          <Title order={3} mt="md">
            Retired legends
          </Title>
          <SimpleGrid cols={{ base: 1, xs: 2, md: 3 }} spacing="md">
            {retired.map((ch) => (
              <CharCard key={ch.id} ch={ch} />
            ))}
          </SimpleGrid>
        </>
      )}
    </Stack>
  );
}

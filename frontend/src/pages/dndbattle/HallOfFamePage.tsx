import { Alert, Card, Center, Loader, SimpleGrid, Stack, Text, Title } from '@mantine/core';
import { IconCrown } from '@tabler/icons-react';
import { useHallOfFame } from '@/hooks/useArena';

const RECORD_LABELS: Record<string, string> = {
  highest_hit: 'Biggest Hit',
  highest_round: 'Biggest Round',
  most_wins: 'Most Wins',
  most_damage: 'Most Lifetime Damage',
};

export function HallOfFamePage() {
  const { data, isLoading, error } = useHallOfFame();

  if (isLoading) {
    return (
      <Center h="60vh">
        <Loader color="grape" />
      </Center>
    );
  }
  if (error || !data) {
    return (
      <Alert color="red" title="Couldn't load the Hall of Fame">
        {(error as Error)?.message ?? 'Please try again.'}
      </Alert>
    );
  }

  const { records } = data;

  return (
    <Stack gap="lg">
      <div>
        <Title order={2}>
          <IconCrown size={26} style={{ verticalAlign: 'text-bottom', marginRight: 8 }} />
          Hall of Fame
        </Title>
        <Text c="dimmed" size="sm">
          All-time records — these survive season resets.
        </Text>
      </div>

      {records.length === 0 ? (
        <Text c="dimmed">No records yet. Go make history!</Text>
      ) : (
        <SimpleGrid cols={{ base: 1, xs: 2, md: 3 }} spacing="md">
          {records.map((r) => (
            <Card key={r.record_key} withBorder radius="md" padding="lg">
              <Text c="dimmed" size="xs" tt="uppercase" fw={600}>
                {RECORD_LABELS[r.record_key] ?? r.record_key}
              </Text>
              <Text fw={700} size="lg" mt={4}>
                {r.character_name}
              </Text>
              <Text c="yellow.5" fw={700} size="xl">
                {Math.round(r.value).toLocaleString()}
              </Text>
              {r.achieved_at && (
                <Text c="dimmed" size="xs" mt={4}>
                  {new Date(r.achieved_at).toLocaleDateString()}
                </Text>
              )}
            </Card>
          ))}
        </SimpleGrid>
      )}
    </Stack>
  );
}

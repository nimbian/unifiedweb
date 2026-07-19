// Achievement catalog: every achievement grouped by category, with how many
// players have earned each (rarity).

import { useMemo } from 'react';
import { Alert, Badge, Card, Center, Group, Loader, Progress, SimpleGrid, Stack, Text, Title } from '@mantine/core';
import { useDndAchievements } from '@/hooks/useDnd';
import { DndNav } from './DndNav';
import type { AchievementInfo } from '@/types/dnd';

export function DndAchievementsPage() {
  const { data, isLoading, isError } = useDndAchievements();

  const byCategory = useMemo(() => {
    const map = new Map<string, AchievementInfo[]>();
    for (const a of data?.achievements ?? []) {
      const cat = a.category ?? 'Other';
      const list = map.get(cat);
      if (list) list.push(a);
      else map.set(cat, [a]);
    }
    return [...map.entries()];
  }, [data]);

  if (isLoading) return <><DndNav /><Center h="40vh"><Loader /></Center></>;
  if (isError || !data) return <><DndNav /><Alert color="red">Failed to load achievements.</Alert></>;

  const total = data.total_players;

  return (
    <>
      <DndNav />
      <Text c="dimmed" mb="md">
        {data.achievements.length} achievements · {total} adventurer{total === 1 ? '' : 's'}
      </Text>
      <Stack gap="lg">
        {byCategory.map(([cat, list]) => (
          <div key={cat}>
            <Title order={4} mb="sm">{cat}</Title>
            <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }} spacing="sm">
              {list.map((a) => {
                const pct = total > 0 ? (a.earned_count / total) * 100 : 0;
                return (
                  <Card key={a.id} withBorder radius="md" padding="sm">
                    <Group gap="sm" wrap="nowrap" align="flex-start">
                      <Text size="xl">{a.emoji ?? '🏆'}</Text>
                      <div style={{ flex: 1 }}>
                        <Group justify="space-between" wrap="nowrap">
                          <Text fw={600}>{a.name}</Text>
                          <Badge size="xs" variant="light" color={pct < 20 ? 'grape' : 'gray'}>
                            {a.earned_count}
                          </Badge>
                        </Group>
                        {a.description && <Text size="xs" c="dimmed">{a.description}</Text>}
                        <Progress value={pct} size="xs" mt={6} radius="xl" />
                      </div>
                    </Group>
                  </Card>
                );
              })}
            </SimpleGrid>
          </div>
        ))}
      </Stack>
    </>
  );
}

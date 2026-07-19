// Progress page — collection stats for a given user.
//
// Top: general stats (total value, deduped "one of each" value, total cards,
// unique cards). Bottom: every set as a block showing owned/total, grouped by
// the collection page's categories. Clicking a block deep-links to that user's
// collection with the matching tab + set open (via ?tab=&set= query params,
// which UserCardsPage reads).

import { useMemo } from 'react';
import {
  Alert,
  Anchor,
  Center,
  Group,
  Loader,
  Paper,
  Progress,
  SimpleGrid,
  Stack,
  Text,
  Title,
  UnstyledButton,
} from '@mantine/core';
import { IconChartBar } from '@tabler/icons-react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useProgress } from '@/hooks/useProgress';
import { useUserProfile } from '@/hooks/useUsers';
import { formatValue } from '@/utils/format';
import type { SetCategory, SetProgress, UserProgress } from '@/types';

// Display order + labels for the set groups (mirrors the collection tabs).
const CATEGORY_LABELS: { key: SetCategory; label: string }[] = [
  { key: 'baseSets', label: 'Base Sets' },
  { key: 'sets', label: 'Unique Sets' },
  { key: 'expansions', label: 'Expansions' },
];

// Sub-section order within Unique Sets (mirrors the Unique Sets picker groups).
const UNIQUE_GROUP_ORDER = ['Creatures', 'Items', 'Locations'];

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <Paper withBorder radius="md" p="md">
      <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
        {label}
      </Text>
      <Text size="xl" fw={700} mt={4}>
        {value}
      </Text>
    </Paper>
  );
}

function SetBlock({ set, onOpen }: { set: SetProgress; onOpen: (s: SetProgress) => void }) {
  const pct = set.total > 0 ? Math.round((set.owned / set.total) * 100) : 0;
  const complete = set.total > 0 && set.owned >= set.total;
  return (
    <UnstyledButton onClick={() => onOpen(set)}>
      <Paper
        withBorder
        radius="md"
        p="sm"
        style={{ height: '100%', borderColor: complete ? 'var(--mantine-color-teal-6)' : undefined }}
      >
        <Group justify="space-between" wrap="nowrap" gap="xs" mb={6}>
          <Text fw={600} lineClamp={1}>
            {set.name}
          </Text>
          <Text size="sm" c={complete ? 'teal' : 'dimmed'} style={{ whiteSpace: 'nowrap' }}>
            {set.owned}/{set.total}
          </Text>
        </Group>
        <Progress value={pct} color={complete ? 'teal' : 'blue'} size="sm" radius="xl" />
        {/* When the set is complete, show the role it grants. */}
        {complete && set.role && (
          <Text size="xs" c="grape" fw={600} ta="center" mt={6}>
            {set.role}
          </Text>
        )}
      </Paper>
    </UnstyledButton>
  );
}

function SetGrid({ sets, onOpen }: { sets: SetProgress[]; onOpen: (s: SetProgress) => void }) {
  return (
    <SimpleGrid cols={{ base: 1, xs: 2, sm: 3, md: 4 }} spacing="sm">
      {sets.map((s) => (
        <SetBlock key={`${s.category}-${s.slug}`} set={s} onOpen={onOpen} />
      ))}
    </SimpleGrid>
  );
}

// Unique Sets rendered as Creatures / Items / Locations sub-sections (then any
// other groups), matching the collection page's Unique Sets picker.
function UniqueSetGroups({
  sets,
  onOpen,
}: {
  sets: SetProgress[];
  onOpen: (s: SetProgress) => void;
}) {
  const byGroup = useMemo(() => {
    const map = new Map<string, SetProgress[]>();
    for (const s of sets) {
      const g = s.group ?? 'Other';
      const list = map.get(g);
      if (list) list.push(s);
      else map.set(g, [s]);
    }
    const known = UNIQUE_GROUP_ORDER.filter((g) => map.has(g));
    const rest = [...map.keys()].filter((g) => !UNIQUE_GROUP_ORDER.includes(g)).sort();
    return [...known, ...rest].map((g) => [g, map.get(g)!] as const);
  }, [sets]);

  return (
    <Stack gap="sm">
      {byGroup.map(([group, groupSets]) => (
        <div key={group}>
          <Text fw={600} c="dimmed" size="sm" mb={6}>
            {group}
          </Text>
          <SetGrid sets={groupSets} onOpen={onOpen} />
        </div>
      ))}
    </Stack>
  );
}

function ProgressContent({ did, data }: { did: string; data: UserProgress }) {
  const navigate = useNavigate();
  const { data: profile } = useUserProfile(did);

  const grouped = useMemo(() => {
    const map: Record<SetCategory, SetProgress[]> = { baseSets: [], sets: [], expansions: [] };
    for (const s of data.sets) map[s.category].push(s);
    return map;
  }, [data.sets]);

  const openSet = (s: SetProgress) =>
    navigate(`/user/${did}?tab=${s.category}&set=${encodeURIComponent(s.slug)}`);

  const { stats } = data;

  return (
    <Stack gap="lg">
      <Group justify="space-between" align="flex-end">
        <Title order={2}>
          <IconChartBar size={26} style={{ verticalAlign: 'text-bottom', marginRight: 8 }} />
          {profile?.name ?? did}'s Progress
        </Title>
        <Anchor component={Link} to={`/user/${did}`} size="sm">
          View collection →
        </Anchor>
      </Group>

      {/* General stats */}
      <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="md">
        <StatCard label="Collection value" value={formatValue(stats.total_value)} />
        <StatCard label="Best Copy Collection" value={formatValue(stats.top_value)} />
        <StatCard label="Total cards" value={String(stats.total_cards)} />
        <StatCard label="Unique cards" value={String(stats.unique_cards)} />
      </SimpleGrid>

      {/* Per-set completion */}
      <Stack gap="md">
        {CATEGORY_LABELS.map(({ key, label }) =>
          grouped[key].length === 0 ? null : (
            <div key={key}>
              <Title order={4} mb="sm">
                {label}
              </Title>
              {key === 'sets' ? (
                <UniqueSetGroups sets={grouped[key]} onOpen={openSet} />
              ) : (
                <SetGrid sets={grouped[key]} onOpen={openSet} />
              )}
            </div>
          ),
        )}
      </Stack>
    </Stack>
  );
}

export function ProgressPage() {
  const { did } = useParams();
  const { data, isLoading, isError } = useProgress(did ?? '');

  if (!did || isLoading) {
    return (
      <Center h="40vh">
        <Loader />
      </Center>
    );
  }
  if (isError || !data) {
    return <Alert color="red">Failed to load progress.</Alert>;
  }
  return <ProgressContent did={did} data={data} />;
}

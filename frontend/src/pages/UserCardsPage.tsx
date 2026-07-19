// A user's collection page — replaces userCards.j2 + userCardsJS.j2.
//
// The legacy template had a wall of jQuery buttons that swapped DataTables.
// Here that becomes Mantine <Tabs>:
//   Full / Creatures / Items / Locations -> flat CardsTable (by category)
//   Base Sets                            -> pick Creatures/Items/Locations base set
//   Unique Sets                          -> pick a creature/item/location set
//   Expansions                           -> pick an expansion
// The "self" variant resolves the did from the authenticated user (was /mycards).
//
// When viewing your own collection, every card table shows sell checkboxes whose
// selection is shared page-wide (SelectionProvider); the SellBar drives the sale
// and a single "Clear all".

import { useMemo, useState } from 'react';
import {
  Alert,
  Anchor,
  Badge,
  Center,
  Loader,
  Paper,
  Select,
  Stack,
  Tabs,
  Text,
  Title,
} from '@mantine/core';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';
import { useMyRoles, useSetRole, useUserProfile } from '@/hooks/useUsers';
import { useCards } from '@/hooks/useCollections';
import { useSetView, useSidebar } from '@/hooks/useSets';
import { BuyBar } from '@/components/BuyBar';
import { CardsTable } from '@/components/CardsTable';
import { SelectionProvider } from '@/components/SelectionContext';
import { SellBar } from '@/components/SellBar';
import { SetTable } from '@/components/SetTable';
import type { CardCategory } from '@/types';

// Base sets, broken out per mon class (slugs handled specially by the backend).
const BASE_SET_OPTIONS = [
  { name: 'Creatures', slug: 'BaseCreatures' },
  { name: 'Items', slug: 'BaseItems' },
  { name: 'Locations', slug: 'BaseLocations' },
];

export function UserCardsPage({ self = false, shop = false }: { self?: boolean; shop?: boolean }) {
  const params = useParams();
  const { user } = useAuth();
  // The shop is the system user's collection (uid/did 0): cards sold back to it.
  const did = shop ? '0' : self ? user?.did : params.did;

  if (!did) {
    return (
      <Center h="40vh">
        <Loader />
      </Center>
    );
  }
  return <UserCardsContent did={did} shop={shop} />;
}

function UserCardsContent({ did, shop = false }: { did: string; shop?: boolean }) {
  const { user } = useAuth();
  const { data: profile } = useUserProfile(did);
  const { data: sidebar } = useSidebar();

  // Deep-link support: the progress page links here with ?tab=&set= so a clicked
  // set block opens the right tab with that set pre-selected.
  const [searchParams] = useSearchParams();
  const initialTab = searchParams.get('tab') ?? 'full';
  const initialSet = searchParams.get('set');
  const [tab, setTab] = useState<string>(initialTab);

  // You may sell only your *own* cards. On the shop, any signed-in user may buy.
  // The backend enforces both independently. Either enables card checkboxes.
  const canSell = !shop && Boolean(user) && user?.did === did;
  const canBuy = shop && Boolean(user);
  const selectable = canSell || canBuy;

  return (
    <SelectionProvider>
      <Stack gap="xs" align="center" mb="md">
        <Title order={2} c="red.5">
          {shop ? 'Enchanted Sleeve' : `${profile?.name ?? did}'s Collection`}
        </Title>

        {/* Chosen role, shown below the name to everyone who views the page. */}
        {!shop && profile?.role && (
          <Badge color="grape" variant="light" size="lg">
            {profile.role}
          </Badge>
        )}

        {/* The owner can pick a role from the sets they have completed. */}
        {canSell && <RolePicker did={did} current={profile?.roleid ?? null} />}

        {!shop && (
          <Anchor component={Link} to={`/user/${did}/progress`} size="sm">
            View progress →
          </Anchor>
        )}
      </Stack>

      {canBuy ? <BuyBar /> : canSell ? <SellBar did={did} /> : null}

      <Tabs value={tab} onChange={(v) => setTab(v ?? 'full')} keepMounted={false}>
        <Tabs.List mb="md">
          <Tabs.Tab value="full">Full Collection</Tabs.Tab>
          <Tabs.Tab value="monsters">Creatures</Tabs.Tab>
          <Tabs.Tab value="items">Items</Tabs.Tab>
          <Tabs.Tab value="locations">Locations</Tabs.Tab>
          <Tabs.Tab value="baseSets">Base Sets</Tabs.Tab>
          <Tabs.Tab value="sets">Unique Sets</Tabs.Tab>
          <Tabs.Tab value="expansions">Expansions</Tabs.Tab>
        </Tabs.List>

        {(['full', 'monsters', 'items', 'locations'] as CardCategory[]).map((cat) => (
          <Tabs.Panel key={cat} value={cat}>
            <CategoryPanel did={did} category={cat} active={tab === cat} selectable={selectable} />
          </Tabs.Panel>
        ))}

        <Tabs.Panel value="baseSets">
          <SetPicker
            did={did}
            active={tab === 'baseSets'}
            selectable={selectable}
            initialSlug={initialTab === 'baseSets' ? initialSet : null}
            groups={[{ label: 'Base Sets', options: BASE_SET_OPTIONS }]}
            description="The starter base sets — pick Creatures, Items, or Locations to see which of its cards are owned."
          />
        </Tabs.Panel>

        <Tabs.Panel value="sets">
          <SetPicker
            did={did}
            active={tab === 'sets'}
            selectable={selectable}
            initialSlug={initialTab === 'sets' ? initialSet : null}
            groups={[
              { label: 'Creatures', options: sidebar?.creature_sets ?? [] },
              { label: 'Items', options: sidebar?.item_sets ?? [] },
              { label: 'Locations', options: sidebar?.location_sets ?? [] },
            ]}
            description="Themed collectible sets. Choose a creature, item, or location set to see its cards and which are owned."
          />
        </Tabs.Panel>

        <Tabs.Panel value="expansions">
          <SetPicker
            did={did}
            active={tab === 'expansions'}
            selectable={selectable}
            initialSlug={initialTab === 'expansions' ? initialSet : null}
            groups={[{ label: 'Expansions', options: sidebar?.expansions ?? [] }]}
            description="Full card expansions. Choose an expansion to see all its cards and which are owned."
          />
        </Tabs.Panel>
      </Tabs>
    </SelectionProvider>
  );
}

// Role selector — shown on the owner's own collection page. Options are the sets
// the user has completed; choosing one displays its role below their name, and
// clearing it (the Select's clear button) removes the role.
function RolePicker({ did, current }: { did: string; current: number | null }) {
  const { data: options = [], isLoading } = useMyRoles();
  const setRole = useSetRole(did);

  const data = useMemo(
    () => options.map((o) => ({ value: String(o.rwid), label: o.role ?? o.name ?? `Set ${o.rwid}` })),
    [options],
  );

  const noneCompleted = !isLoading && options.length === 0;

  return (
    <Select
      size="xs"
      maw={260}
      clearable
      disabled={noneCompleted || setRole.isPending}
      placeholder={noneCompleted ? 'Complete a set to earn a role' : 'Select a role…'}
      data={data}
      value={current != null ? String(current) : null}
      onChange={(v) => setRole.mutate(v ? Number(v) : null)}
    />
  );
}

function CategoryPanel({
  did,
  category,
  active,
  selectable,
}: {
  did: string;
  category: CardCategory;
  active: boolean;
  selectable: boolean;
}) {
  const { data = [], isFetching, isError } = useCards(did, active ? category : 'full');
  if (isError) return <Alert color="red">Failed to load cards.</Alert>;
  return <CardsTable records={data} fetching={isFetching} selectable={selectable} />;
}

function SetPanel({
  did,
  slug,
  selectable,
}: {
  did: string;
  slug: string | null;
  selectable?: boolean;
}) {
  const { data = [], isFetching, isError } = useSetView(did, slug);
  if (isError) return <Alert color="red">Failed to load set.</Alert>;
  return <SetTable records={data} fetching={isFetching} selectable={selectable} />;
}

interface PickerGroup {
  label: string;
  options: { name: string; slug: string }[];
}

function SetPicker({
  did,
  active,
  groups,
  selectable,
  description,
  initialSlug = null,
}: {
  did: string;
  active: boolean;
  groups: PickerGroup[];
  selectable?: boolean;
  description?: string;
  initialSlug?: string | null;
}) {
  const [slug, setSlug] = useState<string | null>(initialSlug);

  const data = useMemo(
    () =>
      groups
        .filter((g) => g.options.length > 0)
        .map((g) => ({
          group: g.label,
          items: g.options.map((o) => ({ value: o.slug, label: o.name })),
        })),
    [groups],
  );

  return (
    <Paper p="xs">
      <Select
        placeholder="Choose a set…"
        searchable
        clearable
        mb="md"
        data={data}
        value={slug}
        onChange={setSlug}
        maw={360}
      />
      {slug ? (
        <SetPanel did={did} slug={active ? slug : null} selectable={selectable} />
      ) : description ? (
        <Text c="dimmed" size="sm">
          {description}
        </Text>
      ) : null}
    </Paper>
  );
}

// Global search page — replaces search.j2 / the `#searchTable` DataTable backed
// by /api/getAll.
//
// Loading is incremental: the backend filters/orders and returns one page at a
// time, and the table fetches the next page as the user scrolls to the bottom
// (infinite scroll). The text box, column filters, and sorting are all applied
// *server-side* (over the whole dataset, not just the rows already loaded) — so
// changing any of them refetches from the first page.

import { useMemo, useState } from 'react';
import { Alert, Anchor, Group, Text, TextInput, Title } from '@mantine/core';
import { IconSearch } from '@tabler/icons-react';
import { useSearchParams } from 'react-router-dom';
import { DataTable, type DataTableSortStatus } from 'mantine-datatable';
import { useDebouncedValue } from '@mantine/hooks';
import { useSearch, useSearchFacets } from '@/hooks/useCollections';
import { useCardViewer } from '@/components/CardViewer';
import { SelectColumnFilter, TextColumnFilter, YesNoColumnFilter } from '@/components/TextColumnFilter';
import { ActivePill } from '@/components/ActivePill';
import { compareCr, formatValue } from '@/utils/format';
import type { SearchRow } from '@/types';

export function SearchPage() {
  // Deep-link support: ?name=<card> pre-filters the Card column (used by the
  // "find more" shortcut on unowned set cards).
  const [searchParams] = useSearchParams();
  const [query, setQuery] = useState('');
  const [debounced] = useDebouncedValue(query, 300);
  const [holoFilter, setHoloFilter] = useState<string | null>(null);
  const [expFilter, setExpFilter] = useState<string | null>(null);
  const [gradeFilter, setGradeFilter] = useState<string | null>(null);
  const [crFilter, setCrFilter] = useState<string | null>(null);
  const [activeFilter, setActiveFilter] = useState<string | null>(null);
  const [nameFilter, setNameFilter] = useState(searchParams.get('name') ?? '');
  const [debouncedName] = useDebouncedValue(nameFilter, 300);
  const [sort, setSort] = useState<DataTableSortStatus<SearchRow>>({
    columnAccessor: 'name',
    direction: 'asc',
  });
  const viewer = useCardViewer();

  const { data: facets } = useSearchFacets();
  const expOptions = useMemo(
    () => (facets?.expansions ?? []).map((e) => ({ value: e, label: e })),
    [facets],
  );
  const gradeOptions = useMemo(
    () => (facets?.grades ?? []).map((g) => ({ value: String(g), label: String(g) })),
    [facets],
  );
  // CR options use the custom challenge-rating order, not the server's text sort.
  const crOptions = useMemo(
    () => [...(facets?.crs ?? [])].sort(compareCr).map((c) => ({ value: c, label: c })),
    [facets],
  );

  const filters = useMemo(
    () => ({
      holo: holoFilter === null ? undefined : holoFilter === 'yes',
      exp: expFilter ?? undefined,
      grade: gradeFilter === null ? undefined : Number(gradeFilter),
      cr: crFilter ?? undefined,
      name: debouncedName.trim() || undefined,
      active: activeFilter === null ? undefined : activeFilter === 'active',
      sort: String(sort.columnAccessor),
      direction: sort.direction,
    }),
    [holoFilter, expFilter, gradeFilter, crFilter, debouncedName, activeFilter, sort],
  );

  const {
    data,
    isLoading,
    isError,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useSearch(debounced.trim(), filters);

  const records = useMemo(() => data?.pages.flatMap((p) => p.items) ?? [], [data]);
  const total = data?.pages[0]?.total ?? 0;

  if (isError) return <Alert color="red">Failed to load search data.</Alert>;

  return (
    <>
      <Group justify="space-between" mb="md">
        <Title order={2}>Search</Title>
        <TextInput
          placeholder="Filter by user, card, expansion, set…"
          leftSection={<IconSearch size={16} />}
          value={query}
          onChange={(e) => setQuery(e.currentTarget.value)}
          w={320}
        />
      </Group>
      <DataTable<SearchRow>
        withTableBorder
        borderRadius="md"
        striped
        highlightOnHover
        height={600}
        fetching={isLoading}
        idAccessor="collection_id"
        records={records}
        sortStatus={sort}
        onSortStatusChange={setSort}
        onScrollToBottom={() => {
          if (hasNextPage && !isFetchingNextPage) fetchNextPage();
        }}
        columns={[
          {
            accessor: 'collection_id',
            title: 'Card ID',
            width: 90,
            sortable: true,
            render: ({ collection_id, name }) => (
              <Anchor onClick={() => viewer.open({ collectionId: collection_id, name })}>
                {collection_id}
              </Anchor>
            ),
          },
          { accessor: 'user', title: 'User', sortable: true },
          {
            accessor: 'last_active',
            title: 'Active',
            width: 100,
            textAlign: 'center',
            filter: (
              <SelectColumnFilter
                label="Active"
                value={activeFilter}
                onChange={setActiveFilter}
                data={[
                  { value: 'active', label: 'Active' },
                  { value: 'inactive', label: 'Inactive' },
                ]}
              />
            ),
            filtering: activeFilter !== null,
            render: ({ last_active }) => <ActivePill lastActive={last_active} />,
          },
          {
            accessor: 'cr',
            title: 'CR',
            width: 70,
            sortable: true,
            filter: (
              <SelectColumnFilter label="CR" value={crFilter} onChange={setCrFilter} data={crOptions} />
            ),
            filtering: crFilter !== null,
          },
          {
            accessor: 'name',
            title: 'Card',
            sortable: true,
            filter: (
              <TextColumnFilter
                value={nameFilter}
                onChange={setNameFilter}
                placeholder="Filter cards…"
              />
            ),
            filtering: nameFilter !== '',
          },
          {
            accessor: 'exp',
            title: 'Expansion',
            sortable: true,
            filter: (
              <SelectColumnFilter
                label="Expansion"
                value={expFilter}
                onChange={setExpFilter}
                data={expOptions}
              />
            ),
            filtering: expFilter !== null,
          },
          {
            accessor: 'grade',
            title: 'Grade',
            width: 80,
            sortable: true,
            filter: (
              <SelectColumnFilter
                label="Grade"
                value={gradeFilter}
                onChange={setGradeFilter}
                data={gradeOptions}
              />
            ),
            filtering: gradeFilter !== null,
          },
          {
            accessor: 'holo',
            title: 'Holo',
            width: 70,
            filter: (
              <YesNoColumnFilter label="Holo" value={holoFilter} onChange={setHoloFilter} />
            ),
            filtering: holoFilter !== null,
            render: ({ holo }) => (holo ? 'Yes' : 'No'),
          },
          { accessor: 'edition', title: 'Edition', sortable: true },
          {
            accessor: 'value',
            title: 'Value',
            textAlign: 'right',
            sortable: true,
            render: ({ value }) => formatValue(value),
          },
          { accessor: 'set_name', title: 'Set', sortable: true },
        ]}
      />
      <Text size="sm" c="dimmed" mt="xs">
        {isLoading
          ? 'Loading…'
          : `Loaded ${records.length} of ${total}${
              isFetchingNextPage ? ' (loading more…)' : ''
            }`}
      </Text>
    </>
  );
}

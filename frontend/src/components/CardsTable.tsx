// Reusable owned-cards grid (Mantine DataTable) — replaces the jQuery DataTables
// "#cs" table. Sorts by CR using the legacy ordering and gold-highlights
// grade-10 holo cards. Paginated with a card-name column filter.

import { useEffect, useMemo, useState } from 'react';
import { DataTable, type DataTableSortStatus } from 'mantine-datatable';
import { Anchor, Badge } from '@mantine/core';
import type { CardRow } from '@/types';
import { compareCr, formatValue, isGoldCard } from '@/utils/format';
import { useCardViewer } from './CardViewer';
import { useSelection } from './SelectionContext';
import {
  matches,
  matchesYesNo,
  SelectColumnFilter,
  TextColumnFilter,
  YesNoColumnFilter,
} from './TextColumnFilter';

// Distinct, sorted Select options for a column, derived from the loaded rows.
function optionsFrom(records: CardRow[], pick: (c: CardRow) => string | number | null) {
  const seen = new Set<string>();
  for (const r of records) {
    const v = pick(r);
    if (v !== null && v !== undefined && v !== '') seen.add(String(v));
  }
  return [...seen]
    .sort((a, b) => a.localeCompare(b, undefined, { numeric: true }))
    .map((v) => ({ value: v, label: v }));
}

const PAGE_SIZES = [10, 25, 50, 100];

interface Props {
  records: CardRow[];
  fetching?: boolean;
  // When true, a checkbox column is shown and selection is shared via the page's
  // SelectionContext (used by the "sell your own cards" flow). No-op if rendered
  // outside a SelectionProvider.
  selectable?: boolean;
}

export function CardsTable({ records, fetching, selectable }: Props) {
  const selection = useSelection();
  const selecting = selectable && selection ? selection : null;
  const viewer = useCardViewer();
  const [sort, setSort] = useState<DataTableSortStatus<CardRow>>({
    columnAccessor: 'name',
    direction: 'asc',
  });
  const [nameFilter, setNameFilter] = useState('');
  const [holoFilter, setHoloFilter] = useState<string | null>(null);
  const [expFilter, setExpFilter] = useState<string | null>(null);
  const [gradeFilter, setGradeFilter] = useState<string | null>(null);
  const [crFilter, setCrFilter] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  const expOptions = useMemo(() => optionsFrom(records, (c) => c.exp), [records]);
  const gradeOptions = useMemo(() => optionsFrom(records, (c) => c.grade), [records]);
  // CR options use the custom challenge-rating order, not alphabetical.
  const crOptions = useMemo(() => {
    const seen = new Set<string>();
    for (const c of records) if (c.cr) seen.add(c.cr);
    return [...seen].sort(compareCr).map((v) => ({ value: v, label: v }));
  }, [records]);

  const sorted = useMemo(() => {
    const dir = sort.direction === 'asc' ? 1 : -1;
    return [...records]
      .filter((c) => matches(c.name, nameFilter))
      .filter((c) => matchesYesNo(c.holo, holoFilter))
      .filter((c) => expFilter === null || c.exp === expFilter)
      .filter((c) => gradeFilter === null || String(c.grade ?? '') === gradeFilter)
      .filter((c) => crFilter === null || c.cr === crFilter)
      .sort((a, b) => {
        if (sort.columnAccessor === 'cr') return compareCr(a.cr, b.cr) * dir;
        const av = a[sort.columnAccessor as keyof CardRow];
        const bv = b[sort.columnAccessor as keyof CardRow];
        return String(av ?? '').localeCompare(String(bv ?? ''), undefined, { numeric: true }) * dir;
      });
  }, [records, sort, nameFilter, holoFilter, expFilter, gradeFilter, crFilter]);

  // Keep the page in range as data, filter, sort or page size change.
  useEffect(
    () => setPage(1),
    [nameFilter, holoFilter, expFilter, gradeFilter, crFilter, pageSize, sort, records],
  );

  const visible = sorted.slice((page - 1) * pageSize, page * pageSize);

  return (
    <DataTable<CardRow>
      withTableBorder
      borderRadius="md"
      striped
      highlightOnHover
      minHeight={180}
      fetching={fetching}
      idAccessor="collection_id"
      records={visible}
      totalRecords={sorted.length}
      page={page}
      onPageChange={setPage}
      recordsPerPage={pageSize}
      recordsPerPageOptions={PAGE_SIZES}
      onRecordsPerPageChange={setPageSize}
      sortStatus={sort}
      onSortStatusChange={setSort}
      selectedRecords={selecting ? selecting.selectedFor(records) : undefined}
      onSelectedRecordsChange={
        selecting ? (next) => selecting.setSelectedFor(records, next) : undefined
      }
      rowColor={({ grade, holo }) => (isGoldCard(grade, holo) ? 'yellow' : undefined)}
      columns={[
        {
          accessor: 'collection_id',
          title: 'Card ID',
          sortable: true,
          width: 90,
          render: ({ collection_id, name }) => (
            <Anchor onClick={() => viewer.open({ collectionId: collection_id, name })}>
              {collection_id}
            </Anchor>
          ),
        },
        {
          accessor: 'cr',
          title: 'CR',
          sortable: true,
          width: 70,
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
          sortable: true,
          width: 80,
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
          width: 80,
          sortable: true,
          filter: (
            <YesNoColumnFilter label="Holo" value={holoFilter} onChange={setHoloFilter} />
          ),
          filtering: holoFilter !== null,
          render: ({ holo }) =>
            holo ? <Badge color="grape">Yes</Badge> : <Badge color="gray">No</Badge>,
        },
        { accessor: 'edition', title: 'Edition' },
        {
          accessor: 'value',
          title: 'Value',
          sortable: true,
          textAlign: 'right',
          render: ({ value }) => formatValue(value),
        },
        { accessor: 'set_name', title: 'Set', sortable: true },
      ]}
    />
  );
}

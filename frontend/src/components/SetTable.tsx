// Per-set ownership grid with expandable rows — replaces the jQuery `#setTable`
// plus its child-row drill-down (createChild in userCardsJS.j2). Owned slots are
// green; expanding a row reveals the actual owned cards for that slot. Paginated,
// with a card-name text filter, a Yes/No filter on "Acquired?", and sortable
// name/acquired/quantity columns.

import { ActionIcon, Badge, Box, Group, Tooltip } from '@mantine/core';
import { IconQuestionMark } from '@tabler/icons-react';
import { DataTable, type DataTableSortStatus } from 'mantine-datatable';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { SetCardEntry } from '@/types';
import { CardsTable } from './CardsTable';
import { matches, matchesYesNo, TextColumnFilter, YesNoColumnFilter } from './TextColumnFilter';

const PAGE_SIZES = [10, 25, 50, 100];

interface Props {
  records: SetCardEntry[];
  fetching?: boolean;
  // Show sell checkboxes on the inner owned-cards tables (owner only).
  selectable?: boolean;
}

export function SetTable({ records, fetching, selectable }: Props) {
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState<string[]>([]);
  const [nameFilter, setNameFilter] = useState('');
  const [acquiredFilter, setAcquiredFilter] = useState<string | null>(null);
  const [sort, setSort] = useState<DataTableSortStatus<SetCardEntry>>({
    columnAccessor: 'name',
    direction: 'asc',
  });
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  const sorted = useMemo(() => {
    const dir = sort.direction === 'asc' ? 1 : -1;
    return records
      .filter((r) => matches(r.name, nameFilter))
      .filter((r) => matchesYesNo(r.has, acquiredFilter))
      .sort((a, b) => {
        if (sort.columnAccessor === 'count') return (a.count - b.count) * dir;
        if (sort.columnAccessor === 'has') return (Number(a.has) - Number(b.has)) * dir;
        return (a.name ?? '').localeCompare(b.name ?? '', undefined, { numeric: true }) * dir;
      });
  }, [records, nameFilter, acquiredFilter, sort]);

  useEffect(() => setPage(1), [nameFilter, acquiredFilter, sort, pageSize, records]);

  const visible = sorted.slice((page - 1) * pageSize, page * pageSize);

  return (
    <DataTable<SetCardEntry>
      withTableBorder
      borderRadius="md"
      striped
      highlightOnHover
      minHeight={180}
      fetching={fetching}
      idAccessor="name"
      records={visible}
      totalRecords={sorted.length}
      page={page}
      onPageChange={setPage}
      recordsPerPage={pageSize}
      recordsPerPageOptions={PAGE_SIZES}
      onRecordsPerPageChange={setPageSize}
      sortStatus={sort}
      onSortStatusChange={setSort}
      rowColor={({ has }) => (has ? 'green' : undefined)}
      rowExpansion={{
        allowMultiple: true,
        expanded: { recordIds: expanded, onRecordIdsChange: setExpanded },
        content: ({ record }) =>
          record.cards.length > 0 ? (
            <Box p="sm">
              <CardsTable records={record.cards} selectable={selectable} />
            </Box>
          ) : null,
      }}
      columns={[
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
          // For cards the user doesn't own (quantity 0), offer a shortcut to the
          // global search, pre-filtered to this card name ("find more").
          render: ({ name, count }) => (
            <Group gap={6} wrap="nowrap">
              <span>{name}</span>
              {count === 0 && name && (
                <Tooltip label="Find more" withArrow openDelay={150}>
                  <ActionIcon
                    size="xs"
                    radius="xl"
                    variant="light"
                    color="blue"
                    aria-label="Find more"
                    onClick={(e) => {
                      e.stopPropagation(); // don't toggle the row's expansion
                      navigate(`/satchemon/search?name=${encodeURIComponent(name)}`);
                    }}
                  >
                    <IconQuestionMark size={13} />
                  </ActionIcon>
                </Tooltip>
              )}
            </Group>
          ),
        },
        {
          accessor: 'has',
          title: 'Acquired?',
          width: 120,
          sortable: true,
          filter: (
            <YesNoColumnFilter
              label="Acquired?"
              value={acquiredFilter}
              onChange={setAcquiredFilter}
            />
          ),
          filtering: acquiredFilter !== null,
          render: ({ has }) =>
            has ? <Badge color="green">Yes</Badge> : <Badge color="gray">No</Badge>,
        },
        { accessor: 'count', title: 'Quantity', width: 110, textAlign: 'right', sortable: true },
      ]}
    />
  );
}

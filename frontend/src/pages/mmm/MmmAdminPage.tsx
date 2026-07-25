// MMM admin: upload a donors CSV to replace the supporter data. Reached only by
// portal admins (AdminRoute gates the route; the backend re-checks the
// admin_discord_ids allowlist on POST /api/mmm/admin/donors).

import { useState } from 'react';
import {
  Alert,
  Anchor,
  Button,
  Code,
  FileInput,
  Group,
  Paper,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { IconArrowLeft, IconUpload } from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import axios from 'axios';
import { mmmApi } from '@/api/mmm';

const CSV_HEADER = 'name,initiate,apprentice,knight,master,ascendant,luminary,arbiter';

function messageFor(err: unknown, fallback: string): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail;
    if (typeof detail === 'string' && detail) return detail;
  }
  return fallback;
}

export function MmmAdminPage() {
  const [file, setFile] = useState<File | null>(null);
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: (f: File) => mmmApi.importDonors(f),
    onSuccess: (res) => {
      notifications.show({
        color: 'green',
        message: `Imported: ${res.inserted} added, ${res.updated} updated.`,
      });
      queryClient.invalidateQueries({ queryKey: ['mmm'] });
      setFile(null);
    },
    onError: (err) => {
      notifications.show({ color: 'red', message: messageFor(err, 'Upload failed. Try again.') });
    },
  });

  const result = mutation.data;

  return (
    <Stack gap="lg" maw={620}>
      <Anchor component={Link} to="/mmm" c="dimmed">
        <Group gap={4} wrap="nowrap">
          <IconArrowLeft size={16} />
          <Text component="span" inherit size="sm">
            Back to supporters
          </Text>
        </Group>
      </Anchor>

      <Stack gap={4}>
        <Title order={1}>Manage supporters</Title>
        <Text c="dimmed">
          Upload a donors CSV to update the supporter wall. Rows are matched by name — existing
          supporters are updated, new names are added.
        </Text>
      </Stack>

      <Paper withBorder radius="md" p="lg">
        <Stack>
          <Text size="sm">The file must start with this header row:</Text>
          <Code block>{CSV_HEADER}</Code>

          <FileInput
            label="donors.csv"
            placeholder="Choose a .csv file"
            accept=".csv,text/csv"
            value={file}
            onChange={setFile}
            clearable
            leftSection={<IconUpload size={16} />}
          />

          <Group>
            <Button
              onClick={() => file && mutation.mutate(file)}
              loading={mutation.isPending}
              disabled={!file}
            >
              Upload &amp; update
            </Button>
          </Group>

          {result && (
            <Alert color="green" title="Import complete">
              {result.inserted} added, {result.updated} updated ({result.total} rows).
            </Alert>
          )}
        </Stack>
      </Paper>
    </Stack>
  );
}

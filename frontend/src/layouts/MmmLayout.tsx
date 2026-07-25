// Layout for the Midweek Monster Mash donor pages.
//
// MMM is a community-wide supporter wall (not Satchemon-specific), reached from
// the homepage, so it gets its own light chrome rather than the Satchemon
// AppShell: a slim header (brand → home) over a centered content column. Public;
// no auth required.

import { Anchor, Box, Container, Group, Text } from '@mantine/core';
import { IconArrowLeft } from '@tabler/icons-react';
import { Link, Outlet } from 'react-router-dom';

export function MmmLayout() {
  return (
    <Box>
      <Box
        component="header"
        style={{
          borderBottom: '1px solid var(--mantine-color-default-border)',
          position: 'sticky',
          top: 0,
          zIndex: 10,
          backdropFilter: 'blur(6px)',
          background: 'var(--mantine-color-body)',
        }}
      >
        <Container size="lg" py="sm">
          <Group justify="space-between" wrap="nowrap">
            <Anchor component={Link} to="/" c="dimmed" fw={600} underline="never">
              <Group gap={6} wrap="nowrap">
                <IconArrowLeft size={16} />
                <Text component="span" inherit>
                  Moore
                  <Text component="span" inherit c="red.5">
                    DnD
                  </Text>
                </Text>
              </Group>
            </Anchor>
            <Text fw={700} size="sm" c="dimmed" tt="uppercase" style={{ letterSpacing: '0.08em' }}>
              Midweek Monster Mash
            </Text>
          </Group>
        </Container>
      </Box>

      <Container size="lg" py="xl">
        <Outlet />
      </Container>
    </Box>
  );
}

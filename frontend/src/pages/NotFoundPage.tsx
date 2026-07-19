import { Button, Center, Stack, Text, Title } from '@mantine/core';
import { useNavigate } from 'react-router-dom';

export function NotFoundPage() {
  const navigate = useNavigate();
  return (
    <Center h="60vh">
      <Stack align="center">
        <Title order={1}>404</Title>
        <Text c="dimmed">This page does not exist.</Text>
        <Button onClick={() => navigate('/')}>Back to all users</Button>
      </Stack>
    </Center>
  );
}

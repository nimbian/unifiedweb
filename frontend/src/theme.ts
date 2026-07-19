import { createTheme } from '@mantine/core';

// Dark theme echoing the legacy app (Bootstrap dark + red collection headings).
export const theme = createTheme({
  primaryColor: 'red',
  fontFamily: 'Inter, system-ui, sans-serif',
  defaultRadius: 'md',
  headings: { fontWeight: '700' },
});

// Drive slideshow — replaces cs.html. A Mantine Carousel-style crossfade is
// overkill here; we use a simple image stage with prev/next/autoplay controls
// and a LoadingOverlay while images load.

import { useCallback, useEffect, useState } from 'react';
import {
  ActionIcon,
  Alert,
  Box,
  Group,
  LoadingOverlay,
  Paper,
  Select,
  Text,
} from '@mantine/core';
import { IconChevronLeft, IconChevronRight, IconPlayerPause, IconPlayerPlay } from '@tabler/icons-react';
import { driveApi } from '@/api/drive';
import { useDriveImages } from '@/hooks/useDrive';

const SPEEDS = [
  { value: '2000', label: '2 s' },
  { value: '4000', label: '4 s' },
  { value: '6000', label: '6 s' },
  { value: '10000', label: '10 s' },
];

export function SlideshowPage() {
  const { data: images = [], isLoading, isError } = useDriveImages();
  const [current, setCurrent] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [interval, setIntervalMs] = useState(4000);

  const next = useCallback(
    () => setCurrent((c) => (images.length ? (c + 1) % images.length : 0)),
    [images.length],
  );
  const prev = () => setCurrent((c) => (images.length ? (c - 1 + images.length) % images.length : 0));

  useEffect(() => {
    if (!playing || images.length === 0) return;
    const id = window.setInterval(next, interval);
    return () => window.clearInterval(id);
  }, [playing, interval, images.length, next]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight') next();
      if (e.key === 'ArrowLeft') prev();
      if (e.key === ' ') {
        e.preventDefault();
        setPlaying((p) => !p);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  if (isError) return <Alert color="red">Could not load images from Drive.</Alert>;

  const img = images[current];

  return (
    <Paper p="md" pos="relative" mih={400}>
      <LoadingOverlay visible={isLoading} />
      <Group justify="space-between" mb="sm">
        <Text c="dimmed" size="sm">
          {images.length ? `${current + 1} / ${images.length}` : '—'}
        </Text>
        <Group>
          <ActionIcon variant="default" onClick={() => setPlaying((p) => !p)}>
            {playing ? <IconPlayerPause size={18} /> : <IconPlayerPlay size={18} />}
          </ActionIcon>
          <Select
            w={90}
            data={SPEEDS}
            value={String(interval)}
            onChange={(v) => setIntervalMs(Number(v))}
            aria-label="Interval"
          />
        </Group>
      </Group>

      <Box pos="relative" style={{ display: 'flex', justifyContent: 'center', minHeight: 360 }}>
        <ActionIcon
          variant="default"
          size="lg"
          pos="absolute"
          left={0}
          top="50%"
          onClick={prev}
          aria-label="Previous"
        >
          <IconChevronLeft />
        </ActionIcon>
        {img && (
          <img
            src={driveApi.imageUrl(img.id)}
            alt={img.name}
            style={{ maxWidth: '90%', maxHeight: 520, objectFit: 'contain', display: 'block' }}
          />
        )}
        <ActionIcon
          variant="default"
          size="lg"
          pos="absolute"
          right={0}
          top="50%"
          onClick={next}
          aria-label="Next"
        >
          <IconChevronRight />
        </ActionIcon>
      </Box>

      {img && (
        <Text ta="center" c="dimmed" size="xs" mt="sm">
          {img.name.replace(/\.[^/.]+$/, '')}
        </Text>
      )}
    </Paper>
  );
}

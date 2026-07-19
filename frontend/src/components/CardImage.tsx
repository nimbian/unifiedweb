// Layered, tiltable card image. Transparent PNGs are stacked and given
// increasing translateZ so they parallax in 3D. Click-drag rotates the card
// freely through a full 360° on both axes; a moving glare fakes a holographic
// sheen. Each front layer (and the glare) is back-face-culled, so spinning past
// 90° hides them and reveals a single shared card back (cards/back.png).
//
// Layer order (bottom -> top): Color, Holo, Cards, Grade — the holo pattern sits
// *under* the card art so it shimmers through. For now the layers (and whether a
// card is holo at all) are randomized, but seeded by the card id so each card
// looks consistent across opens.

import { useMemo, useRef, useState } from 'react';
import { Box, Button, Center, Group, Loader, Text } from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { cardsApi } from '@/api/cards';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api';
const url = (sub: string, file: string) => `${API_BASE}/cards/${sub}/${file}`;
const BACK_URL = `${API_BASE}/cards/back.png`;

// The card's physical thickness, in px. The front art sits at +DEPTH/2, the back
// at -DEPTH/2, and the gap between them is filled by a short stack of rounded
// card-silhouette slices so the card reads as a real (thin) object with edges
// that follow the same rounded corners as the faces.
const DEPTH = 1;
// Number of body slices spanning the depth. More = smoother edge, but a handful
// is plenty at this thickness.
const SLICES = 14;
// Corner radius shared by the faces and every body slice, so the extruded edge
// curves to match the card corners.
const RADIUS = '5%';
// Card-stock colour for the extruded edge (light, like a real card's edge).
const EDGE_COLOR = '#e3ddd0';

// Angular distance (0–180°) of an angle from facing straight-on — how far the
// front of the card is turned away. Drives the glare so it fades as you spin to
// the back.
const facingTilt = (deg: number) => {
  const m = ((deg % 360) + 360) % 360;
  return m > 180 ? 360 - m : m;
};

// Tiny deterministic PRNG so a given card id always yields the same look.
function mulberry32(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const pick = <T,>(arr: T[], r: number): T => arr[Math.floor(r * arr.length)];

export function CardImage({ collectionId, width = 320 }: { collectionId: number; width?: number }) {
  const { data: manifest, isLoading } = useQuery({
    queryKey: ['card-layers'],
    queryFn: cardsApi.layers,
    staleTime: 60 * 60 * 1000,
  });

  // Seeded, per-card layer selection (Color, optional Holo, Cards, Grade).
  const layers = useMemo<string[]>(() => {
    if (!manifest) return [];
    const rnd = mulberry32(collectionId || 1);
    const rColor = rnd();
    const rHoloOn = rnd();
    const rHolo = rnd();
    const rCard = rnd();
    const rGrade = rnd();

    const out: string[] = [];
    if (manifest.color.length) out.push(url('Color', pick(manifest.color, rColor)));
    if (rHoloOn < 0.5 && manifest.holo.length) out.push(url('Holo', pick(manifest.holo, rHolo)));
    if (manifest.cards.length) out.push(url('Cards', pick(manifest.cards, rCard)));
    if (manifest.grade.length) out.push(url('Grade', pick(manifest.grade, rGrade)));
    return out;
  }, [manifest, collectionId]);

  const [rot, setRot] = useState({ x: 0, y: 0 });
  const dragging = useRef(false);
  const last = useRef({ x: 0, y: 0 });

  const onPointerDown = (e: React.PointerEvent) => {
    dragging.current = true;
    last.current = { x: e.clientX, y: e.clientY };
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent) => {
    if (!dragging.current) return;
    const dx = e.clientX - last.current.x;
    const dy = e.clientY - last.current.y;
    last.current = { x: e.clientX, y: e.clientY };
    // Unclamped: rotation accumulates so the card can spin a full 360° either way
    // (drag down -> top tilts away; drag sideways -> spins toward the back).
    setRot((r) => ({ x: r.x - dy * 0.4, y: r.y + dx * 0.4 }));
  };
  const stop = () => {
    dragging.current = false;
  };

  if (isLoading || layers.length === 0) {
    return (
      <Center w={width} h={width * 1.4}>
        <Loader />
      </Center>
    );
  }

  const glareOpacity = Math.min(0.85, (facingTilt(rot.x) + facingTilt(rot.y)) / 90 + 0.12);

  // Which side faces the viewer. The card's surface normal points toward us while
  // cos(rotX)·cos(rotY) >= 0; once it goes negative the card has been spun more
  // than a quarter turn and we should be looking at its back. We toggle this in
  // JS rather than relying on CSS `backface-visibility`, which the stacked
  // translateZ layers flatten away in some browsers (front showed mirrored).
  const rad = Math.PI / 180;
  const frontFacing = Math.cos(rot.x * rad) * Math.cos(rot.y * rad) >= 0;

  return (
    <Box>
      <Box
        style={{
          width,
          // Vertical/horizontal room so the 3D-tilted card edges aren't clipped
          // by the modal (the rotated top/bottom can extend well past the box).
          padding: '90px 40px',
          userSelect: 'none',
          touchAction: 'none',
          margin: '0 auto',
        }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={stop}
        onPointerCancel={stop}
      >
        <div
          style={{
            position: 'relative',
            transformStyle: 'preserve-3d',
            // Perspective is applied here (rather than on the parent) as the
            // single-element pattern — most robust against the surrounding context
            // being flattened. Nothing inside this subtree may use a grouping
            // property (opacity<1, filter, mix-blend-mode, overflow≠visible) or the
            // browser collapses every layer/edge to z=0 and the 3D is lost.
            transform: `perspective(1100px) rotateX(${rot.x}deg) rotateY(${rot.y}deg)`,
            transition: dragging.current ? 'none' : 'transform 250ms ease-out',
            cursor: 'grab',
          }}
        >
          {/* Extruded body — a stack of rounded card-silhouette slices filling the
              depth. Each shares the faces' corner radius, so the edge curves to
              match the corners. Always present; the opaque front/back art sits in
              front of it on each side and hides it until the card is angled. */}
          {Array.from({ length: SLICES + 1 }, (_, k) => (
            <div
              key={`slice-${k}`}
              style={{
                position: 'absolute',
                inset: 0,
                borderRadius: RADIUS,
                background: EDGE_COLOR,
                transform: `translateZ(${-DEPTH / 2 + (DEPTH * k) / SLICES}px)`,
                pointerEvents: 'none',
              }}
            />
          ))}

          {layers.map((src, i) => (
            <img
              key={src}
              src={src}
              alt=""
              draggable={false}
              style={{
                display: 'block',
                width: '100%',
                // First layer is in normal flow (defines the box size); the rest
                // overlay it. The whole stack sits flat on the front face (+DEPTH/2).
                position: i === 0 ? 'relative' : 'absolute',
                inset: i === 0 ? undefined : 0,
                transform: `translateZ(${DEPTH / 2}px)`,
                borderRadius: RADIUS,
                // Hidden once the card turns past a quarter turn, so the front
                // vanishes and the back face shows through. `visibility` (not
                // display) keeps the first layer's box, preserving size.
                visibility: frontFacing ? 'visible' : 'hidden',
              }}
            />
          ))}

          {/* Shared card back — pushed to the back face (-DEPTH/2) and pre-flipped
              180° so it reads upright once the card has been spun around. Shown
              only while the back faces us. */}
          <img
            src={BACK_URL}
            alt=""
            draggable={false}
            style={{
              display: 'block',
              width: '100%',
              position: 'absolute',
              inset: 0,
              transform: `translateZ(${-DEPTH / 2}px) rotateY(180deg)`,
              visibility: frontFacing ? 'hidden' : 'visible',
              borderRadius: RADIUS,
            }}
          />

          {/* Holographic glare — a hotspot that tracks the tilt. Culled with the
              front so it never bleeds onto the card back. NOTE: no `mix-blend-mode`
              or `opacity` here — both are "grouping" properties that would flatten
              the whole preserve-3d context (killing the layer depth and edges), so
              the sheen strength is baked into the gradient's alpha instead. */}
          <div
            style={{
              position: 'absolute',
              inset: 0,
              transform: `translateZ(${DEPTH / 2 + 1}px)`,
              pointerEvents: 'none',
              borderRadius: RADIUS,
              visibility: frontFacing ? 'visible' : 'hidden',
              background: `radial-gradient(circle at ${50 + rot.y * 1.6}% ${50 - rot.x * 1.6}%, rgba(255,255,255,${(0.75 * glareOpacity).toFixed(3)}), rgba(255,255,255,0) 45%)`,
            }}
          />
        </div>
      </Box>

      <Group justify="center" mt="md" gap="sm">
        <Text size="xs" c="dimmed">
          Drag to rotate
        </Text>
        <Button
          size="xs"
          variant="subtle"
          onClick={() => setRot((r) => ({ ...r, y: r.y + 180 }))}
        >
          Flip
        </Button>
        <Button size="xs" variant="subtle" onClick={() => setRot({ x: 0, y: 0 })}>
          Reset
        </Button>
      </Group>
    </Box>
  );
}

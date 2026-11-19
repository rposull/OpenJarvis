import { useEffect, useMemo, useRef, useState } from 'react';

export type GraphNode = { id: string; label: string; group: string };
export type GraphLink = { source: string; target: string; kind?: string };

type SimNode = GraphNode & { x: number; y: number; vx: number; vy: number };

const GROUP_COLORS: Record<string, string> = {
  note: '#5ce1ff',
  concept: '#9d7cff',
  code: '#e056fd',
  default: '#6ee7b7',
};

function groupColor(group: string) {
  return GROUP_COLORS[group] ?? GROUP_COLORS.default;
}

function simulate(
  nodes: SimNode[],
  links: GraphLink[],
  width: number,
  height: number,
  reducedMotion: boolean,
) {
  const cx = width / 2;
  const cy = height / 2;
  const iterations = reducedMotion ? 24 : 90;
  const linkById = new Map<string, SimNode>();
  nodes.forEach((n) => linkById.set(n.id, n));

  for (let step = 0; step < iterations; step++) {
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i];
        const b = nodes[j];
        let dx = a.x - b.x;
        let dy = a.y - b.y;
        const dist = Math.max(Math.hypot(dx, dy), 0.01);
        const force = 4200 / (dist * dist);
        dx = (dx / dist) * force;
        dy = (dy / dist) * force;
        a.vx += dx;
        a.vy += dy;
        b.vx -= dx;
        b.vy -= dy;
      }
    }

    for (const link of links) {
      const a = linkById.get(link.source);
      const b = linkById.get(link.target);
      if (!a || !b) continue;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const dist = Math.max(Math.hypot(dx, dy), 0.01);
      const force = (dist - 72) * 0.035;
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;
      a.vx += fx;
      a.vy += fy;
      b.vx -= fx;
      b.vy -= fy;
    }

    for (const n of nodes) {
      n.vx += (cx - n.x) * 0.002;
      n.vy += (cy - n.y) * 0.002;
      n.vx *= 0.78;
      n.vy *= 0.78;
      n.x += n.vx;
      n.y += n.vy;
      n.x = Math.max(28, Math.min(width - 28, n.x));
      n.y = Math.max(28, Math.min(height - 28, n.y));
    }
  }
}

export function ForceKnowledgeGraph({
  nodes,
  links,
  height = 380,
}: {
  nodes: GraphNode[];
  links: GraphLink[];
  height?: number;
}) {
  const width = 820;
  const reducedMotion = useMemo(
    () => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    [],
  );

  const [sim, setSim] = useState<SimNode[]>([]);
  const rafRef = useRef(0);
  const tickRef = useRef(0);

  useEffect(() => {
    if (!nodes.length) {
      setSim([]);
      return;
    }

    const seeded: SimNode[] = nodes.map((n, i) => {
      const angle = (i / Math.max(nodes.length, 1)) * Math.PI * 2;
      const r = 40 + (i % 5) * 14;
      return {
        ...n,
        x: width / 2 + Math.cos(angle) * r,
        y: height / 2 + Math.sin(angle) * r,
        vx: 0,
        vy: 0,
      };
    });

    simulate(seeded, links, width, height, reducedMotion);
    setSim(seeded.map((n) => ({ ...n })));

    if (reducedMotion) return undefined;

    tickRef.current = 0;
    const breathe = () => {
      tickRef.current += 1;
      if (tickRef.current % 4 === 0 && seeded.length < 120) {
        simulate(seeded, links, width, height, false);
        setSim(seeded.map((n) => ({ ...n })));
      }
      if (tickRef.current < 180) {
        rafRef.current = requestAnimationFrame(breathe);
      }
    };
    rafRef.current = requestAnimationFrame(breathe);

    return () => cancelAnimationFrame(rafRef.current);
  }, [nodes, links, height, reducedMotion]);

  const pos = useMemo(() => {
    const map: Record<string, SimNode> = {};
    sim.forEach((n) => {
      map[n.id] = n;
    });
    return map;
  }, [sim]);

  if (!nodes.length) return null;

  return (
    <svg
      className="vault-graph-svg"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="Knowledge graph visualization"
      style={{ minHeight: height }}
    >
      <defs>
        <radialGradient id="vault-core-glow" cx="50%" cy="45%" r="55%">
          <stop offset="0%" stopColor="rgba(157,124,255,0.22)" />
          <stop offset="100%" stopColor="rgba(0,0,0,0)" />
        </radialGradient>
        <filter id="vault-node-glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      <rect width={width} height={height} fill="url(#vault-core-glow)" />
      {links.map((l, i) => {
        const a = pos[l.source];
        const b = pos[l.target];
        if (!a || !b) return null;
        return (
          <line
            key={`${l.source}-${l.target}-${i}`}
            x1={a.x}
            y1={a.y}
            x2={b.x}
            y2={b.y}
            stroke="rgba(92,225,255,0.22)"
            strokeWidth={1}
          />
        );
      })}
      {sim.map((n) => {
        const fill = groupColor(n.group);
        return (
          <g key={n.id} filter="url(#vault-node-glow)">
            <circle cx={n.x} cy={n.y} r={11} fill={fill} fillOpacity={0.28} stroke={fill} strokeWidth={1.25} />
            <circle cx={n.x} cy={n.y} r={4} fill={fill} fillOpacity={0.95} />
            <text
              x={n.x}
              y={n.y + 22}
              textAnchor="middle"
              fill="rgba(232,244,255,0.88)"
              fontSize={10}
              fontFamily="Share Tech Mono, monospace"
            >
              {n.label.length > 22 ? `${n.label.slice(0, 20)}…` : n.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
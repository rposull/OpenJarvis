import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router';
import { motion } from 'motion/react';
import {
  Brain,
  Database,
  GitBranch,
  HardDrive,
  Loader2,
  Orbit,
  RefreshCw,
  Search,
  Sparkles,
  Upload,
  Zap,
} from 'lucide-react';
import {
  fetchKnowledgeStack,
  fetchObsidianDesk,
  getMemoryConfig,
  getMemoryStats,
  runGraphify,
  searchMemory,
  type KnowledgeStack,
  type MemoryConfig,
  type MemorySearchResult,
  type MemoryStats,
  type ObsidianDesk,
} from '../lib/api';
import { listConnectors } from '../lib/connectors-api';
import { ForceKnowledgeGraph } from '../components/NeuralVault/ForceKnowledgeGraph';
import '../styles/neural-vault.css';

function relevancePercent(score: number) {
  const pct = Math.min(100, Math.max(4, Math.round(score * 100)));
  return pct;
}

export function NeuralVaultPage() {
  const [desk, setDesk] = useState<ObsidianDesk | null>(null);
  const [stack, setStack] = useState<KnowledgeStack | null>(null);
  const [memoryStats, setMemoryStats] = useState<MemoryStats | null>(null);
  const [memoryConfig, setMemoryConfig] = useState<MemoryConfig | null>(null);
  const [connectorChunks, setConnectorChunks] = useState(0);
  const [connectedSources, setConnectedSources] = useState(0);

  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState('');

  const [query, setQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<MemorySearchResult[]>([]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [d, s, stats, cfg, connectors] = await Promise.all([
        fetchObsidianDesk(),
        fetchKnowledgeStack(),
        getMemoryStats().catch(() => ({ entries: 0, backend: 'offline' } as MemoryStats)),
        getMemoryConfig().catch(() => null),
        listConnectors().catch(() => []),
      ]);
      setDesk(d);
      setStack(s);
      setMemoryStats(stats);
      setMemoryConfig(cfg);
      const connected = connectors.filter((c) => c.connected);
      setConnectedSources(connected.length);
      setConnectorChunks(
        connected.reduce((sum, c) => sum + (c.chunks ?? 0), 0),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load neural vault');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, 45000);
    return () => window.clearInterval(id);
  }, [refresh]);

  const runSearch = useCallback(async () => {
    const q = query.trim();
    if (!q) {
      setResults([]);
      return;
    }
    setSearching(true);
    setError('');
    try {
      const hits = await searchMemory(q, 12);
      setResults(hits);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Memory search failed');
    } finally {
      setSearching(false);
    }
  }, [query]);

  useEffect(() => {
    const t = window.setTimeout(() => {
      if (query.trim().length >= 2) void runSearch();
    }, 320);
    return () => window.clearTimeout(t);
  }, [query, runSearch]);

  const graph = desk?.graph;
  const vault = desk?.vault;

  const totalRecords = useMemo(() => {
    const mem = memoryStats?.entries ?? 0;
    const notes = vault?.note_count ?? 0;
    const graphNodes = graph?.nodes?.length ?? 0;
    return { mem, notes, graphNodes, chunks: connectorChunks };
  }, [memoryStats, vault, graph, connectorChunks]);

  const backendLabel = memoryStats?.backend ?? '—';
  const memoryLive = memoryConfig?.available !== false && (memoryStats?.entries ?? 0) >= 0;

  return (
    <div className="flex-1 overflow-y-auto px-5 py-8 sm:px-8 vault-page">
      <div className="vault-scanline" aria-hidden />
      <div className="max-w-6xl mx-auto relative z-10">
        <div className="flex flex-wrap items-start justify-between gap-4 mb-8">
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
          >
            <p className="vault-display text-[11px] mb-2" style={{ color: 'var(--vault-cyan)' }}>
              Local-first · On-device
            </p>
            <h1
              className="vault-display text-2xl sm:text-3xl font-semibold flex items-center gap-3"
              style={{ color: 'var(--vault-ink)' }}
            >
              <Orbit size={28} style={{ color: 'var(--vault-violet)' }} />
              Neural Vault
            </h1>
            <p className="text-sm mt-2 max-w-xl leading-relaxed" style={{ color: 'var(--vault-muted)' }}>
              Your Jarvis memory, connector index, and knowledge graph — one holographic console. Nothing leaves this
              machine unless you connect a cloud source.
            </p>
          </motion.div>

          <div className="flex flex-wrap items-center gap-2">
            <Link
              to="/data-sources"
              className="vault-chip text-xs no-underline hover:opacity-90"
              style={{ padding: '0.45rem 0.75rem' }}
            >
              <Upload size={12} />
              Ingest data
            </Link>
            <button
              type="button"
              disabled={loading || syncing}
              className="vault-chip text-xs cursor-pointer disabled:opacity-50"
              style={{ padding: '0.45rem 0.75rem', background: 'rgba(157,124,255,0.12)', borderColor: 'rgba(157,124,255,0.35)' }}
              onClick={async () => {
                setSyncing(true);
                setError('');
                try {
                  await runGraphify();
                  await refresh();
                } catch (e) {
                  setError(e instanceof Error ? e.message : 'Graphify sync failed');
                } finally {
                  setSyncing(false);
                }
              }}
            >
              <RefreshCw size={12} className={syncing ? 'animate-spin' : ''} />
              Sync graphify
            </button>
          </div>
        </div>

        <motion.section
          className="vault-hero p-6 mb-6"
          initial={{ opacity: 0, scale: 0.985 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
        >
          <div className="vault-hero-glow" aria-hidden />
          <div className="relative z-10 grid sm:grid-cols-2 lg:grid-cols-4 gap-6">
            <h2 className="sr-only">Vault telemetry</h2>
            <div className="vault-metric">
              <p className="text-[10px] uppercase tracking-widest mb-1" style={{ color: 'var(--vault-muted)' }}>
                Memory shards
              </p>
              <p className="vault-metric-value">{totalRecords.mem.toLocaleString()}</p>
              <p className="text-xs mt-1 font-mono" style={{ color: 'var(--vault-muted)' }}>
                {backendLabel} · {memoryLive ? 'online' : 'degraded'}
              </p>
            </div>
            <div className="vault-metric">
              <p className="text-[10px] uppercase tracking-widest mb-1" style={{ color: 'var(--vault-muted)' }}>
                Knowledge chunks
              </p>
              <p className="vault-metric-value">{totalRecords.chunks.toLocaleString()}</p>
              <p className="text-xs mt-1" style={{ color: 'var(--vault-muted)' }}>
                {connectedSources} connector{connectedSources === 1 ? '' : 's'} linked
              </p>
            </div>
            <div className="vault-metric">
              <p className="text-[10px] uppercase tracking-widest mb-1" style={{ color: 'var(--vault-muted)' }}>
                Graph nodes
              </p>
              <p className="vault-metric-value">{totalRecords.graphNodes.toLocaleString()}</p>
              <p className="text-xs mt-1" style={{ color: 'var(--vault-muted)' }}>
                {graph?.source ?? 'awaiting sync'}
              </p>
            </div>
            <div className="vault-metric">
              <p className="text-[10px] uppercase tracking-widest mb-1" style={{ color: 'var(--vault-muted)' }}>
                Vault notes
              </p>
              <p className="vault-metric-value">{totalRecords.notes.toLocaleString()}</p>
              <p className="text-xs mt-1 truncate max-w-[200px] font-mono" style={{ color: 'var(--vault-muted)' }}>
                {vault?.path ?? '~/.openjarvis'}
              </p>
            </div>
          </div>
        </motion.section>

        {error && (
          <div className="vault-panel p-3 mb-4 text-sm" style={{ color: '#ff8fab', borderColor: 'rgba(255,100,120,0.35)' }}>
            {error}
          </div>
        )}

        <div className="grid lg:grid-cols-5 gap-4 mb-6">
          <div className="lg:col-span-2 vault-panel p-4 flex flex-col min-h-[420px]">
            <div className="flex items-center gap-2 mb-3">
              <Brain size={16} style={{ color: 'var(--vault-cyan)' }} />
              <h2 className="text-sm font-semibold vault-display text-[11px]" style={{ color: 'var(--vault-violet)' }}>
                Semantic recall
              </h2>
              {searching && <Loader2 size={14} className="animate-spin ml-auto" style={{ color: 'var(--vault-cyan)' }} />}
            </div>
            <div className="relative mb-3">
              <Search
                size={15}
                className="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none"
                style={{ color: 'var(--vault-muted)' }}
              />
              <input
                type="search"
                className="vault-search"
                placeholder="Query memory in plain English…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && void runSearch()}
                aria-label="Search local memory"
              />
            </div>
            <p className="text-[11px] mb-3" style={{ color: 'var(--vault-muted)' }}>
              FTS-backed SQLite on this PC. Chat context pulls from the same index when memory is enabled in Settings.
            </p>
            <div className="flex-1 overflow-y-auto space-y-2 pr-1">
              {results.length === 0 && (
                <div
                  className="flex flex-col items-center justify-center h-full min-h-[200px] text-center px-4"
                  style={{ color: 'var(--vault-muted)' }}
                >
                  <Zap size={22} className="mb-2 opacity-60" />
                  <p className="text-sm">Type a phrase to illuminate matching shards.</p>
                </div>
              )}
              {results.map((row, i) => {
                const pct = relevancePercent(row.score ?? 0);
                return (
                  <motion.div
                    key={`${i}-${row.content.slice(0, 24)}`}
                    className="vault-shard"
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.04, duration: 0.35 }}
                  >
                    <div className="flex items-center justify-between gap-2 mb-2">
                      <span className="vault-chip">shard · {pct}% match</span>
                      {row.metadata?.source ? (
                        <span className="text-[10px] truncate font-mono" style={{ color: 'var(--vault-muted)' }}>
                          {String(row.metadata.source)}
                        </span>
                      ) : null}
                    </div>
                    <p className="text-sm leading-relaxed" style={{ color: 'var(--vault-ink)' }}>
                      {row.content.length > 420 ? `${row.content.slice(0, 417)}…` : row.content}
                    </p>
                    <div className="vault-score-bar mt-2">
                      <div className="vault-score-fill" style={{ width: `${pct}%` }} />
                    </div>
                  </motion.div>
                );
              })}
            </div>
          </div>

          <div className="lg:col-span-3 vault-panel p-4">
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-sm font-semibold flex items-center gap-2 vault-display text-[11px]" style={{ color: 'var(--vault-violet)' }}>
                <GitBranch size={16} />
                Knowledge constellation
              </h2>
              {loading && <Sparkles size={14} className="animate-pulse" style={{ color: 'var(--vault-cyan)' }} />}
            </div>
            <div className="vault-graph-frame">
              {graph && graph.nodes.length > 0 ? (
                <ForceKnowledgeGraph nodes={graph.nodes} links={graph.links} height={400} />
              ) : (
                <div
                  className="flex flex-col items-center justify-center text-sm px-6 text-center"
                  style={{ minHeight: 400, color: 'var(--vault-muted)' }}
                >
                  <HardDrive size={24} className="mb-3 opacity-50" />
                  <p>Graph empty — run Sync graphify or add notes to your vault.</p>
                  <p className="text-xs mt-2 font-mono">{vault?.path}</p>
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="grid md:grid-cols-2 gap-4">
          <motion.div
            className="vault-panel p-4"
            initial={{ opacity: 0, y: 8 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
          >
            <h2 className="text-sm font-semibold mb-3 flex items-center gap-2" style={{ color: 'var(--vault-violet)' }}>
              <Database size={16} />
              Recent vault notes
            </h2>
            <div className="space-y-1 max-h-[220px] overflow-y-auto">
              {(vault?.recent_notes ?? []).map((note) => (
                <div key={note.path} className="vault-note-row">
                  <p className="text-sm font-medium truncate" style={{ color: 'var(--vault-ink)' }}>
                    {note.title}
                  </p>
                  <p className="text-xs truncate mt-0.5" style={{ color: 'var(--vault-muted)' }}>
                    {note.preview}
                  </p>
                </div>
              ))}
              {!vault?.recent_notes?.length && (
                <p className="text-xs" style={{ color: 'var(--vault-muted)' }}>
                  No markdown in vault yet.
                </p>
              )}
            </div>
          </motion.div>

          <motion.div
            className="vault-panel p-4"
            initial={{ opacity: 0, y: 8 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
          >
            <h2 className="text-sm font-semibold mb-3 flex items-center gap-2" style={{ color: 'var(--vault-violet)' }}>
              <Sparkles size={16} />
              Knowledge stack
            </h2>
            <div className="grid sm:grid-cols-2 gap-2">
              {(desk?.tools ?? stack?.tools ?? []).map((tool) => (
                <div
                  key={tool.id}
                  className="vault-note-row"
                  style={{
                    borderColor: tool.active || tool.installed ? 'rgba(92,225,255,0.2)' : 'transparent',
                  }}
                >
                  <p className="text-sm font-medium" style={{ color: 'var(--vault-ink)' }}>
                    {tool.label}
                    <span
                      className="ml-2 text-[10px] uppercase vault-chip"
                      style={{
                        padding: '0.1rem 0.4rem',
                        opacity: tool.active || tool.installed ? 1 : 0.55,
                      }}
                    >
                      {tool.active || tool.installed ? 'armed' : 'setup'}
                    </span>
                  </p>
                  <p className="text-xs mt-0.5" style={{ color: 'var(--vault-muted)' }}>
                    {tool.role}
                  </p>
                </div>
              ))}
            </div>
          </motion.div>
        </div>
      </div>
    </div>
  );
}
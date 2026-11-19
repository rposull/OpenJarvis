import { useEffect, useState } from 'react';
import { motion } from 'motion/react';
import { Mic, MicOff } from 'lucide-react';
import { fetchSpeechHealth } from '../../lib/api';
import { useAppStore } from '../../lib/store';
import type { VoicePhase } from '../../lib/dashboard/types';
import { subscribeVoiceStatus } from '../../lib/voiceStatus';
import { HudPanel } from './HudPanel';

const phases: { key: VoicePhase; label: string }[] = [
  { key: 'listening', label: 'Listening' },
  { key: 'thinking', label: 'Thinking' },
  { key: 'speaking', label: 'Speaking' },
  { key: 'offline', label: 'Offline' },
];

function WaveBars({ active }: { active: boolean }) {
  return (
    <div className="flex h-10 items-end justify-center gap-1">
      {Array.from({ length: 12 }).map((_, i) => (
        <motion.div
          key={i}
          className="w-1 rounded-full bg-[var(--at-lime)]"
          animate={
            active
              ? { height: [6, 18 + (i % 4) * 6, 8, 22 - (i % 3) * 4, 6] }
              : { height: 4, opacity: 0.25 }
          }
          transition={
            active
              ? { duration: 0.9, repeat: Infinity, delay: i * 0.05, ease: 'easeInOut' }
              : { duration: 0.2 }
          }
        />
      ))}
    </div>
  );
}

export function VoiceStatusPanel() {
  const [speechAvailable, setSpeechAvailable] = useState<boolean | null>(null);
  const [phase, setPhase] = useState<VoicePhase>('idle');
  const isStreaming = useAppStore((s) => s.streamState.isStreaming);

  useEffect(() => {
    fetchSpeechHealth()
      .then((h) => setSpeechAvailable(h.available))
      .catch(() => setSpeechAvailable(false));
  }, []);

  useEffect(() => subscribeVoiceStatus(setPhase), []);

  const resolvedPhase: VoicePhase = !speechAvailable
    ? 'offline'
    : phase === 'idle' && isStreaming
      ? 'thinking'
      : phase === 'idle'
        ? 'idle'
        : phase;

  const waveformActive = resolvedPhase === 'listening' || resolvedPhase === 'speaking';

  return (
    <HudPanel title="Voice Assistant" subtitle="Audio interface status">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div
            className={`flex h-10 w-10 items-center justify-center rounded-full border ${
              resolvedPhase === 'offline'
                ? 'border-[rgba(200,245,66,0.2)] bg-black/40 text-[var(--at-muted)]'
                : 'border-[rgba(200,245,66,0.4)] bg-[rgba(200,245,66,0.1)] text-[var(--at-lime)] shadow-[0_0_16px_rgba(200,245,66,0.25)]'
            }`}
          >
            {resolvedPhase === 'offline' ? <MicOff className="h-5 w-5" /> : <Mic className="h-5 w-5" />}
          </div>
          <div>
            <div className="font-[family-name:var(--font-hud)] text-sm text-[var(--at-ink)]">
              {resolvedPhase === 'idle' ? 'Standby' : phases.find((p) => p.key === resolvedPhase)?.label}
            </div>
            <div className="text-[11px] text-[var(--at-muted)]">
              {speechAvailable ? 'STT / TTS linked' : 'Speech backend unavailable'}
            </div>
          </div>
        </div>

        <WaveBars active={waveformActive} />
      </div>

      <div className="mt-4 grid grid-cols-4 gap-2">
        {phases.map((item) => {
          const active = resolvedPhase === item.key;
          return (
            <div
              key={item.key}
              className={`rounded-lg border px-2 py-2 text-center text-[10px] uppercase tracking-wider ${
                active
                  ? 'border-[rgba(200,245,66,0.5)] bg-[rgba(200,245,66,0.15)] text-[var(--at-ink)]'
                  : 'border-[rgba(200,245,66,0.1)] bg-black/20 text-[var(--at-muted)]'
              }`}
            >
              {item.label}
            </div>
          );
        })}
      </div>
    </HudPanel>
  );
}

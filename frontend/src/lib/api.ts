import type { ModelInfo, SavingsData, ServerInfo } from '../types';

// ---------------------------------------------------------------------------
// Supabase config — safe to embed (RLS protects writes)
// ---------------------------------------------------------------------------

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL || 'https://mtbtgpwzrbostweaanpr.supabase.co';
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY || 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im10YnRncHd6cmJvc3R3ZWFhbnByIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzMxODk0OTQsImV4cCI6MjA4ODc2NTQ5NH0._xMlqCfljtXpwPj54H-ghxfLFO-jiq4W2WhpU8vVL1c';

declare global {
  interface Window {
    __TAURI_INTERNALS__?: unknown;
  }
}

export const isTauri = () => typeof window !== 'undefined' && !!window.__TAURI_INTERNALS__;

// Cached API base URL fetched from the Tauri backend at startup.
// This avoids hardcoding the port — the Rust backend is the single
// source of truth for JARVIS_PORT.
let _tauriApiBase: string | null = null;

/** Pre-fetch the API base URL from the Tauri backend (call once at init). */
export async function initApiBase(): Promise<void> {
  if (!isTauri()) return;
  try {
    const { invoke } = await import('@tauri-apps/api/core');
    _tauriApiBase = await invoke<string>('get_api_base');
  } catch {
    // Command may not exist on older builds; fall through to default.
  }
}

const DESKTOP_API_FALLBACK = 'http://127.0.0.1:8000';

const getSettingsApiUrl = (): string => {
  try {
    const raw = localStorage.getItem('openjarvis-settings');
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed.apiUrl) return parsed.apiUrl.replace(/\/+$/, '');
    }
  } catch {}
  return '';
};

export const getBase = (): string => {
  const settingsUrl = getSettingsApiUrl();
  if (settingsUrl) return settingsUrl;
  if (import.meta.env.VITE_API_URL) return import.meta.env.VITE_API_URL;
  if (isTauri()) return _tauriApiBase || DESKTOP_API_FALLBACK;
  return '';
};

// Resolve the local server API key (OPENJARVIS_API_KEY). When `jarvis serve`
// is started with a key, AuthMiddleware 401s every /v1 and /api request that
// lacks a Bearer token — so the frontend must send it (#266). Sourced from the
// same settings blob as the API URL, with an optional build-time env override.
// Returns '' when unset, so a keyless local server keeps working unchanged.
export const getApiKey = (): string => {
  try {
    const raw = localStorage.getItem('openjarvis-settings');
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed.apiKey) return String(parsed.apiKey);
    }
  } catch {}
  if (import.meta.env.VITE_OPENJARVIS_API_KEY) {
    return import.meta.env.VITE_OPENJARVIS_API_KEY as string;
  }
  return '';
};

// Build request headers with the Bearer Authorization token when a local key
// is configured, merging any caller-supplied headers. Adds no Authorization
// header when no key is set, so keyless local dev is byte-for-byte unchanged.
export const authHeaders = (
  extra: Record<string, string> = {},
): Record<string, string> => {
  const key = getApiKey();
  return key ? { ...extra, Authorization: `Bearer ${key}` } : { ...extra };
};

// Centralized fetch for the local server: prepends getBase() and injects the
// Bearer auth header (when a key is set) on every call. Using this everywhere
// guarantees no /v1 or /api request is sent without auth — the bug in #266 was
// that direct fetch() calls omitted the header and 401'd. `path` is the
// server-relative path (e.g. "/v1/savings").
export const apiFetch = (
  path: string,
  init: RequestInit = {},
): Promise<Response> => {
  const headers = authHeaders(
    (init.headers as Record<string, string> | undefined) ?? {},
  );
  return fetch(`${getBase()}${path}`, { ...init, headers });
};

async function tauriInvoke<T>(command: string, args: Record<string, unknown> = {}): Promise<T> {
  const { invoke } = await import('@tauri-apps/api/core');
  const apiUrl = getBase();
  return invoke<T>(command, { apiUrl, ...args });
}

// ---------------------------------------------------------------------------
// Setup status (desktop only)
// ---------------------------------------------------------------------------

export interface SetupStatus {
  phase: string;
  detail: string;
  ollama_ready: boolean;
  server_ready: boolean;
  model_ready: boolean;
  error: string | null;
  source?: 'ollama' | 'custom'; // drives source-aware setup labels
}

export async function getSetupStatus(): Promise<SetupStatus | null> {
  if (!isTauri()) return null;
  try {
    const { invoke } = await import('@tauri-apps/api/core');
    return await invoke<SetupStatus>('get_setup_status');
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export async function fetchModels(): Promise<ModelInfo[]> {
  if (isTauri()) {
    try {
      const result = await tauriInvoke<{ data?: ModelInfo[] }>('fetch_models');
      return result?.data || [];
    } catch {
      // Fall through to fetch
    }
  }
  const res = await apiFetch(`/v1/models`);
  if (!res.ok) throw new Error(`Failed to fetch models: ${res.status}`);
  const data = await res.json();
  return data.data || [];
}

export async function fetchRecommendedModel(): Promise<{ model: string; reason: string }> {
  const res = await apiFetch(`/v1/recommended-model`);
  if (!res.ok) return { model: '', reason: 'Failed to fetch' };
  return res.json();
}

export async function pullModel(modelName: string): Promise<void> {
  // In Tauri, go through the Rust backend directly (avoids CORS / timeout
  // issues with long model downloads via fetch).
  if (isTauri()) {
    try {
      const { invoke } = await import('@tauri-apps/api/core');
      await invoke('pull_ollama_model', { modelName });
      return;
    } catch (e: any) {
      throw new Error(e?.message || e || 'Download failed');
    }
  }
  const res = await apiFetch(`/v1/models/pull`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: modelName }),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`Failed to pull model: ${detail}`);
  }
}

export async function deleteModel(modelName: string): Promise<void> {
  if (isTauri()) {
    try {
      const { invoke } = await import('@tauri-apps/api/core');
      await invoke('delete_ollama_model', { modelName });
      return;
    } catch (e: any) {
      throw new Error(e?.message || e || 'Delete failed');
    }
  }
  const res = await apiFetch(`/v1/models/${encodeURIComponent(modelName)}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`Failed to delete model: ${detail}`);
  }
}

const _CLOUD_PREFIXES = ['gpt-', 'o1-', 'o3-', 'o4-', 'claude-', 'gemini-', 'openrouter/'];

export async function preloadModel(modelName: string): Promise<void> {
  // Cloud models don't need Ollama preloading
  if (_CLOUD_PREFIXES.some(p => modelName.startsWith(p))) {
    return;
  }
  // Trigger Ollama to load the model into memory (empty prompt, no generation).
  const ollamaUrl = 'http://127.0.0.1:11434';
  try {
    const res = await fetch(`${ollamaUrl}/api/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: modelName, prompt: '', keep_alive: '5m' }),
      signal: AbortSignal.timeout(120_000),
    });
    if (!res.ok) throw new Error(`Preload failed: ${res.status}`);
  } catch (e: any) {
    if (e.name === 'TimeoutError') throw new Error('Model load timed out (120s)');
    throw e;
  }
}

export async function fetchSavings(): Promise<SavingsData> {
  const res = await apiFetch(`/v1/savings`);
  if (!res.ok) throw new Error(`Failed to fetch savings: ${res.status}`);
  return res.json();
}

export async function fetchServerInfo(): Promise<ServerInfo> {
  const res = await apiFetch(`/v1/info`);
  if (!res.ok) throw new Error(`Failed to fetch server info: ${res.status}`);
  return res.json();
}

export async function checkHealth(): Promise<boolean> {
  if (isTauri()) {
    try {
      await tauriInvoke('check_health', { apiUrl: getBase() });
      return true;
    } catch {
      return false;
    }
  }
  // In the browser, hit /health relative to the page origin so the request
  // flows through whatever path is already serving the SPA — the Vite
  // proxy in dev, FastAPI's static mount in prod. This avoids the
  // false-negative "Cannot reach backend" banner when getBase() points at
  // an absolute URL the browser can't reach directly.
  //
  // If /health itself fails for any reason (proxy quirk, stale service
  // worker, etc.) fall back to an arbitrary API endpoint we know the rest
  // of the app polls successfully. If THAT also fails we genuinely can't
  // reach the backend.
  const probe = async (url: string): Promise<boolean> => {
    try {
      const res = await fetch(url, { cache: 'no-store' });
      return res.ok;
    } catch {
      return false;
    }
  };
  if (await probe('/health')) return true;
  return probe('/v1/connectors');
}

export async function fetchEnergy(): Promise<unknown> {
  if (isTauri()) {
    try {
      return await tauriInvoke('fetch_energy', { apiUrl: getBase() });
    } catch {}
  }
  const res = await apiFetch(`/v1/telemetry/energy`);
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  return res.json();
}

export async function fetchTelemetry(): Promise<unknown> {
  if (isTauri()) {
    try {
      return await tauriInvoke('fetch_telemetry', { apiUrl: getBase() });
    } catch {}
  }
  const res = await apiFetch(`/v1/telemetry/stats`);
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  return res.json();
}

export async function fetchTraces(limit: number = 50): Promise<unknown> {
  if (isTauri()) {
    try {
      return await tauriInvoke('fetch_traces', { apiUrl: getBase(), limit });
    } catch {}
  }
  const res = await apiFetch(`/v1/traces?limit=${limit}`);
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  return res.json();
}

// ---------------------------------------------------------------------------
// Speech
// ---------------------------------------------------------------------------

export interface TranscriptionResult {
  text: string;
  language: string | null;
  confidence: number | null;
  duration_seconds: number;
}

export interface SpeechHealth {
  available: boolean;
  backend?: string;
  reason?: string;
}

export async function transcribeAudio(audioBlob: Blob, filename = 'recording.webm'): Promise<TranscriptionResult> {
  if (isTauri()) {
    try {
      const buffer = await audioBlob.arrayBuffer();
      return await tauriInvoke<TranscriptionResult>('transcribe_audio', {
        audioData: Array.from(new Uint8Array(buffer)),
        filename,
      });
    } catch {
      // Fall through to fetch
    }
  }
  const formData = new FormData();
  formData.append('file', audioBlob, filename);
  formData.append('language', 'en');
  const res = await apiFetch(`/v1/speech/transcribe`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) throw new Error(`Transcription failed: ${res.status}`);
  return res.json();
}

export async function fetchSpeechHealth(): Promise<SpeechHealth> {
  if (isTauri()) {
    try {
      return await tauriInvoke<SpeechHealth>('speech_health');
    } catch {
      return { available: false };
    }
  }
  const res = await apiFetch(`/v1/speech/health`);
  if (!res.ok) return { available: false };
  return res.json();
}

export interface TtsHealth {
  available: boolean;
  backend?: string;
  reason?: string;
}

export async function fetchTtsHealth(): Promise<TtsHealth> {
  const res = await apiFetch(`/v1/speech/tts/health`);
  if (!res.ok) return { available: false };
  return res.json();
}

export async function synthesizeSpeech(text: string): Promise<Blob> {
  const res = await apiFetch(`/v1/speech/synthesize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`Speech synthesis failed: ${detail}`);
  }
  return res.blob();
}

// ---------------------------------------------------------------------------
// Agent Manager
// ---------------------------------------------------------------------------

export interface ManagedAgent {
  id: string;
  name: string;
  agent_type: string;
  config: Record<string, unknown>;
  status: 'idle' | 'running' | 'paused' | 'error' | 'archived' | 'needs_attention' | 'budget_exceeded' | 'stalled';
  summary_memory: string;
  created_at: number;
  updated_at: number;
  // Runtime stats
  total_runs?: number;
  total_cost?: number;
  total_tokens?: number;
  input_tokens?: number;
  output_tokens?: number;
  last_run_at?: number | null;
  // Schedule
  schedule_type?: string;
  schedule_value?: string;
  // Budget
  budget?: number;
  // Learning
  learning_enabled?: boolean;
  // Live progress
  current_activity?: string;
}

export interface AgentTask {
  id: string;
  agent_id: string;
  description: string;
  status: 'pending' | 'active' | 'completed' | 'failed';
  progress: Record<string, unknown>;
  findings: unknown[];
  created_at: number;
}

export interface ChannelBinding {
  id: string;
  agent_id: string;
  channel_type: string;
  config: Record<string, unknown>;
  session_id: string;
  routing_mode: string;
}

export interface AgentTemplate {
  id: string;
  name: string;
  description: string;
  source: 'built-in' | 'user';
  agent_type: string;
  [key: string]: unknown;
}

export interface PersistedToolCall {
  tool: string;
  arguments: string;
  result?: string;
  success?: boolean;
  latency?: number;
}

export interface AgentMessage {
  id: string;
  agent_id: string;
  direction: 'user_to_agent' | 'agent_to_user';
  content: string;
  mode: 'immediate' | 'queued';
  status: 'pending' | 'delivered' | 'responded';
  created_at: number;
  tool_calls?: PersistedToolCall[] | null;
}

export async function fetchManagedAgents(): Promise<ManagedAgent[]> {
  const res = await apiFetch(`/v1/managed-agents`);
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  const data = await res.json();
  return data.agents || [];
}

export async function fetchManagedAgent(agentId: string): Promise<ManagedAgent> {
  const res = await apiFetch(`/v1/managed-agents/${agentId}`);
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  return res.json();
}

export async function createManagedAgent(body: {
  name: string;
  agent_type?: string;
  template_id?: string;
  config?: Record<string, unknown>;
}): Promise<ManagedAgent> {
  const res = await apiFetch(`/v1/managed-agents`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  return res.json();
}

export async function updateManagedAgent(
  agentId: string,
  body: Partial<{ name: string; agent_type: string; config: Record<string, unknown> }>,
): Promise<ManagedAgent> {
  const res = await apiFetch(`/v1/managed-agents/${agentId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  return res.json();
}

export async function deleteManagedAgent(agentId: string): Promise<void> {
  const res = await apiFetch(`/v1/managed-agents/${agentId}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
}

export async function pauseManagedAgent(agentId: string): Promise<void> {
  const res = await apiFetch(`/v1/managed-agents/${agentId}/pause`, { method: 'POST' });
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
}

export async function resumeManagedAgent(agentId: string): Promise<void> {
  const res = await apiFetch(`/v1/managed-agents/${agentId}/resume`, { method: 'POST' });
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
}

export async function fetchAgentTasks(agentId: string): Promise<AgentTask[]> {
  const res = await apiFetch(`/v1/managed-agents/${agentId}/tasks`);
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  const data = await res.json();
  return data.tasks || [];
}

export async function createAgentTask(agentId: string, description: string): Promise<AgentTask> {
  const res = await apiFetch(`/v1/managed-agents/${agentId}/tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ description }),
  });
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  return res.json();
}

export async function fetchAgentChannels(agentId: string): Promise<ChannelBinding[]> {
  const res = await apiFetch(`/v1/managed-agents/${agentId}/channels`);
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  const data = await res.json();
  return data.bindings || [];
}

export async function bindAgentChannel(
  agentId: string,
  channelType: string,
  config?: Record<string, unknown>,
): Promise<ChannelBinding> {
  const res = await fetch(
    `${getBase()}/v1/managed-agents/${agentId}/channels`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        channel_type: channelType,
        config: config || {},
        routing_mode: 'dedicated',
      }),
    },
  );
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  return res.json();
}

export async function unbindAgentChannel(
  agentId: string,
  bindingId: string,
): Promise<void> {
  const res = await fetch(
    `${getBase()}/v1/managed-agents/${agentId}/channels/${bindingId}`,
    { method: 'DELETE' },
  );
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
}

// -- SendBlue auto-setup helpers ------------------------------------------

export async function sendblueVerify(
  apiKeyId: string,
  apiSecretKey: string,
): Promise<{ valid: boolean; numbers: string[]; raw: unknown }> {
  const res = await apiFetch(`/v1/channels/sendblue/verify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key_id: apiKeyId, api_secret_key: apiSecretKey }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Verification failed: ${res.status}`);
  }
  return res.json();
}

export async function sendblueRegisterWebhook(
  apiKeyId: string,
  apiSecretKey: string,
  webhookUrl: string,
): Promise<{ registered: boolean; status: number }> {
  const res = await apiFetch(`/v1/channels/sendblue/register-webhook`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      api_key_id: apiKeyId,
      api_secret_key: apiSecretKey,
      webhook_url: webhookUrl,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Webhook registration failed: ${res.status}`);
  }
  return res.json();
}

export async function sendblueTest(
  apiKeyId: string,
  apiSecretKey: string,
  fromNumber: string,
  toNumber: string,
): Promise<{ sent: boolean; status: number }> {
  const res = await apiFetch(`/v1/channels/sendblue/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      api_key_id: apiKeyId,
      api_secret_key: apiSecretKey,
      from_number: fromNumber,
      to_number: toNumber,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Test message failed: ${res.status}`);
  }
  return res.json();
}

export async function sendblueHealth(): Promise<{ channel_connected: boolean; bridge_wired: boolean; ready: boolean }> {
  const res = await apiFetch(`/v1/channels/sendblue/health`);
  if (!res.ok) return { channel_connected: false, bridge_wired: false, ready: false };
  return res.json();
}

export async function fetchTemplates(): Promise<AgentTemplate[]> {
  const res = await apiFetch(`/v1/templates`);
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  const data = await res.json();
  return data.templates || [];
}

export async function runManagedAgent(agentId: string): Promise<void> {
  const res = await apiFetch(`/v1/managed-agents/${agentId}/run`, { method: 'POST' });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `Failed: ${res.status}`);
  }
}

export async function recoverManagedAgent(agentId: string): Promise<{ recovered: boolean; checkpoint: unknown }> {
  const res = await apiFetch(`/v1/managed-agents/${agentId}/recover`, { method: 'POST' });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `Failed: ${res.status}`);
  }
  return res.json();
}

export async function fetchAgentState(agentId: string): Promise<{
  agent: ManagedAgent;
  tasks: AgentTask[];
  channels: ChannelBinding[];
  messages: AgentMessage[];
  checkpoint: unknown;
}> {
  const res = await apiFetch(`/v1/managed-agents/${agentId}/state`);
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  return res.json();
}

export interface AgentToolCallStart {
  tool: string;
  arguments: string;
}

export interface AgentToolCallEnd {
  tool: string;
  success: boolean;
  latency: number;
  result?: string;
}

export async function sendAgentMessage(
  agentId: string,
  content: string,
  mode: 'immediate' | 'queued' = 'queued',
  callbacks?: {
    onProgress?: (label: string) => void;
    onContentDelta?: (delta: string, fullContent: string) => void;
    onToolCallStart?: (info: AgentToolCallStart) => void;
    onToolCallEnd?: (info: AgentToolCallEnd) => void;
    onDone?: (fullContent: string, usage?: Record<string, number>, telemetry?: Record<string, unknown>) => void;
  },
): Promise<AgentMessage> {
  const res = await apiFetch(`/v1/managed-agents/${agentId}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, mode, stream: true }),
  });
  if (!res.ok) throw new Error(`Failed: ${res.status}`);

  // If streaming, consume the SSE response so the agent runs
  const contentType = res.headers.get('content-type') || '';
  if (contentType.includes('text/event-stream') && res.body) {
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let fullContent = '';
    let buffer = '';
    let lastUsage: Record<string, number> | undefined;
    let lastTelemetry: Record<string, unknown> | undefined;
    let currentEvent: string | undefined;
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim();
            continue;
          }
          if (!line.startsWith('data: ')) {
            if (line.trim() === '') currentEvent = undefined;
            continue;
          }
          const data = line.slice(6);
          if (data === '[DONE]') {
            currentEvent = undefined;
            continue;
          }
          const evName = currentEvent;
          currentEvent = undefined;

          if (evName === 'tool_call_start') {
            try {
              const parsed = JSON.parse(data);
              callbacks?.onToolCallStart?.({
                tool: parsed.tool,
                arguments: parsed.arguments ?? '',
              });
            } catch {
              /* skip */
            }
            continue;
          }
          if (evName === 'tool_call_end') {
            try {
              const parsed = JSON.parse(data);
              callbacks?.onToolCallEnd?.({
                tool: parsed.tool,
                success: !!parsed.success,
                latency: typeof parsed.latency === 'number' ? parsed.latency : 0,
                result: parsed.result,
              });
            } catch {
              /* skip */
            }
            continue;
          }

          try {
            const chunk = JSON.parse(data);
            // Deep-research branch still uses tool_progress in a data chunk
            const toolProgress = chunk.choices?.[0]?.tool_progress;
            if (toolProgress) {
              callbacks?.onProgress?.(toolProgress);
            }
            const delta = chunk.choices?.[0]?.delta?.content || '';
            if (delta) {
              fullContent += delta;
              callbacks?.onContentDelta?.(delta, fullContent);
            }
            if (chunk.usage) lastUsage = chunk.usage;
            if (chunk.telemetry) lastTelemetry = chunk.telemetry;
          } catch {
            /* skip malformed chunks */
          }
        }
      }
    } catch { /* stream ended */ }

    callbacks?.onDone?.(fullContent, lastUsage, lastTelemetry);

    return {
      id: '',
      agent_id: agentId,
      direction: 'agent_to_user',
      content: fullContent,
      mode,
      status: 'delivered',
      created_at: Date.now() / 1000,
    };
  }

  return res.json();
}

/**
 * Ask the agent a question by triggering an ad-hoc run.
 *
 * Posts the question as an `immediate`, non-streamed message — the backend
 * stores it and spawns a real agent tick (`execute_tick`) that consumes it as
 * the run's input (tools, trace, and all), rather than a raw one-shot chat.
 * Returns immediately with the stored user message; progress is observed via
 * the `/v1/agents/events` WebSocket and the resulting trace.
 */
export async function askAgent(agentId: string, content: string): Promise<AgentMessage> {
  const res = await apiFetch(`/v1/managed-agents/${agentId}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, mode: 'immediate', stream: false }),
  });
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  return res.json();
}

export async function fetchAgentMessages(agentId: string): Promise<AgentMessage[]> {
  const res = await apiFetch(`/v1/managed-agents/${agentId}/messages`);
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  const data = await res.json();
  return data.messages || [];
}

export async function fetchErrorAgents(): Promise<ManagedAgent[]> {
  const res = await apiFetch(`/v1/agents/errors`);
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  const data = await res.json();
  return data.agents || [];
}

// ---------------------------------------------------------------------------
// Agent Learning + Traces
// ---------------------------------------------------------------------------

export interface LearningLogEntry {
  id: string;
  agent_id: string;
  event_type: string;
  description: string;
  data: Record<string, unknown>;
  created_at: number;
}

export interface AgentTrace {
  id: string;
  outcome: string;
  duration: number;
  started_at: number;
  steps: number;
  error_message?: string;
  metadata?: Record<string, unknown>;
}

export interface ToolInfo {
  name: string;
  description: string;
  category: string;
  source: 'tool' | 'channel';
  requires_credentials: boolean;
  credential_keys: string[];
  configured: boolean;
}

export async function fetchAvailableTools(): Promise<ToolInfo[]> {
  const res = await apiFetch(`/v1/tools`);
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  const data = await res.json();
  return data.tools || [];
}

export async function saveToolCredentials(
  toolName: string,
  credentials: Record<string, string>,
): Promise<void> {
  const res = await apiFetch(`/v1/tools/${toolName}/credentials`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(credentials),
  });
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
}

export interface AgentTraceDetail {
  id: string;
  agent: string;
  outcome: string;
  duration: number;
  started_at: number;
  steps: Array<{
    step_type: string;
    input: unknown;
    output: string;
    duration: number;
    metadata: Record<string, unknown>;
  }>;
}

export async function fetchLearningLog(agentId: string): Promise<LearningLogEntry[]> {
  const res = await apiFetch(`/v1/managed-agents/${agentId}/learning`);
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  const data = await res.json();
  return data.learning_log || [];
}

export async function triggerLearning(agentId: string): Promise<void> {
  const res = await apiFetch(`/v1/managed-agents/${agentId}/learning/run`, { method: 'POST' });
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
}

export async function fetchAgentTraces(agentId: string, limit = 20): Promise<AgentTrace[]> {
  const res = await apiFetch(`/v1/managed-agents/${agentId}/traces?limit=${limit}`);
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  const data = await res.json();
  return data.traces || [];
}

export async function fetchAgentTrace(agentId: string, traceId: string): Promise<AgentTraceDetail> {
  const res = await apiFetch(`/v1/managed-agents/${agentId}/traces/${traceId}`);
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  return res.json();
}

// ---------------------------------------------------------------------------
// Leaderboard savings submission (Supabase)
// ---------------------------------------------------------------------------

export interface SavingsSubmission {
  anon_id: string;
  display_name: string;
  email: string;
  total_calls: number;
  total_tokens: number;
  dollar_savings: number;
  energy_wh_saved: number;
  flops_saved: number;
  token_counting_version?: number;
}

export async function submitSavings(data: SavingsSubmission): Promise<boolean> {
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY) return false;
  try {
    const res = await fetch(
      `${SUPABASE_URL}/rest/v1/savings_entries?on_conflict=anon_id`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          apikey: SUPABASE_ANON_KEY,
          Authorization: `Bearer ${SUPABASE_ANON_KEY}`,
          Prefer: 'resolution=merge-duplicates',
        },
        body: JSON.stringify(data),
      },
    );
    return res.ok || res.status === 201 || res.status === 200;
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------------------
// Memory
// ---------------------------------------------------------------------------

export interface MemorySearchResult {
  content: string;
  score: number;
  metadata: Record<string, unknown>;
}

export interface MemoryStats {
  entries: number;
  backend: string;
  [key: string]: unknown;
}

export interface MemoryConfig {
  backend: string;
  // Set by the server when the native `openjarvis_rust` extension is missing,
  // so the UI can show the real cause instead of a healthy-looking config.
  available?: boolean;
  detail?: string | null;
  context_from_memory: boolean;
  context_top_k: number;
  context_min_score: number;
  context_max_tokens: number;
}

/**
 * Extract the server's `detail` message from a failed JSON response so the UI
 * surfaces the real cause (e.g. "openjarvis_rust extension is not installed")
 * instead of a blanket fallback string (#502).
 */
async function memoryErrorDetail(res: Response, fallback: string): Promise<string> {
  try {
    const data = await res.json();
    if (data && typeof data.detail === 'string' && data.detail) return data.detail;
  } catch {
    // Non-JSON body — fall through to the generic message below.
  }
  return fallback;
}

export async function getMemoryStats(): Promise<MemoryStats> {
  const res = await apiFetch(`/v1/memory/stats`);
  if (!res.ok) throw new Error('Failed to fetch memory stats');
  return res.json();
}

export async function searchMemory(query: string, topK: number = 5): Promise<MemorySearchResult[]> {
  const res = await apiFetch(`/v1/memory/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, top_k: topK }),
  });
  if (!res.ok) throw new Error('Failed to search memory');
  const data = await res.json();
  return data.results;
}

export async function storeMemory(content: string, metadata?: Record<string, unknown>): Promise<void> {
  const res = await apiFetch(`/v1/memory/store`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, metadata }),
  });
  if (!res.ok) throw new Error(await memoryErrorDetail(res, 'Failed to store memory'));
}

export async function indexMemoryPath(path: string): Promise<{ chunks_indexed: number; note?: string }> {
  const res = await apiFetch(`/v1/memory/index`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  });
  if (!res.ok) throw new Error(await memoryErrorDetail(res, 'Failed to index path'));
  return res.json();
}

export async function getMemoryConfig(): Promise<MemoryConfig> {
  const res = await apiFetch(`/v1/memory/config`);
  if (!res.ok) throw new Error('Failed to fetch memory config');
  return res.json();
}

// ---------------------------------------------------------------------------
// Approvals
// ---------------------------------------------------------------------------

export interface PendingApproval {
  id: string;
  action_type: string;
  description: string;
  payload: Record<string, unknown>;
  permission_key: string;
  tier: 'trivial' | 'low' | 'medium' | 'high';
  status: string;
  created_at: string;
  expires_at: string;
}

export async function fetchPendingApprovals(): Promise<PendingApproval[]> {
  const res = await apiFetch(`/v1/approvals/pending`);
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  const data = await res.json();
  return data.actions || [];
}

export async function approveAction(actionId: string): Promise<void> {
  const res = await apiFetch(`/v1/approvals/${actionId}/approve`, { method: 'POST' });
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
}

export async function denyAction(actionId: string): Promise<void> {
  const res = await apiFetch(`/v1/approvals/${actionId}/deny`, { method: 'POST' });
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
}

// ---------------------------------------------------------------------------
// Inference source (desktop only)
// ---------------------------------------------------------------------------

export type InferenceSource = {
  kind: 'ollama' | 'custom';
  model?: string;
  host?: string;
  engine?: string;
};

export async function getInferenceSource(): Promise<InferenceSource> {
  if (isTauri()) {
    try {
      const { invoke } = await import('@tauri-apps/api/core');
      return await invoke<InferenceSource>('get_inference_source');
    } catch (e: any) {
      throw new Error(e?.message ?? e ?? 'Failed to read inference source');
    }
  }
  return { kind: 'ollama' };
}

export async function setInferenceSource(
  src: InferenceSource & { apiKey?: string },
): Promise<void> {
  if (!isTauri()) throw new Error('Inference source is configurable in the desktop app only.');
  try {
    const { invoke } = await import('@tauri-apps/api/core');
    await invoke<void>('set_inference_source', {
      kind: src.kind,
      model: src.model ?? null,
      host: src.host ?? null,
      engine: src.engine ?? null,
      apiKey: src.apiKey ?? null,
    });
  } catch (e: any) {
    // Surface the backend's actionable error strings (e.g. "A server URL is
    // required…", "Could not store the API key…") as proper Error instances.
    throw new Error(e?.message ?? e ?? 'Failed to save inference source');
  }
}

// ---------------------------------------------------------------------------
// Trading / TradingView
// ---------------------------------------------------------------------------

export interface TradingMarketPnl {
  realized_pnl?: number;
  session_pnl?: number;
  unrealized_pnl?: number;
  closed_trades?: number;
  open_positions?: number;
  wins?: number;
  losses?: number;
  win_rate_pct?: number;
}

export interface TradingSession {
  running?: boolean;
  mode?: string;
  equity?: number;
  return_pct?: number;
  open_positions?: number;
  closed_trades?: number;
  session_pnl?: number;
  realized_pnl?: number;
  unrealized_pnl?: number;
  today_pnl?: number;
  win_rate_pct?: number;
  wins?: number;
  losses?: number;
  kill_switch?: boolean;
  updated_at?: number;
}

export interface TradingPnlSummary {
  available: boolean;
  equity?: number;
  starting_equity?: number;
  return_pct?: number;
  realized_pnl?: number;
  session_pnl?: number;
  unrealized_pnl?: number;
  today_pnl?: number;
  open_positions?: number;
  closed_trades?: number;
  wins?: number;
  losses?: number;
  win_rate_pct?: number;
  wins_today?: number;
  losses_today?: number;
  trades_today?: number;
  voided_pnl?: number;
  mode?: string;
  running?: boolean;
  strategy_display?: {
    active?: boolean;
    source?: string;
    actual_raw_pnl?: number;
    actual_raw_trades?: number;
    actual_raw_win_rate_pct?: number;
    blocked_trades_skipped?: number;
    new_trades_since_baseline?: number;
    new_pnl_since_baseline?: number;
    updated_at?: number;
  };
  strategy_charts?: {
    profit_series?: { label: string; value: number }[];
    win_rate_series?: { label: string; value: number }[];
    equity_curve?: { label: string; value: number }[];
  };
  markets?: {
    crypto?: TradingMarketPnl;
    stocks?: TradingMarketPnl;
  };
  alpaca?: {
    configured?: boolean;
    ok?: boolean;
    keys_file_exists?: boolean;
    equity?: number;
    buying_power?: number;
    sample_quote?: { symbol?: string; price?: number };
    error?: string;
    config?: { enabled?: boolean; data_for_stocks?: boolean; orders_enabled?: boolean };
    stock_gates?: TradingConfig['stock_gates'];
  };
  simulation?: Record<string, unknown>;
  error?: string;
}

export interface TradingStatus {
  available: boolean;
  data_dir?: string;
  pnl?: TradingPnlSummary;
  alpaca?: TradingPnlSummary['alpaca'];
  markets?: TradingPnlSummary['markets'];
  session: TradingSession;
  ledger?: {
    starting_equity?: number;
    equity?: number;
    ledger_realized_pnl?: number;
    return_pct?: number;
  };
}

export interface TradingPosition {
  n: number;
  status: string;
  action: string;
  symbol: string;
  qty: string;
  price?: number;
  entry_cost_usd?: number;
  market_value_usd?: number;
  mark_premium?: number;
  spot?: number;
  live_mark?: boolean;
  unrealized_pnl?: number;
  pnl?: number | null;
  unrealized?: string;
  note?: string;
  bought_at?: string;
  bought_at_ts?: number;
  exit_plan?: string;
  bars_held?: number;
  max_hold_bars?: number;
  bars_remaining?: number;
  kind?: string;
  tradingview_symbol: string;
  nautilus_backtest?: NautilusSetupValidation | null;
}

export interface TradingHotCandidate {
  symbol: string;
  tradingview_symbol: string;
  pattern?: string;
  direction?: string;
  kind?: string;
  strength?: number;
  spot?: number;
  spot_fmt?: string;
  reason?: string;
  win_prob?: number;
  win_prob_pct?: number;
  nautilus_backtest?: NautilusSetupValidation | null;
}

export interface TradingPaperOrderResult {
  ok: boolean;
  mode?: string;
  message?: string;
  queued?: boolean;
  executed?: boolean;
  trade_id?: string;
  symbol?: string;
  leg?: string;
  error?: string;
}

export interface TradingStockSymbol {
  symbol: string;
  tradingview_symbol: string;
  exchange: string;
  market: string;
}

export interface TradingConfig {
  default_exchange: string;
  default_symbol: string;
  interval: string;
  theme: string;
  webhook_url: string;
  webhook_secret_configured?: boolean;
  auto_execute?: boolean;
  allowed_markets?: string[];
  auto_switch_chart?: boolean;
  paper_only?: boolean;
  stock_exchanges?: string[];
  crypto_exchanges?: string[];
  example_stock_symbols?: TradingStockSymbol[];
  stock_gates?: {
    option_campaign_max_open?: number;
    symbol_whitelist?: string[];
    min_win_prob_pct?: number;
    require_alpaca_quote?: boolean;
    stocks_enabled?: boolean;
  };
  crypto_gates?: {
    option_campaign_max_open?: number;
    min_win_prob_pct?: number;
    double_top_min_strength?: number;
    bear_flag_min_strength?: number;
    option_live_pattern_min_strength?: number;
    spot_max_hold_bars?: number;
    crypto_trade_mode?: string;
    stock_trade_mode?: string;
    crypto_kind?: string;
    stock_kind?: string;
  };
  trade_modes?: {
    crypto_trade_mode?: string;
    stock_trade_mode?: string;
    crypto_kind?: string;
    stock_kind?: string;
  };
}

export interface TradingAlert {
  received_at: number;
  tradingview_symbol: string;
  internal_symbol?: string;
  market?: string;
  action?: string;
  price?: number;
  message?: string;
  alert_name?: string;
  trade_status?: string;
  order_result?: TradingPaperOrderResult;
}

export interface TradingAutomationStatus {
  paper_only: boolean;
  auto_execute: boolean;
  allowed_markets: string[];
  default_qty: number;
  webhook_secret_configured: boolean;
  webhook_url: string;
  tunnel_active: boolean;
  live_session_running: boolean;
  manual_order_queue_depth: number;
  auto_switch_chart: boolean;
  alerts_buffered?: number;
  last_alert?: {
    received_at: number;
    tradingview_symbol: string;
    action?: string;
    trade_status?: string;
    internal_symbol?: string;
  } | null;
}

export interface TradingViewAccountStatus {
  linked: boolean;
  display_name: string;
  linked_at: number | null;
  link_method: string;
  updated_at: number | null;
  oauth_available: boolean;
  login_method: string;
  limitations: string;
}

export interface TradingViewLinkStatus {
  webhook_url: string;
  webhook_local_path: string;
  tunnel_configured: boolean;
  tunnel_url: string | null;
  ngrok_domain: string;
  default_exchange: string;
  interval: string;
  theme?: string;
  auto_execute: boolean;
  webhook_secret_configured: boolean;
  alert_json_template: Record<string, unknown>;
  chart_url_template: string;
  linked: boolean;
  webhook_ready?: boolean;
  account_linked?: boolean;
  account?: TradingViewAccountStatus;
  recent_alert_count: number;
  last_alert_at: number | null;
  alerts_buffered?: number;
}

export interface TradingLearningSummary {
  available: boolean;
  learning_active?: boolean;
  trades_since_last_sweep?: number;
  refinement?: {
    learning_active?: boolean;
    trades_since_last_sweep?: number;
    deployed_strategy?: string;
    sweep_pending?: boolean;
  };
  error?: string;
}

export interface MarketScoutAgent {
  id: string;
  status: string;
  symbols_scanned?: number;
  setups_found?: number;
  last_scan_at?: number;
  note?: string;
}

export interface MarketScoutStatus {
  running: boolean;
  updated_at?: number;
  started_at?: number;
  universe?: number;
  setup_count?: number;
  scouts: MarketScoutAgent[];
  note?: string;
  pid?: number;
}

export interface MarketScoutSetup {
  symbol: string;
  tradingview_symbol: string;
  direction: string;
  confidence: number;
  label: string;
  tools: string[];
  pattern?: string | null;
  rsi?: number | null;
  ml_rsi?: number | null;
  spot_fmt?: string;
  detected_at?: number;
  market?: string;
  conviction_pct?: number | null;
  signal_score?: number | null;
  auto_eligible?: boolean;
  nautilus_backtest?: NautilusSetupValidation | null;
  entry_allowed?: boolean;
  direction_confirmed?: boolean;
  fakeout_risk?: number;
  bull_score?: number;
  bear_score?: number;
  confirmation_note?: string;
  confirmation_pass?: string[];
  confirmation_fail?: string[];
  symbol_math?: Record<string, unknown>;
  symbol_math_score?: number;
  symbol_math_pass?: boolean;
  scan_source?: string;
  chart_ready?: boolean;
  signal_tier?: string | null;
}

export interface SetupScannerRow extends MarketScoutSetup {
  scan_source?: string;
  chart_ready?: boolean;
  feed_updated_at?: number;
  received_at?: number;
  action?: string;
  price?: number;
  trade_status?: string;
  chart_url?: string;
  symbol_math?: {
    style?: string;
    swing_pct?: number;
    min_profit_pct?: number;
    target_move_pct?: number;
    repeatability?: number;
    playbook_hint?: string;
  };
  symbol_math_score?: number;
  symbol_math_pass?: boolean;
}

export interface SetupChartPayload {
  ok: boolean;
  symbol?: string;
  error?: string;
  bars?: number;
  candles?: Array<{ time: number; open: number; high: number; low: number; close: number; volume?: number }>;
  lines?: { ema9?: Array<{ time: number; value: number }>; ema21?: Array<{ time: number; value: number }> };
  overlays?: Array<{
    kind?: string;
    price?: number;
    top?: number;
    bottom?: number;
    label?: string;
    color?: string;
  }>;
  markers?: Array<{
    time: number;
    position: 'aboveBar' | 'belowBar' | 'inBar';
    shape: 'arrowUp' | 'arrowDown' | 'circle' | 'square';
    color: string;
    text?: string;
    price?: number;
  }>;
  trend?: { label?: string; bull_score?: number; bear_score?: number; direction?: string };
  setup?: Record<string, unknown>;
  updated_at?: number;
}

export async function fetchSetupScanner(): Promise<{ ok?: boolean; count?: number; setups?: SetupScannerRow[] }> {
  const res = await apiFetch('/api/trading/setup-scanner');
  if (!res.ok) throw new Error(`Setup scanner failed: ${res.status}`);
  return res.json();
}

export async function fetchSetupChart(symbol: string, pattern?: string | null): Promise<SetupChartPayload> {
  const encoded = encodeURIComponent(symbol.trim());
  const pat = pattern ? `&pattern=${encodeURIComponent(pattern)}` : '';
  const res = await apiFetch(`/api/trading/setup-chart?symbol=${encoded}${pat}`);
  if (!res.ok) throw new Error(`Setup chart failed: ${res.status}`);
  return res.json();
}

export interface TradingLedgerTrades {
  available: boolean;
  all_time?: boolean;
  starting_equity?: number;
  equity?: number;
  ledger_realized_pnl?: number;
  session_pnl?: number;
  return_pct?: number;
  open_count: number;
  closed_count: number;
  wins?: number;
  losses?: number;
  breakeven?: number;
  win_rate_pct?: number;
  open: TradingPosition[];
  closed: Array<{
    n: number;
    status: string;
    action: string;
    symbol: string;
    qty: string;
    price?: number;
    exit_price?: number;
    pnl?: number;
    exit_reason?: string;
    note?: string;
  }>;
  updated_at?: number;
  strategy_display?: TradingPnlSummary['strategy_display'];
  strategy_charts?: TradingPnlSummary['strategy_charts'];
  closed_count_raw?: number;
  closed_count_strategy?: number;
}

export interface NautilusSetupValidation {
  ok?: boolean;
  passed?: boolean;
  symbol?: string;
  strategy?: string;
  timeframe?: string;
  win_rate?: number;
  total_pnl?: number;
  max_drawdown?: number;
  trades?: number;
  gate_reason?: string;
  error?: string;
  validated_at?: number;
  min_win_rate_used?: number;
}

export async function fetchTradingScoutFeed(includeNautilus = true): Promise<{
  updated_at?: number;
  count: number;
  setups: MarketScoutSetup[];
  hot_agreement: string[];
}> {
  const q = includeNautilus ? '?include_nautilus=1' : '';
  const res = await apiFetch(`/api/trading/scout-feed${q}`);
  if (!res.ok) throw new Error(`Scout feed failed: ${res.status}`);
  return res.json();
}

export async function validateNautilusSetup(body: {
  symbol: string;
  direction?: string;
  pattern?: string | null;
  label?: string;
  market?: string;
  timeframe?: string;
  strategy?: string;
  force_refresh?: boolean;
}): Promise<MarketScoutSetup> {
  const res = await apiFetch('/api/trading/nautilus/validate-setup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || data.error || `Validate failed: ${res.status}`);
  return data;
}

export async function fetchTradingScoutStatus(): Promise<MarketScoutStatus> {
  const res = await apiFetch('/api/trading/scout-status');
  if (!res.ok) throw new Error(`Scout status failed: ${res.status}`);
  return res.json();
}

export interface TradingAutoStatus {
  enabled: boolean;
  auto_buy: boolean;
  auto_sell: boolean;
  scout_auto_execute: boolean;
  scout_min_confidence_pct: number;
  take_profit_on_unrealized_usd: number;
  trail_profit: boolean;
  auto_close_on_scout_reversal: boolean;
  poll_sec: number;
  scout_feed_orders: boolean;
  daemon_pid?: number | null;
  buys_today: number;
  sells_today: number;
  last_buy?: number | null;
  last_sell?: number | null;
  rules?: { buy?: string; sell?: string; trail_profit?: boolean };
  nautilus?: {
    learner?: Record<string, unknown>;
    gate?: Record<string, unknown>;
  };
}

export async function fetchTradingAutoStatus(): Promise<TradingAutoStatus> {
  const res = await apiFetch('/api/trading/auto-status');
  if (!res.ok) throw new Error(`Auto status failed: ${res.status}`);
  return res.json();
}

export async function fetchTradingLearningSummary(): Promise<TradingLearningSummary> {
  const res = await apiFetch('/api/trading/learning-summary');
  if (!res.ok) throw new Error(`Learning summary failed: ${res.status}`);
  return res.json();
}

export async function fetchTradingStatus(): Promise<TradingStatus> {
  const res = await apiFetch('/api/trading/status');
  if (!res.ok) throw new Error(`Trading status failed: ${res.status}`);
  return res.json();
}

export async function fetchTradingPnl(): Promise<TradingPnlSummary> {
  const res = await apiFetch('/api/trading/pnl');
  if (!res.ok) throw new Error(`Trading PnL failed: ${res.status}`);
  return res.json();
}

export type StrategyPerformancePayload = {
  available: boolean;
  alpha_index: number;
  components?: {
    win_rate_pct?: number;
    return_pct?: number | null;
    avg_signal_score?: number;
    avg_quality_pct?: number;
  };
  series: Array<{ label: string; value: number }>;
  updated_at?: number;
};

export async function fetchTradingStrategyPerformance(): Promise<StrategyPerformancePayload> {
  const res = await apiFetch('/api/trading/strategy-performance');
  if (!res.ok) throw new Error(`Strategy performance failed: ${res.status}`);
  return res.json();
}

export async function fetchAlpacaStatus(): Promise<NonNullable<TradingPnlSummary['alpaca']>> {
  const res = await apiFetch('/api/trading/alpaca/status');
  if (!res.ok) throw new Error(`Alpaca status failed: ${res.status}`);
  return res.json();
}

export type PropFirmEvalDesk = {
  ok: boolean;
  config: {
    enabled?: boolean;
    target_pass_pct?: number;
    stop_after_losing_day?: boolean;
    max_trades_per_day?: number;
    error?: string;
  };
  path: string;
  error?: string;
  symbol_focus?: string;
  mode?: string;
  eval?: {
    generated_at?: number;
    eval_pass_pct?: number;
    eval_fail_pct?: number;
    eval_timeout_pct?: number;
    funded_payout_given_pass_pct?: number;
    combined_payout_chance_pct?: number;
    interpretation?: string;
    simulations?: number;
    rules?: Record<string, number>;
    replay_sample?: {
      n_trades?: number;
      win_rate_pct?: number;
      mean_pnl_usd?: number;
      total_replay_pnl_usd?: number;
    };
  } | null;
};

export async function fetchPropFirmEval(): Promise<PropFirmEvalDesk> {
  const res = await apiFetch('/api/trading/prop-firm-eval');
  if (!res.ok) throw new Error(`Prop-firm eval failed: ${res.status}`);
  return res.json();
}

export async function fetchAlpacaQuote(symbol: string): Promise<{ symbol: string; price: number }> {
  const res = await apiFetch(`/api/trading/alpaca/quote/${encodeURIComponent(symbol)}`);
  if (!res.ok) throw new Error(`Alpaca quote failed: ${res.status}`);
  return res.json();
}

export type OrderFlowSnapshot = {
  symbol: string;
  market: string;
  bid?: number;
  ask?: number;
  mid?: number;
  spread_pct?: number;
  bid_size?: number;
  ask_size?: number;
  imbalance: number;
  pressure: string;
  score_pct: number;
  source: string;
};

export async function fetchOrderFlow(symbol: string, market?: string): Promise<OrderFlowSnapshot> {
  const q = market ? `?market=${encodeURIComponent(market)}` : '';
  const res = await apiFetch(`/api/trading/order-flow/${encodeURIComponent(symbol)}${q}`);
  if (!res.ok) throw new Error(`Order flow failed: ${res.status}`);
  return res.json();
}

export async function fetchTradingPositions(): Promise<{
  count: number;
  positions: TradingPosition[];
}> {
  const res = await apiFetch('/api/trading/positions');
  if (!res.ok) throw new Error(`Trading positions failed: ${res.status}`);
  return res.json();
}

export async function fetchTradingLedgerTrades(): Promise<TradingLedgerTrades> {
  const res = await apiFetch('/api/trading/ledger-trades');
  if (!res.ok) throw new Error(`Trading ledger failed: ${res.status}`);
  return res.json();
}

export async function fetchTradingHotSymbols(): Promise<{
  count: number;
  candidates: TradingHotCandidate[];
}> {
  const res = await apiFetch('/api/trading/hot-symbols');
  if (!res.ok) throw new Error(`Hot symbols failed: ${res.status}`);
  return res.json();
}

export async function fetchTradingConfig(): Promise<TradingConfig> {
  const res = await apiFetch('/api/trading/config');
  if (!res.ok) throw new Error(`Trading config failed: ${res.status}`);
  return res.json();
}

export async function submitTradingPaperOrder(
  symbol: string,
  action: 'buy' | 'sell',
  opts?: {
    market?: string;
    price?: number;
    tradingview_symbol?: string;
    source?: string;
  },
): Promise<TradingPaperOrderResult> {
  const res = await apiFetch('/api/trading/paper-order', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      symbol,
      action,
      source: opts?.source ?? 'ui_chart_symbol',
      market: opts?.market,
      price: opts?.price,
      tradingview_symbol: opts?.tradingview_symbol,
    }),
  });
  const data = (await res.json()) as TradingPaperOrderResult & { detail?: string };
  if (!res.ok) {
    throw new Error(data.detail || data.error || `Paper order failed: ${res.status}`);
  }
  return data;
}

export async function fetchTradingSymbolMap(symbol: string): Promise<{
  symbol: string;
  tradingview_symbol: string;
  exchange: string;
  market?: string;
}> {
  const res = await apiFetch(`/api/trading/symbol-map/${encodeURIComponent(symbol)}`);
  if (!res.ok) throw new Error(`Symbol map failed: ${res.status}`);
  return res.json();
}

export async function fetchTradingAlerts(): Promise<{
  count: number;
  alerts: TradingAlert[];
}> {
  const res = await apiFetch('/api/trading/alerts');
  if (!res.ok) throw new Error(`Trading alerts failed: ${res.status}`);
  return res.json();
}

export async function fetchTradingAutomationStatus(): Promise<TradingAutomationStatus> {
  const res = await apiFetch('/api/trading/automation-status');
  if (!res.ok) throw new Error(`Automation status failed: ${res.status}`);
  return res.json();
}

export async function fetchTradingViewLink(): Promise<TradingViewLinkStatus> {
  const res = await apiFetch('/api/trading/tradingview/link');
  if (!res.ok) throw new Error(`TradingView link failed: ${res.status}`);
  return res.json();
}

export async function fetchTradingViewAccount(): Promise<TradingViewAccountStatus> {
  const res = await apiFetch('/api/trading/tradingview/account');
  if (!res.ok) throw new Error(`TradingView account failed: ${res.status}`);
  return res.json();
}

export async function saveTradingViewAccount(body: {
  action?: 'link' | 'unlink';
  display_name?: string;
  confirmed_in_widget?: boolean;
}): Promise<{ ok: boolean; account: TradingViewAccountStatus }> {
  const res = await apiFetch('/api/trading/tradingview/account', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || `TradingView account save failed: ${res.status}`);
  }
  return data;
}

export async function executeTradingViewAlert(
  tradingviewSymbol?: string,
  index = 0,
): Promise<{ ok: boolean; alert: TradingAlert; order: TradingPaperOrderResult }> {
  const res = await apiFetch('/api/trading/execute-tradingview-alert', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      tradingview_symbol: tradingviewSymbol,
      index,
    }),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || `Execute alert failed: ${res.status}`);
  }
  return data;
}

export interface FreqtradeProfit {
  profit_closed_fiat?: number;
  profit_closed_coin?: number;
  profit_closed_percent?: number;
  profit_all_fiat?: number;
  profit_all_percent?: number;
  trade_count?: number;
  closed_trade_count?: number;
  winning_trades?: number;
  losing_trades?: number;
  winrate?: number;
  profit_factor?: number | null;
  best_pair?: string;
  best_rate?: number;
  bot_start_date?: string;
  stake_currency?: string;
}

export interface FreqtradeTrade {
  trade_id?: number;
  pair?: string;
  is_open?: boolean;
  open_rate?: number;
  current_rate?: number;
  close_rate?: number;
  profit_ratio?: number;
  profit_pct?: number;
  profit_abs?: number;
  stake_amount?: number;
  open_date?: string;
  close_date?: string;
  exit_reason?: string;
  nautilus_backtest?: NautilusSetupValidation | null;
}

export interface FreqtradeBalance {
  total?: number;
  total_bot?: number;
  symbol?: string;
  currencies?: Array<{
    currency?: string;
    free?: number;
    balance?: number;
    used?: number;
    est_stake?: number;
  }>;
}

export interface FreqtradeStatus {
  enabled?: boolean;
  dry_run?: boolean;
  api_url?: string;
  strategy?: string;
  config_path?: string;
  api_reachable?: boolean;
  supervisor_running?: boolean;
  supervisor_pid?: number | null;
  state?: string;
  runmode?: string;
  open_trades?: number;
  max_open_trades?: number;
  show_config?: Record<string, unknown>;
  profit?: FreqtradeProfit;
  balance?: FreqtradeBalance;
  open_trades_list?: FreqtradeTrade[];
  closed_trades?: FreqtradeTrade[];
  closed_trades_total?: number;
  nautilus?: {
    learner?: Record<string, unknown>;
    gate?: Record<string, unknown>;
  };
  nautilus_validations?: Record<string, NautilusSetupValidation>;
}

export async function fetchFreqtradeStatus(): Promise<FreqtradeStatus> {
  const res = await apiFetch('/api/trading/freqtrade/status');
  if (!res.ok) throw new Error(`Freqtrade status failed: ${res.status}`);
  return res.json();
}

export async function startFreqtradeBot(): Promise<{ ok: boolean; message: string }> {
  const res = await apiFetch('/api/trading/freqtrade/start', { method: 'POST' });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || data.message || `Start failed: ${res.status}`);
  return data;
}

export async function stopFreqtradeBot(): Promise<{ ok: boolean; message: string }> {
  const res = await apiFetch('/api/trading/freqtrade/stop', { method: 'POST' });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || data.message || `Stop failed: ${res.status}`);
  return data;
}

export interface NautilusStatus {
  enabled?: boolean;
  mode?: string;
  configured_mode?: string;
  live_trading_unlock?: boolean;
  paper_only?: boolean;
  version?: string;
  runner_script?: string;
  state_path?: string;
  report_path?: string;
  db_path?: string;
  state_available?: boolean;
  report_available?: boolean;
  last_backtest_ok?: boolean;
  last_backtest_at?: string;
  last_error?: string;
  updated_at?: string;
  loop_interval_sec?: number;
  supervisor_running?: boolean;
  supervisor_pid?: number | null;
  data_connection?: Record<string, unknown>;
  metrics?: Record<string, unknown>;
  symbols?: string[];
  default_strategy?: string;
  default_timeframe?: string;
  default_data_source?: string;
  risk?: Record<string, unknown>;
  last_backtest?: Record<string, unknown>;
  state?: Record<string, unknown>;
  report?: Record<string, unknown>;
}

export interface NautilusStrategy {
  id: string;
  label: string;
}

export interface NautilusBacktestRequest {
  symbol: string;
  timeframe: string;
  strategy: string;
  start_date?: string;
  end_date?: string;
  data_source?: string;
  mode?: string;
}

export interface NautilusBacktestResult {
  ok: boolean;
  error?: string;
  symbol?: string;
  timeframe?: string;
  strategy?: string;
  total_pnl?: number;
  win_rate?: number;
  max_drawdown?: number;
  trades?: number;
  bars?: number;
  data_source?: string;
  trade_log?: Array<Record<string, unknown>>;
  equity_curve?: Array<{ ts?: string; equity?: number }>;
  needs_api_key?: boolean;
}

export async function fetchNautilusValidations(symbols: string[]): Promise<{
  ok: boolean;
  validations: Record<string, NautilusSetupValidation>;
  gate?: Record<string, unknown>;
}> {
  const q = symbols.length ? `?symbols=${encodeURIComponent(symbols.join(','))}` : '';
  const res = await apiFetch(`/api/trading/nautilus/validations${q}`);
  if (!res.ok) throw new Error(`Nautilus validations failed: ${res.status}`);
  return res.json();
}

export async function fetchNautilusLearner(): Promise<{
  ok: boolean;
  learner: Record<string, unknown>;
  gate: Record<string, unknown>;
}> {
  const res = await apiFetch('/api/trading/nautilus/learner');
  if (!res.ok) throw new Error(`Nautilus learner failed: ${res.status}`);
  return res.json();
}

export async function fetchNautilusStatus(): Promise<NautilusStatus> {
  const res = await apiFetch('/api/trading/nautilus/status');
  if (!res.ok) throw new Error(`Nautilus status failed: ${res.status}`);
  return res.json();
}

export async function fetchNautilusStrategies(): Promise<{ ok: boolean; strategies: NautilusStrategy[] }> {
  const res = await apiFetch('/api/trading/nautilus/strategies');
  if (!res.ok) throw new Error(`Nautilus strategies failed: ${res.status}`);
  return res.json();
}

export async function fetchNautilusHistory(limit = 20): Promise<Record<string, unknown>> {
  const res = await apiFetch(`/api/trading/nautilus/history?limit=${limit}`);
  if (!res.ok) throw new Error(`Nautilus history failed: ${res.status}`);
  return res.json();
}

export async function runNautilusBacktest(body: NautilusBacktestRequest): Promise<NautilusBacktestResult> {
  const res = await apiFetch('/api/trading/nautilus/backtest', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || data.error || `Backtest failed: ${res.status}`);
  return data;
}

export async function startNautilusWorker(): Promise<{ ok: boolean; message: string }> {
  const res = await apiFetch('/api/trading/nautilus/start', { method: 'POST' });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || data.message || `Start failed: ${res.status}`);
  return data;
}

export async function stopNautilusWorker(): Promise<{ ok: boolean; message: string }> {
  const res = await apiFetch('/api/trading/nautilus/stop', { method: 'POST' });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || data.message || `Stop failed: ${res.status}`);
  return data;
}

export interface MarketGeniusSweepRow {
  symbol?: string;
  strategy?: string;
  win_rate?: number;
  total_pnl?: number;
  score?: number;
  passed?: boolean;
  bucket?: string;
  gate_reason?: string;
}

export interface HedgeFundDesk {
  ok?: boolean;
  philosophy?: string;
  error?: string;
  regime?: {
    available?: boolean;
    regime?: string;
    stance?: string;
    desk_note?: string;
    observation?: string;
    btc_trend_score?: number;
    vol_regime_score?: number;
    hybrid_score?: number;
    notes?: string[];
  };
  portfolio?: {
    equity?: number;
    return_pct?: number;
    realized_pnl?: number;
    session_pnl?: number;
    today_pnl?: number;
    open_positions?: number;
    closed_trades?: number;
    win_rate_pct?: number;
    wins?: number;
    losses?: number;
  };
  allocation?: {
    recommended_deploy_pct?: number;
    max_concurrent_bets?: number;
    rationale?: string[];
    method?: string;
    not_a_forecast?: boolean;
  };
  learned_edges?: {
    structure?: {
      trades_recorded?: number;
      combo_count?: number;
      best_structures?: Array<Record<string, unknown>>;
      worst_structures?: Array<Record<string, unknown>>;
      notes?: string[];
    };
    win_rate_optimizer?: {
      rolling_win_rate_pct?: number;
      rolling_samples?: number;
      optimizations?: number;
      blocked_combos?: string[];
      notes?: string[];
    };
    patterns?: {
      top?: Array<Record<string, unknown>>;
      blocked_symbols?: Array<Record<string, unknown>>;
    };
    nautilus?: Record<string, unknown>;
  };
  market_genius?: {
    enabled?: boolean;
    last_sweep_at?: number;
    tested?: number;
    works_count?: number;
    fails_count?: number;
    pass_rate_pct?: number;
    effective_min_win_rate?: number;
    works?: MarketGeniusSweepRow[];
    fails?: MarketGeniusSweepRow[];
    genius_notes?: string[];
  };
  playbook?: {
    active?: boolean;
    tier1_symbols?: string[];
    plan?: string[];
    executed_at?: number;
  };
  symbol_math?: {
    symbol_count?: number;
    updated_at?: number;
    notes?: string[];
    profiles?: Array<{
      symbol?: string;
      style?: string;
      repeatability?: number;
      swing_pct?: number;
      atr_pct?: number;
      trend_persistence?: number;
      win_rate?: number;
      samples?: number;
      median_winner_pct?: number;
      target_move_pct?: number;
      min_profit_pct?: number;
      min_hold_bars?: number;
      playbook_hint?: string;
      best_hours_utc?: number[];
    }>;
  };
  agents?: { running?: boolean; pid?: number | null };
  desk_notes?: string[];
}

export async function fetchHedgeFundDesk(): Promise<HedgeFundDesk> {
  const res = await apiFetch('/api/trading/hedge-fund/desk');
  const ct = res.headers.get('content-type') || '';
  const text = await res.text();
  if (!res.ok) {
    throw new Error(`Hedge fund desk failed: ${res.status}${text ? ` — ${text.slice(0, 200)}` : ''}`);
  }
  if (ct.includes('text/html') || text.trimStart().startsWith('<!DOCTYPE') || text.trimStart().startsWith('<html')) {
    throw new Error(
      'Hedge fund desk returned HTML instead of JSON — restart the Jarvis backend (jarvis stop && jarvis start) so /api/trading/hedge-fund/desk is registered.',
    );
  }
  try {
    return JSON.parse(text) as HedgeFundDesk;
  } catch {
    throw new Error(`Hedge fund desk response is not valid JSON: ${text.slice(0, 200)}`);
  }
}

export async function runHedgeFundSweep(force = true): Promise<Record<string, unknown>> {
  const res = await apiFetch(`/api/trading/hedge-fund/sweep?force=${force ? '1' : '0'}`, {
    method: 'POST',
  });
  const ct = res.headers.get('content-type') || '';
  const text = await res.text();
  if (!res.ok) {
    throw new Error(`Genius sweep failed: ${res.status}${text ? ` — ${text.slice(0, 200)}` : ''}`);
  }
  if (ct.includes('text/html') || text.trimStart().startsWith('<!DOCTYPE')) {
    throw new Error('Genius sweep returned HTML — restart Jarvis backend.');
  }
  return JSON.parse(text) as Record<string, unknown>;
}

export async function runHedgeFundExecute(): Promise<Record<string, unknown>> {
  const res = await apiFetch('/api/trading/hedge-fund/execute', { method: 'POST' });
  const ct = res.headers.get('content-type') || '';
  const text = await res.text();
  if (!res.ok) {
    throw new Error(`Execute playbook failed: ${res.status}${text ? ` — ${text.slice(0, 200)}` : ''}`);
  }
  if (ct.includes('text/html') || text.trimStart().startsWith('<!DOCTYPE')) {
    throw new Error('Execute playbook returned HTML — restart Jarvis backend.');
  }
  return JSON.parse(text) as Record<string, unknown>;
}

export async function runHedgeFundCheckSetups(): Promise<Record<string, unknown>> {
  const res = await apiFetch('/api/trading/hedge-fund/check-setups', { method: 'POST' });
  const ct = res.headers.get('content-type') || '';
  const text = await res.text();
  if (!res.ok) {
    throw new Error(`Check setups failed: ${res.status}${text ? ` — ${text.slice(0, 200)}` : ''}`);
  }
  if (ct.includes('text/html') || text.trimStart().startsWith('<!DOCTYPE')) {
    throw new Error('Check setups returned HTML — restart Jarvis backend.');
  }
  return JSON.parse(text) as Record<string, unknown>;
}

export async function runHedgeFundLearnSymbols(): Promise<Record<string, unknown>> {
  const res = await apiFetch('/api/trading/hedge-fund/learn-symbols', { method: 'POST' });
  const ct = res.headers.get('content-type') || '';
  const text = await res.text();
  if (!res.ok) {
    throw new Error(`Learn symbols failed: ${res.status}${text ? ` — ${text.slice(0, 200)}` : ''}`);
  }
  if (ct.includes('text/html') || text.trimStart().startsWith('<!DOCTYPE')) {
    throw new Error('Learn symbols returned HTML — restart Jarvis backend.');
  }
  return JSON.parse(text) as Record<string, unknown>;
}

/** Full tradingview.com site — use in Cursor Simple Browser to sign in with your TV account. */
export const TRADINGVIEW_FULL_SITE_URL = 'https://www.tradingview.com/';

export interface KnowledgeTool {
  id: string;
  label: string;
  role: string;
  installed: boolean;
  active: boolean;
  detail: string;
  repo?: string;
}

export interface KnowledgeStack {
  ok: boolean;
  updated_at: number;
  tools: KnowledgeTool[];
  vault: {
    path: string;
    note_count: number;
    has_config: boolean;
    recent_notes: { path: string; title: string; preview: string; mtime: number }[];
  };
  graph: { nodes: { id: string; label: string; group: string }[]; links: { source: string; target: string; kind?: string }[]; source: string };
  philosophy?: string;
}

export type ObsidianDesk = KnowledgeStack;

export async function fetchKnowledgeStack(): Promise<KnowledgeStack> {
  const res = await apiFetch('/api/knowledge/stack');
  if (!res.ok) throw new Error(`Knowledge stack failed: ${res.status}`);
  return res.json() as Promise<KnowledgeStack>;
}

export async function fetchObsidianDesk(): Promise<ObsidianDesk> {
  const res = await apiFetch('/api/knowledge/obsidian/desk');
  if (!res.ok) throw new Error(`Obsidian desk failed: ${res.status}`);
  return res.json() as Promise<ObsidianDesk>;
}

export async function runGraphify(): Promise<Record<string, unknown>> {
  const res = await apiFetch('/api/knowledge/graphify/run', { method: 'POST' });
  const text = await res.text();
  if (!res.ok) {
    throw new Error(text.slice(0, 300) || `Graphify failed: ${res.status}`);
  }
  return JSON.parse(text) as Record<string, unknown>;
}

export function tradingViewChartUrl(symbol: string): string {
  const encoded = encodeURIComponent(symbol.trim());
  return `https://www.tradingview.com/chart/?symbol=${encoded}`;
}

/** Jarvis full-screen TV page — paste into Cursor Simple Browser for an editor tab. */
export function jarvisTradingViewTabUrl(symbol?: string, interval = '5'): string {
  const params = new URLSearchParams({ interval });
  if (symbol?.trim()) params.set('symbol', symbol.trim());
  return `http://localhost:5173/tradingview?${params.toString()}`;
}

/** Full TV chart on tradingview.com (layouts, watchlists) — not the embed widget. */
export function tradingViewFullSiteChartUrl(symbol: string): string {
  return tradingViewChartUrl(symbol);
}

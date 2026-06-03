/**
 * Shared per-agent run state for the bug_fix domain.
 *
 * The BugFixRunDialog still owns the SSE consumption, but mirrors every
 * event into this module-level store so individual canvas nodes can
 * pop their own "what did THIS stage do?" dialog without re-subscribing
 * to the SSE stream themselves.
 *
 * --- Persistence ---
 * Every mutation is synced to localStorage so a page refresh doesn't
 * lose the run history. The key is scoped per flow:
 *   `bugfix-output-{flowId}`
 * On init the store tries to hydrate from localStorage; on reset it
 * clears the key.
 */
import { useSyncExternalStore } from 'react';
import type { RunPhase } from './run-controller';

export interface AgentProgressItem {
  status: string;
  ts: number;
}

export interface DecisionStep {
  step: string;
  description: string;
  details: Record<string, any>;
  confidence: number;
  ts: number;
}

interface NodeOutputState {
  /** Per-agent live token buffer (streaming Analyze, etc.). */
  streamingByAgent: Record<string, string>;
  /** Per-agent progress timeline (non-streaming status updates). */
  progressByAgent: Record<string, AgentProgressItem[]>;
  /** Per-agent decision steps (structured reasoning trace). */
  decisionStepsByAgent: Record<string, DecisionStep[]>;
  /** Final result payload (only set after the `complete` event). */
  result: any;
  /** Mirrors the run dialog's phase so per-node dialogs can show a
   *  blinking cursor while their stage is still running. */
  phase: RunPhase;
  /** Current flow run ID for workspace access. */
  runId: number | null;
}

const initial: NodeOutputState = {
  streamingByAgent: {},
  progressByAgent: {},
  decisionStepsByAgent: {},
  result: null,
  phase: 'idle',
  runId: null,
};

// ─── localStorage helpers ────────────────────────────────────

const STORAGE_KEY_PREFIX = 'bugfix-output-';
let currentFlowId: string | null = null;

function storageKey(): string {
  return `${STORAGE_KEY_PREFIX}${currentFlowId ?? 'default'}`;
}

function persist(): void {
  try {
    localStorage.setItem(storageKey(), JSON.stringify(state));
  } catch {
    // localStorage full or unavailable — silent fail, in-memory still works
  }
}

function hydrate(flowId: string | null): NodeOutputState {
  try {
    const key = `${STORAGE_KEY_PREFIX}${flowId ?? 'default'}`;
    const raw = localStorage.getItem(key);
    if (raw) {
      const parsed = JSON.parse(raw) as NodeOutputState;
      // Basic sanity check
      if (parsed && typeof parsed.phase === 'string') {
        return parsed;
      }
    }
  } catch {
    // Corrupted data — fall through to initial
  }
  return { ...initial };
}

// ─── Store core ──────────────────────────────────────────────

let state: NodeOutputState = initial;
const listeners = new Set<() => void>();

function emit() {
  for (const l of listeners) l();
  persist();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/**
 * Switch the flow context — hydrates from localStorage for the new flow.
 * Called when the user switches tabs or the flowId changes.
 */
export function switchFlowContext(flowId: string | null): void {
  currentFlowId = flowId;
  state = hydrate(flowId);
  emit(); // notify subscribers + persist
}

export function resetNodeOutput(): void {
  state = { ...initial, streamingByAgent: {}, progressByAgent: {} };
  emit();
  // Also clear localStorage for this flow
  try {
    localStorage.removeItem(storageKey());
  } catch {
    // ignore
  }
  // Re-persist the clean state
  persist();
}

export function appendStreamChunk(agentId: string, chunk: string): void {
  state = {
    ...state,
    streamingByAgent: {
      ...state.streamingByAgent,
      [agentId]: (state.streamingByAgent[agentId] ?? '') + chunk,
    },
  };
  emit();
}

export function appendProgress(agentId: string, status: string): void {
  state = {
    ...state,
    progressByAgent: {
      ...state.progressByAgent,
      [agentId]: [
        ...(state.progressByAgent[agentId] ?? []),
        { status, ts: Date.now() },
      ],
    },
  };
  emit();
}

export function appendDecisionStep(agentId: string, step: Omit<DecisionStep, 'ts'>): void {
  state = {
    ...state,
    decisionStepsByAgent: {
      ...state.decisionStepsByAgent,
      [agentId]: [
        ...(state.decisionStepsByAgent[agentId] ?? []),
        { ...step, ts: Date.now() },
      ],
    },
  };
  emit();
}

export function setResult(result: any): void {
  state = { ...state, result };
  emit();
}

export function setPhase(phase: RunPhase): void {
  state = { ...state, phase };
  emit();
}

export function setRunId(runId: number | null): void {
  state = { ...state, runId };
  emit();
}

export function getSnapshot(): NodeOutputState {
  return state;
}

export function useNodeOutput(): NodeOutputState {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}
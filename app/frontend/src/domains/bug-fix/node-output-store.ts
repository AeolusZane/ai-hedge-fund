/**
 * Shared per-agent run state for the bug_fix domain.
 *
 * The BugFixRunDialog still owns the SSE consumption, but mirrors every
 * event into this module-level store so individual canvas nodes can
 * pop their own "what did THIS stage do?" dialog without re-subscribing
 * to the SSE stream themselves.
 */
import { useSyncExternalStore } from 'react';
import type { RunPhase } from './run-controller';

export interface AgentProgressItem {
  status: string;
  ts: number;
}

interface NodeOutputState {
  /** Per-agent live token buffer (streaming Analyze, etc.). */
  streamingByAgent: Record<string, string>;
  /** Per-agent progress timeline (non-streaming status updates). */
  progressByAgent: Record<string, AgentProgressItem[]>;
  /** Final result payload (only set after the `complete` event). */
  result: any;
  /** Mirrors the run dialog's phase so per-node dialogs can show a
   *  blinking cursor while their stage is still running. */
  phase: RunPhase;
}

const initial: NodeOutputState = {
  streamingByAgent: {},
  progressByAgent: {},
  result: null,
  phase: 'idle',
};

let state: NodeOutputState = initial;
const listeners = new Set<() => void>();

function emit() {
  for (const l of listeners) l();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function resetNodeOutput(): void {
  state = { ...initial, streamingByAgent: {}, progressByAgent: {} };
  emit();
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

export function setResult(result: any): void {
  state = { ...state, result };
  emit();
}

export function setPhase(phase: RunPhase): void {
  state = { ...state, phase };
  emit();
}

export function getSnapshot(): NodeOutputState {
  return state;
}

export function useNodeOutput(): NodeOutputState {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}

/**
 * Run history store — records metadata for every bug_fix run so the
 * user can browse past runs even after the page is refreshed.
 *
 * Data is persisted to localStorage under `bugfix-history-{flowId}`.
 * The store keeps at most 10 recent runs per flow.
 */
import { useSyncExternalStore } from 'react';
import type { NodeStatus } from '@/nodes/utils';
import type { RunPhase } from './run-controller';

export interface StageSnapshot {
  status: NodeStatus;
  startedAt: number;
  completedAt?: number;
  outputSummary?: string;
}

export interface RunRecord {
  /** Unique run ID (timestamp-based). */
  id: string;
  /** Flow this run belongs to. */
  flowId: string;
  /** Jira issue key used for this run. */
  issueKey: string;
  /** When the run started. */
  startedAt: number;
  /** When the run completed (or errored). */
  completedAt?: number;
  /** Final phase of the run. */
  phase: RunPhase;
  /** Per-stage snapshots captured as stages complete. */
  stageSnapshots: Record<string, StageSnapshot>;
}

const MAX_HISTORY = 10;
const STORAGE_KEY_PREFIX = 'bugfix-history-';

interface RunHistoryState {
  runs: RunRecord[];
}

const initial: RunHistoryState = { runs: [] };

let state: RunHistoryState = initial;
let currentFlowId: string | null = null;
const listeners = new Set<() => void>();

function emit() {
  for (const l of listeners) l();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function storageKey(): string {
  return `${STORAGE_KEY_PREFIX}${currentFlowId ?? 'default'}`;
}

function persist(): void {
  try {
    localStorage.setItem(storageKey(), JSON.stringify(state));
  } catch {
    // silent
  }
}

function hydrate(flowId: string | null): RunHistoryState {
  try {
    const key = `${STORAGE_KEY_PREFIX}${flowId ?? 'default'}`;
    const raw = localStorage.getItem(key);
    if (raw) {
      const parsed = JSON.parse(raw) as RunHistoryState;
      if (parsed && Array.isArray(parsed.runs)) {
        return parsed;
      }
    }
  } catch {
    // corrupted — fall through
  }
  return { ...initial };
}

// ─── Public API ──────────────────────────────────────────────

/** Switch flow context — hydrates history for the new flow. */
export function switchHistoryContext(flowId: string | null): void {
  currentFlowId = flowId;
  state = hydrate(flowId);
  emit();
}

/** Start a new run record. Returns the run ID. */
export function startRun(flowId: string, issueKey: string): string {
  const id = `run-${Date.now()}`;
  const record: RunRecord = {
    id,
    flowId,
    issueKey,
    startedAt: Date.now(),
    phase: 'running',
    stageSnapshots: {},
  };
  state = {
    runs: [record, ...state.runs].slice(0, MAX_HISTORY),
  };
  persist();
  emit();
  return id;
}

/** Update a stage snapshot within the current (most recent) run. */
export function updateStageSnapshot(
  agentId: string,
  snapshot: StageSnapshot
): void {
  if (state.runs.length === 0) return;
  const current = state.runs[0];
  state = {
    runs: [
      {
        ...current,
        stageSnapshots: {
          ...current.stageSnapshots,
          [agentId]: snapshot,
        },
      },
      ...state.runs.slice(1),
    ],
  };
  persist();
  emit();
}

/** Mark the current run as complete or error. */
export function finishRun(phase: RunPhase): void {
  if (state.runs.length === 0) return;
  const current = state.runs[0];
  state = {
    runs: [
      {
        ...current,
        completedAt: Date.now(),
        phase,
      },
      ...state.runs.slice(1),
    ],
  };
  persist();
  emit();
}

export function getSnapshot(): RunHistoryState {
  return state;
}

export function useRunHistory(): RunHistoryState {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}

/** Get the most recent run (or null if no history). */
export function getLatestRun(): RunRecord | null {
  return state.runs[0] ?? null;
}
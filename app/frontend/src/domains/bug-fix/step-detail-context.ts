/**
 * Step detail context — controls what the right sidebar shows when in
 * "detail" mode. When a user clicks a stage node on the canvas or a
 * timeline entry in the Output Tab, this store records which step to
 * inspect, and the sidebar switches from the component palette to the
 * Step Detail Panel (Layer 3 Micro).
 */
import { useSyncExternalStore } from 'react';

export interface StepDetailTarget {
  /** The canvas node / agent id being inspected. */
  agentId: string;
  /** Human-readable stage name (e.g. "Analyze", "Patch"). */
  stageName: string;
}

let target: StepDetailTarget | null = null;
const listeners = new Set<() => void>();

function emit() {
  for (const l of listeners) l();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Open the detail panel for a specific step. */
export function openStepDetail(agentId: string, stageName: string): void {
  target = { agentId, stageName };
  emit();
}

/** Close the detail panel — return to component palette. */
export function closeStepDetail(): void {
  target = null;
  emit();
}

export function getSnapshot(): StepDetailTarget | null {
  return target;
}

export function useStepDetailTarget(): StepDetailTarget | null {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}
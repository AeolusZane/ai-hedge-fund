/**
 * Tiny module-level bus that lets a canvas node (the Jira Issue Input
 * node's Play button) ask the always-mounted Run dialog to open and
 * start a run. The dialog registers `trigger` on mount; the node
 * imports `requestRun` and calls it from its click handler.
 *
 * We also expose a phase store so the node can flip its Play to Stop
 * while a run is in flight without owning that state itself.
 */
import { useSyncExternalStore } from 'react';

export type RunPhase = 'idle' | 'running' | 'complete' | 'error';

let triggerFn: (() => void) | null = null;
let stopFn: (() => void) | null = null;

let phase: RunPhase = 'idle';
const phaseListeners = new Set<() => void>();

export function registerRunTrigger(fn: () => void): () => void {
  triggerFn = fn;
  return () => {
    if (triggerFn === fn) triggerFn = null;
  };
}

export function registerStopTrigger(fn: () => void): () => void {
  stopFn = fn;
  return () => {
    if (stopFn === fn) stopFn = null;
  };
}

export function requestRun(): void {
  triggerFn?.();
}

export function requestStop(): void {
  stopFn?.();
}

export function setRunPhase(next: RunPhase): void {
  if (phase === next) return;
  phase = next;
  phaseListeners.forEach((fn) => fn());
}

export function useRunPhase(): RunPhase {
  return useSyncExternalStore(
    (cb) => {
      phaseListeners.add(cb);
      return () => phaseListeners.delete(cb);
    },
    () => phase,
    () => phase
  );
}

import { useEffect, useRef, useState } from 'react';

/**
 * Coding-branch flow-connection manager.
 *
 * The original implementation drove the finance hedge-fund SSE runs.
 * In the coding/bug-fix branch each domain owns its own run controller
 * (see `domains/bug-fix/run-controller.ts`), so the only thing we need
 * to expose here is a tiny state store that the flow tabs / left
 * sidebar can read for "is this flow currently running?".
 *
 * Anything that wants to drive a run should mutate state via
 * `flowConnectionManager.setConnection(...)`; we keep the API surface
 * compatible with the previous callers so future domains can adopt it.
 */
export type FlowConnectionState = 'idle' | 'connecting' | 'connected' | 'error' | 'completed';

interface FlowConnectionInfo {
  state: FlowConnectionState;
  abortController: (() => void) | null;
  startTime: number;
  lastActivity: number;
  error?: string;
}

const idleConnection = (): FlowConnectionInfo => ({
  state: 'idle',
  abortController: null,
  startTime: 0,
  lastActivity: 0,
});

class FlowConnectionManager {
  private connections = new Map<string, FlowConnectionInfo>();
  private listeners = new Set<() => void>();

  getConnection(flowId: string): FlowConnectionInfo {
    return this.connections.get(flowId) || idleConnection();
  }

  setConnection(flowId: string, info: Partial<FlowConnectionInfo>): void {
    const existing = this.getConnection(flowId);
    this.connections.set(flowId, {
      ...existing,
      ...info,
      lastActivity: Date.now(),
    });
    this.notifyListeners();
  }

  removeConnection(flowId: string): void {
    const connection = this.connections.get(flowId);
    if (connection?.abortController) connection.abortController();
    this.connections.delete(flowId);
    this.notifyListeners();
  }

  addListener(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private notifyListeners(): void {
    this.listeners.forEach((listener) => listener());
  }
}

export const flowConnectionManager = new FlowConnectionManager();

export function useFlowConnectionState(flowId: string | null) {
  const [, forceUpdate] = useState({});
  const listenerRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (!flowId) return;
    const unsubscribe = flowConnectionManager.addListener(() => forceUpdate({}));
    listenerRef.current = unsubscribe;
    return unsubscribe;
  }, [flowId]);

  return flowId ? flowConnectionManager.getConnection(flowId) : null;
}

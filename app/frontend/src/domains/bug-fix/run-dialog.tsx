import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { useFlowContext } from '@/contexts/flow-context';
import { useLayoutContext } from '@/contexts/layout-context';
import { useNodeContext } from '@/contexts/node-context';
import type { DomainRunDialogProps } from '@/core/types/domain-pack';
import { getNodeInternalState } from '@/hooks/use-node-state';
import { cn } from '@/lib/utils';
import { useReactFlow } from '@xyflow/react';
import { Loader2, Play, Square } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  registerDialogOpener,
  registerRunTrigger,
  registerStopTrigger,
  setRunPhase,
} from './run-controller';
import {
  appendProgress as storeAppendProgress,
  appendStreamChunk as storeAppendStreamChunk,
  resetNodeOutput as storeResetNodeOutput,
  setPhase as storeSetPhase,
  setResult as storeSetResult,
} from './node-output-store';
import { startRun as historyStartRun, finishRun as historyFinishRun, updateStageSnapshot as historyUpdateStageSnapshot } from './run-history-store';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

type Phase = 'idle' | 'running' | 'complete' | 'error';

interface ProgressItem {
  agent: string | null;
  status: string;
}

/**
 * Self-contained Run UI for the bug_fix domain.
 *
 * Posts the user-entered Jira issue key to /workflows/bug_fix/run, consumes
 * the SSE stream inline (no shared SSE helper yet), and renders live
 * progress + the final result blob. Cancellation aborts the fetch which
 * closes the SSE connection on the backend.
 */
export function BugFixRunDialog({ open, onOpenChange }: DomainRunDialogProps) {
  const reactFlow = useReactFlow();
  const { currentFlowId } = useFlowContext();
  const { updateAgentNode, updateAgentNodes } = useNodeContext();
  const { expandBottomPanel, setBottomPanelTab } = useLayoutContext();
  const flowKey = currentFlowId?.toString() || null;
  const [issueKey, setIssueKey] = useState('');
  const [phase, setPhase] = useState<Phase>('idle');
  const [progress, setProgress] = useState<ProgressItem[]>([]);
  // Per-agent live token buffer. Each streaming stage (currently just
  // Analyze) appends chunks here so the UI can show the model's response
  // as it grows instead of staring at "Analyzing root cause" for 30s.
  const [streamingByAgent, setStreamingByAgent] = useState<Record<string, string>>({});
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const startRunRef = useRef<(() => void) | null>(null);
  const stopRunRef = useRef<(() => void) | null>(null);

  // Snapshot the canvas at submit time. Empty arrays = caller wants the
  // default sequence; the backend falls back gracefully. Both the input
  // node (which performs the implicit fetch) and the stage tiles count.
  const canvasStageCount = useMemo(
    () =>
      reactFlow
        .getNodes()
        .filter(
          (n) =>
            n.type === 'bug-fix-stage-node' ||
            n.type === 'jira-issue-input-node'
        ).length,
    [reactFlow, open]
  );

  // If the canvas has a JiraIssueInputNode, the issue key lives there
  // (persisted via useNodeState). The dialog's own input box is hidden.
  const canvasIssueKey = useMemo(() => {
    if (!open) return null;
    const inputNode = reactFlow
      .getNodes()
      .find((n) => n.type === 'jira-issue-input-node');
    if (!inputNode) return null;
    const stored = getNodeInternalState(inputNode.id)?.issueKey;
    return typeof stored === 'string' ? stored : '';
  }, [reactFlow, open]);
  const canvasOwnsIssue = canvasIssueKey !== null;
  const effectiveIssueKey = canvasOwnsIssue ? canvasIssueKey ?? '' : issueKey;

  const reset = useCallback(() => {
    setPhase('idle');
    setProgress([]);
    setStreamingByAgent({});
    setResult(null);
    setError(null);
    storeResetNodeOutput();
  }, []);

  // Closing the dialog should NOT kill the run — the dialog is a
  // viewer for an SSE stream the run-controller owns. The user can
  // explicitly hit Stop (here or on the Jira Issue Input node) to
  // abort. Without this, reopening the dialog mid-run would surface
  // "Run" instead of "Stop" because the abort had already cleared
  // the phase.

  // Mirror the dialog's phase into the shared store so the canvas Play
  // button can swap to Stop while a run is in flight.
  useEffect(() => {
    setRunPhase(phase);
    storeSetPhase(phase);
  }, [phase]);

  // Let canvas nodes pop the dialog open via the run-controller bus.
  useEffect(() => registerDialogOpener(() => onOpenChange(true)), [onOpenChange]);

  // Expose start/stop to the module-level controller so a canvas node
  // (the Jira Issue Input's Play button) can request a run without
  // opening the dialog first. The dialog stays closed during the run —
  // canvas nodes light up in place and a node click reopens the dialog
  // for users who want to see progress / results in detail.
  useEffect(() => {
    return registerRunTrigger(() => {
      queueMicrotask(() => startRunRef.current?.());
    });
  }, []);

  useEffect(() => {
    return registerStopTrigger(() => stopRunRef.current?.());
  }, []);

  const startRun = useCallback(async () => {
    // Always read the canvas Jira Issue Input at submit time —
    // `canvasIssueKey` memo gates on `open`, so a run triggered from
    // the canvas while the dialog is closed would otherwise see an
    // empty effectiveIssueKey and bail out silently.
    const liveCanvasNode = reactFlow
      .getNodes()
      .find((n) => n.type === 'jira-issue-input-node');
    const liveCanvasKey = liveCanvasNode
      ? getNodeInternalState(liveCanvasNode.id)?.issueKey
      : undefined;
    const effective =
      typeof liveCanvasKey === 'string' && liveCanvasKey.trim()
        ? liveCanvasKey
        : issueKey;
    const trimmed = effective.trim();
    if (!trimmed) return;
    reset();
    setPhase('running');

    // Record this run in history store
    historyStartRun(flowKey ?? 'default', trimmed);

    const controller = new AbortController();
    abortRef.current = controller;

    // Snapshot the canvas at submit time so node ids in progress events
    // line up with whatever the user can see. The Jira Issue Input node
    // is included alongside the stage tiles — it performs the implicit
    // fetch as the first runnable node. For LLM-using stages (today:
    // Analyze), fold in the per-node model preference stored via
    // useNodeState — the backend reads it from node.data.
    const runnableNodes = reactFlow
      .getNodes()
      .filter(
        (n) =>
          n.type === 'bug-fix-stage-node' ||
          n.type === 'jira-issue-input-node'
      )
      .map((n) => {
        const internal = getNodeInternalState(n.id);
        if (!internal) return n;
        // Fold the per-node persisted state into node.data so the
        // backend can read modelName, repoPath, project / repo /
        // targetBranch, etc. directly.
        return {
          ...n,
          data: {
            ...n.data,
            ...(internal.modelName ? { modelName: internal.modelName } : {}),
            ...(internal.modelProvider ? { modelProvider: internal.modelProvider } : {}),
            ...(internal.repoPath ? { repoPath: internal.repoPath } : {}),
            ...(internal.project ? { project: internal.project } : {}),
            ...(internal.repo ? { repo: internal.repo } : {}),
            ...(internal.targetBranch ? { targetBranch: internal.targetBranch } : {}),
          },
        };
      });
    const runnableIds = new Set(runnableNodes.map((n) => n.id));
    const runnableEdges = reactFlow
      .getEdges()
      .filter((e) => runnableIds.has(e.source) && runnableIds.has(e.target));

    // Reset every runnable node to IDLE so previous run colors don't bleed in.
    if (runnableNodes.length > 0) {
      updateAgentNodes(flowKey, Array.from(runnableIds), 'IDLE');
    }

    try {
      const response = await fetch(`${API_BASE_URL}/workflows/bug_fix/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          payload: {
            jira_issue: trimmed,
            stage_delay_seconds: 0.1,
            graph_nodes: runnableNodes,
            graph_edges: runnableEdges,
          },
        }),
        signal: controller.signal,
      });
      if (!response.ok || !response.body) {
        throw new Error(`HTTP ${response.status}`);
      }

      // Close dialog and switch to Output Tab — progress now lives there
      onOpenChange(false);
      setBottomPanelTab('output');
      expandBottomPanel();

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // SSE events are separated by blank lines.
        const events = buffer.split('\n\n');
        buffer = events.pop() ?? '';
        for (const block of events) {
          const dataLine = block
            .split('\n')
            .find((line) => line.startsWith('data:'));
          if (!dataLine) continue;
          try {
            const data = JSON.parse(dataLine.slice(5).trim());
            handleEvent(data);
          } catch {
            // Ignore malformed payloads
          }
        }
      }

      setPhase((cur) => (cur === 'running' ? 'complete' : cur));
    } catch (e: any) {
      if (e?.name === 'AbortError') {
        setPhase('idle');
        return;
      }
      setError(e?.message ?? 'Run failed');
      setPhase('error');
    } finally {
      abortRef.current = null;
    }
  }, [issueKey, reset, reactFlow]);

  const handleEvent = (data: any) => {
    if (!data || typeof data !== 'object') return;
    if (data.type === 'progress') {
      // Streaming token chunk — append to that agent's live buffer
      // instead of polluting the status timeline with one row per token.
      if (typeof data.chunk === 'string') {
        const agent = data.agent ?? '__global__';
        setStreamingByAgent((prev) => ({
          ...prev,
          [agent]: (prev[agent] ?? '') + data.chunk,
        }));
        storeAppendStreamChunk(agent, data.chunk);
        if (data.agent) {
          updateAgentNode(flowKey, data.agent, 'IN_PROGRESS');
        }
        return;
      }
      setProgress((prev) => [
        ...prev,
        { agent: data.agent ?? null, status: data.status ?? '' },
      ]);
      if (data.agent) {
        storeAppendProgress(data.agent, data.status ?? '');
      }
      // Light up the matching canvas node (no-op when the executor used
      // the default 5-stage fallback because those agent ids are stage
      // keys, not canvas ids).
      if (data.agent) {
        updateAgentNode(
          flowKey,
          data.agent,
          data.status === 'Done' ? 'COMPLETE' : 'IN_PROGRESS'
        );
        // Record stage snapshot in history
        historyUpdateStageSnapshot(data.agent, {
          status: data.status === 'Done' ? 'COMPLETE' : 'IN_PROGRESS',
          startedAt: Date.now(),
          outputSummary: data.status,
        });
      }
    } else if (data.type === 'complete') {
      setResult(data.data);
      storeSetResult(data.data);
      setPhase('complete');
      setRunPhase('complete');
      historyFinishRun('complete');
    } else if (data.type === 'error') {
      setError(data.message ?? 'Run failed');
      setPhase('error');
      setRunPhase('error');
      historyFinishRun('error');
    }
  };

  const stop = useCallback(() => {
    if (abortRef.current) abortRef.current.abort();
  }, []);

  // Keep refs aimed at the latest callbacks so the controller doesn't
  // capture stale closures.
  useEffect(() => {
    startRunRef.current = startRun;
    stopRunRef.current = stop;
  }, [startRun, stop]);

  const running = phase === 'running';

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            Run Bug Fix
            <Badge variant={canvasStageCount > 0 ? 'success' : 'secondary'} className="text-[10px]">
              {canvasStageCount > 0
                ? `${canvasStageCount} stage${canvasStageCount === 1 ? '' : 's'} from canvas`
                : 'default 5-stage sequence'}
            </Badge>
          </DialogTitle>
          <DialogDescription>
            {canvasStageCount > 0
              ? 'Stages run in the order defined by the canvas edges (topological).'
              : 'No stage nodes on the canvas — falling back to the built-in sequence.'}
            {' Only Fetch Jira hits the real MCP server today.'}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="flex items-center gap-2">
            {canvasOwnsIssue ? (
              <div className="flex-1 flex items-center gap-2 border rounded-md px-3 py-1.5 bg-muted/40 text-xs">
                <Badge variant="outline" className="text-[10px]">
                  from canvas
                </Badge>
                <span className="font-mono">
                  {effectiveIssueKey.trim() || '(empty — edit the Jira Issue Input node)'}
                </span>
              </div>
            ) : (
              <Input
                autoFocus
                placeholder="Jira issue key (e.g. BI-158957)"
                value={issueKey}
                onChange={(e) => setIssueKey(e.target.value)}
                disabled={running}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') startRun();
                }}
              />
            )}
            {running ? (
              <Button variant="destructive" onClick={stop}>
                <Square className="mr-2 h-4 w-4" /> Stop
              </Button>
            ) : (
              <Button onClick={startRun} disabled={!effectiveIssueKey.trim()}>
                <Play className="mr-2 h-4 w-4" /> Run
              </Button>
            )}
          </div>

          {progress.length > 0 && (
            <div className="border rounded-md p-2 max-h-48 overflow-y-auto text-xs font-mono">
              {progress.map((p, i) => (
                <div
                  key={i}
                  className={cn(
                    'flex items-center gap-2 py-0.5',
                    p.status === 'Done' && 'text-muted-foreground'
                  )}
                >
                  {p.agent && (
                    <Badge variant="outline" className="text-[10px]">
                      {p.agent}
                    </Badge>
                  )}
                  <span>{p.status}</span>
                </div>
              ))}
              {running && (
                <div className="flex items-center gap-2 py-0.5 text-muted-foreground">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  <span>waiting…</span>
                </div>
              )}
            </div>
          )}

          {Object.entries(streamingByAgent).map(([agent, text]) => (
            <div key={`stream-${agent}`} className="border rounded-md p-2 space-y-1 text-xs">
              <div className="flex items-center gap-2">
                <Badge variant="outline" className="text-[10px]">
                  {agent}
                </Badge>
                <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                  streaming
                </span>
              </div>
              <pre className="whitespace-pre-wrap font-mono text-[11px] bg-muted/30 rounded p-2 max-h-64 overflow-auto">
                {text}
                {running && <span className="animate-pulse">▍</span>}
              </pre>
            </div>
          ))}

          {error && (
            <div className="border border-destructive/40 rounded-md p-2 text-xs text-destructive">
              {error}
            </div>
          )}

          {result && (
            <div className="space-y-2">
              <div className="text-xs font-semibold">Result</div>
              {result.summary && (
                <div className="text-sm">{result.summary}</div>
              )}
              {result.jira && (
                <div className="grid grid-cols-3 gap-2 text-xs text-muted-foreground">
                  <div>Status: <span className="text-foreground">{result.jira.status}</span></div>
                  <div>Assignee: <span className="text-foreground">{result.jira.assignee}</span></div>
                  <div>Priority: <span className="text-foreground">{result.jira.priority}</span></div>
                </div>
              )}
              {result.analysis && (
                <div className="border rounded-md p-2 space-y-1 text-xs bg-muted/20">
                  <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                    LLM analysis
                  </div>
                  {result.analysis.root_cause_hypothesis && (
                    <div><span className="text-muted-foreground">Root cause: </span>{result.analysis.root_cause_hypothesis}</div>
                  )}
                  {Array.isArray(result.analysis.affected_areas) && result.analysis.affected_areas.length > 0 && (
                    <div><span className="text-muted-foreground">Areas: </span>{result.analysis.affected_areas.join(', ')}</div>
                  )}
                  {Array.isArray(result.analysis.suggested_approach) && result.analysis.suggested_approach.length > 0 && (
                    <div>
                      <span className="text-muted-foreground">Approach:</span>
                      <ul className="list-disc pl-4">
                        {result.analysis.suggested_approach.map((s: string, i: number) => <li key={i}>{s}</li>)}
                      </ul>
                    </div>
                  )}
                </div>
              )}
              {result.analyze_error && (
                <div className="text-xs text-destructive">Analyze: {result.analyze_error}</div>
              )}

              {result.patch && (
                <div className="border rounded-md p-2 space-y-1 text-xs bg-muted/20">
                  <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                    Patch
                  </div>
                  {Array.isArray(result.patch.files_changed) && result.patch.files_changed.length > 0 && (
                    <div>
                      <span className="text-muted-foreground">Files: </span>
                      {result.patch.files_changed.join(', ')}
                    </div>
                  )}
                  {result.patch.claude_output && (
                    <details>
                      <summary className="cursor-pointer text-muted-foreground">Claude output</summary>
                      <pre className="whitespace-pre-wrap text-xs bg-background p-2 rounded max-h-48 overflow-auto">{result.patch.claude_output}</pre>
                    </details>
                  )}
                  {result.patch.diff && (
                    <details>
                      <summary className="cursor-pointer text-muted-foreground">
                        Diff{result.patch.diff_truncated ? ' (truncated)' : ''}
                      </summary>
                      <pre className="whitespace-pre-wrap text-xs bg-background p-2 rounded max-h-64 overflow-auto">{result.patch.diff}</pre>
                    </details>
                  )}
                </div>
              )}
              {result.patch_error && (
                <div className="text-xs text-destructive">Patch: {result.patch_error}</div>
              )}

              {result.open_pr && (
                <div className="border rounded-md p-2 space-y-1 text-xs bg-muted/20">
                  <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                    Open PR
                  </div>
                  <div>
                    <span className="text-muted-foreground">Branch: </span>
                    <span className="font-mono">{result.open_pr.branch}</span>
                  </div>
                  {result.open_pr.pr && (
                    <details>
                      <summary className="cursor-pointer text-muted-foreground">Bitbucket payload</summary>
                      <pre className="whitespace-pre-wrap text-xs bg-background p-2 rounded max-h-48 overflow-auto">
                        {JSON.stringify(result.open_pr.pr, null, 2)}
                      </pre>
                    </details>
                  )}
                </div>
              )}
              {result.open_pr_error && (
                <div className="text-xs text-destructive">Open PR: {result.open_pr_error}</div>
              )}
              <details className="text-xs">
                <summary className="cursor-pointer text-muted-foreground">Raw payload</summary>
                <pre className="bg-muted/40 rounded p-2 max-h-64 overflow-auto">
                  {JSON.stringify(result, null, 2)}
                </pre>
              </details>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

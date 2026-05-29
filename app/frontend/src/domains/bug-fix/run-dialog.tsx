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
import type { DomainRunDialogProps } from '@/core/types/domain-pack';
import { cn } from '@/lib/utils';
import { useReactFlow } from '@xyflow/react';
import { Loader2, Play, Square } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

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
  const [issueKey, setIssueKey] = useState('');
  const [phase, setPhase] = useState<Phase>('idle');
  const [progress, setProgress] = useState<ProgressItem[]>([]);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Snapshot the canvas at submit time. Empty arrays = caller wants the
  // default 5-stage sequence; the backend falls back gracefully.
  const canvasStageCount = useMemo(
    () => reactFlow.getNodes().filter((n) => n.type === 'bug-fix-stage-node').length,
    // Re-compute when the dialog opens so the badge reflects current canvas.
    [reactFlow, open]
  );

  const reset = useCallback(() => {
    setPhase('idle');
    setProgress([]);
    setResult(null);
    setError(null);
  }, []);

  // Cancel any in-flight run when the dialog is closed.
  useEffect(() => {
    if (!open && abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
  }, [open]);

  const startRun = useCallback(async () => {
    const trimmed = issueKey.trim();
    if (!trimmed) return;
    reset();
    setPhase('running');

    const controller = new AbortController();
    abortRef.current = controller;

    // Snapshot the canvas at submit time so node ids in progress events
    // line up with whatever the user can see.
    const stageNodes = reactFlow
      .getNodes()
      .filter((n) => n.type === 'bug-fix-stage-node');
    const stageNodeIds = new Set(stageNodes.map((n) => n.id));
    const stageEdges = reactFlow
      .getEdges()
      .filter((e) => stageNodeIds.has(e.source) && stageNodeIds.has(e.target));

    try {
      const response = await fetch(`${API_BASE_URL}/workflows/bug_fix/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          payload: {
            jira_issue: trimmed,
            stage_delay_seconds: 0.1,
            graph_nodes: stageNodes,
            graph_edges: stageEdges,
          },
        }),
        signal: controller.signal,
      });
      if (!response.ok || !response.body) {
        throw new Error(`HTTP ${response.status}`);
      }

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
  }, [issueKey, reset]);

  const handleEvent = (data: any) => {
    if (!data || typeof data !== 'object') return;
    if (data.type === 'progress') {
      setProgress((prev) => [
        ...prev,
        { agent: data.agent ?? null, status: data.status ?? '' },
      ]);
    } else if (data.type === 'complete') {
      setResult(data.data);
      setPhase('complete');
    } else if (data.type === 'error') {
      setError(data.message ?? 'Run failed');
      setPhase('error');
    }
  };

  const stop = () => {
    if (abortRef.current) abortRef.current.abort();
  };

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
            {running ? (
              <Button variant="destructive" onClick={stop}>
                <Square className="mr-2 h-4 w-4" /> Stop
              </Button>
            ) : (
              <Button onClick={startRun} disabled={!issueKey.trim()}>
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
              {result.pr_url && (
                <div className="text-xs">
                  Stub PR: <a className="underline" href={result.pr_url} target="_blank" rel="noreferrer">{result.pr_url}</a>
                </div>
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

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useNodeOutput } from '@/domains/bug-fix/node-output-store';
import { useStepDetailTarget, closeStepDetail } from '@/domains/bug-fix/step-detail-context';
import { cn } from '@/lib/utils';
import type { NodeStatus } from '@/nodes/utils';
import { getStatusColor, elapsedSeconds } from '@/nodes/utils';
import { CheckCircle2, Loader2, XCircle, Pause, ArrowLeft, RotateCcw } from 'lucide-react';
import { useMemo } from 'react';

function StatusIcon({ status }: { status: NodeStatus }) {
  switch (status) {
    case 'IN_PROGRESS': return <Loader2 className="h-4 w-4 animate-spin" />;
    case 'COMPLETE': return <CheckCircle2 className="h-4 w-4" />;
    case 'ERROR': return <XCircle className="h-4 w-4" />;
    case 'PAUSED': return <Pause className="h-4 w-4" />;
    default: return null;
  }
}

/**
 * Step Detail Panel — Layer 3 Micro.
 *
 * Shows the full reasoning chain, progress timeline, and structured
 * output for a single bug_fix stage. Lives in the right sidebar when
 * the user clicks a stage node or timeline entry.
 */
export function StepDetailPanel() {
  const target = useStepDetailTarget();
  const nodeOutput = useNodeOutput();

  if (!target) return null;

  const { agentId, stageName } = target;
  const stream = nodeOutput.streamingByAgent[agentId] ?? '';
  const progressItems = nodeOutput.progressByAgent[agentId] ?? [];
  const result = nodeOutput.result;

  // Derive status
  const lastProgress = progressItems[progressItems.length - 1];
  const isDone = lastProgress?.status === 'Done';
  const status: NodeStatus = isDone ? 'COMPLETE' : (progressItems.length > 0 ? 'IN_PROGRESS' : 'IDLE') as NodeStatus;

  // Derive elapsed
  const startedAt = progressItems[0]?.ts;
  const completedAt = isDone ? lastProgress?.ts : undefined;
  const elapsed = startedAt ? elapsedSeconds({ status, startedAt, completedAt }) : null;

  // Extract result slice for this stage
  const resultSlice = useMemo(() => sliceFor(stageName, result), [stageName, result]);

  const fmtTime = (ts: number | undefined) => {
    if (!ts) return '';
    return new Date(ts).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
  };

  const fmtElapsed = (s: number | null) => {
    if (s === null) return '';
    if (s < 60) return `${s}s`;
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${m}m${sec}s`;
  };

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b flex items-center gap-2">
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6"
          onClick={closeStepDetail}
        >
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className={cn("text-sm font-semibold", getStatusColor(status))}>
          {stageName}
        </div>
        {status !== 'IDLE' && <StatusIcon status={status} />}
        {elapsed !== null && (
          <span className="text-xs text-muted-foreground">{fmtElapsed(elapsed)}</span>
        )}
        <Badge variant="outline" className={cn(
          "text-xs ml-auto",
          status === 'IN_PROGRESS' && "border-amber-400 text-amber-600",
          status === 'COMPLETE' && "border-green-400 text-green-600",
          status === 'ERROR' && "border-red-400 text-red-600",
          status === 'IDLE' && "text-muted-foreground",
        )}>
          {status}
        </Badge>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">

        {/* Progress Timeline */}
        {progressItems.length > 0 && (
          <div>
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium mb-2">
              Progress Timeline
            </div>
            <div className="space-y-1">
              {progressItems.map((item, i) => (
                <div key={i} className="flex items-center gap-2 text-xs">
                  <span className="text-muted-foreground w-16 shrink-0">{fmtTime(item.ts)}</span>
                  <span className={cn(
                    item.status === 'Done' ? 'text-green-600' : 'text-muted-foreground'
                  )}>
                    {item.status}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Streaming / Reasoning Chain */}
        {stream && (
          <div>
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium mb-2">
              LLM Reasoning
            </div>
            <div className="bg-muted/30 rounded-md p-3 text-xs font-mono whitespace-pre-wrap max-h-[200px] overflow-y-auto">
              {stream}
              {status === 'IN_PROGRESS' && <span className="animate-pulse ml-1">▍</span>}
            </div>
          </div>
        )}

        {/* Structured Result */}
        {resultSlice && (
          <div>
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium mb-2">
              Result
            </div>
            <div className="space-y-2">
              {/* Error */}
              {resultSlice.error && (
                <div className="bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-800 rounded-md p-3 text-xs text-red-600 dark:text-red-400">
                  <div className="font-semibold mb-1">Error</div>
                  {resultSlice.error}
                </div>
              )}

              {/* Root cause (Analyze stage) */}
              {resultSlice.root_cause && (
                <div className="bg-blue-50 dark:bg-blue-950/20 border border-blue-200 dark:border-blue-800 rounded-md p-3">
                  <div className="text-xs font-semibold text-blue-600 dark:text-blue-400 mb-1">Root Cause</div>
                  <div className="text-xs text-muted-foreground">{resultSlice.root_cause}</div>
                </div>
              )}

              {/* Affected files (Analyze stage) */}
              {resultSlice.affected_files && Array.isArray(resultSlice.affected_files) && (
                <div className="bg-muted/30 rounded-md p-3">
                  <div className="text-xs font-semibold mb-1">Affected Files</div>
                  <div className="text-xs text-muted-foreground space-y-0.5">
                    {resultSlice.affected_files.map((f: string, i: number) => (
                      <div key={i}>{f}</div>
                    ))}
                  </div>
                </div>
              )}

              {/* Patch blocked (Patch stage) */}
              {resultSlice.patch_status === 'blocked' && (
                <div className="bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 rounded-md p-3">
                  <div className="text-xs font-semibold text-amber-600 dark:text-amber-400 mb-1">Patch Blocked</div>
                  {resultSlice.blocker_reason && (
                    <div className="text-xs text-muted-foreground mb-1">
                      <span className="font-semibold">Reason:</span> {resultSlice.blocker_reason}
                    </div>
                  )}
                  {resultSlice.blocker_next_step && (
                    <div className="text-xs text-muted-foreground">
                      <span className="font-semibold">Next step:</span> {resultSlice.blocker_next_step}
                    </div>
                  )}
                </div>
              )}

              {/* Patch files (Patch stage) */}
              {resultSlice.patch_status !== 'blocked' && resultSlice.patch_files && Array.isArray(resultSlice.patch_files) && (
                <div className="bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-800 rounded-md p-3">
                  <div className="text-xs font-semibold text-green-600 dark:text-green-400 mb-1">Patched Files</div>
                  <div className="text-xs text-muted-foreground space-y-0.5">
                    {resultSlice.patch_files.map((f: string, i: number) => (
                      <div key={i}>{f}</div>
                    ))}
                  </div>
                </div>
              )}

              {/* PR URL (Open PR stage) */}
              {resultSlice.pr_url && (
                <div className="bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-800 rounded-md p-3">
                  <div className="text-xs font-semibold text-green-600 dark:text-green-400 mb-1">Pull Request</div>
                  <a href={resultSlice.pr_url} target="_blank" rel="noopener noreferrer"
                    className="text-xs text-blue-600 dark:text-blue-400 hover:underline break-all">
                    {resultSlice.pr_url}
                  </a>
                </div>
              )}

              {/* Generic fallback: show all keys */}
              {!resultSlice.error && !resultSlice.root_cause && !resultSlice.patch_files && !resultSlice.pr_url && resultSlice.patch_status !== 'blocked' && (
                <div className="bg-muted/30 rounded-md p-3 text-xs">
                  {Object.entries(resultSlice).map(([key, val]) => (
                    <div key={key} className="mb-1">
                      <span className="font-semibold">{key}: </span>
                      <span className="text-muted-foreground">
                        {typeof val === 'string' ? val : JSON.stringify(val)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* No data yet */}
        {!stream && progressItems.length === 0 && !resultSlice && (
          <div className="text-center py-8 text-muted-foreground">
            <div className="text-sm">No data yet</div>
            <div className="text-xs mt-1">This stage hasn't been run or has no output.</div>
          </div>
        )}
      </div>

      {/* Footer — re-run button (placeholder for future interrupt mechanism) */}
      <div className="px-4 py-2 border-t">
        <Button
          variant="outline"
          size="sm"
          className="w-full text-xs gap-1 opacity-50 cursor-not-allowed"
          disabled
        >
          <RotateCcw className="h-3 w-3" /> Re-run from this step (coming soon)
        </Button>
      </div>
    </div>
  );
}

/** Extract the result slice for a given stage name. */
function sliceFor(stageName: string, result: any): any {
  if (!result || typeof result !== 'object') return null;
  switch (stageName) {
    case 'Jira Issue Input':
      return result.jira ?? null;
    case 'Analyze':
      return result.analysis ?? (result.analyze_error ? { error: result.analyze_error } : null);
    case 'Patch':
      return result.patch ?? (result.patch_error ? { error: result.patch_error } : null);
    case 'Open PR':
      return result.open_pr ?? (result.open_pr_error ? { error: result.open_pr_error } : null);
    default:
      return null;
  }
}
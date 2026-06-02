import { Badge } from '@/components/ui/badge';
import { useNodeOutput } from '@/domains/bug-fix/node-output-store';
import { useRunHistory } from '@/domains/bug-fix/run-history-store';
import { useRunPhase } from '@/domains/bug-fix/run-controller';
import { cn } from '@/lib/utils';
import type { NodeStatus } from '@/nodes/utils';
import { getStatusColor, elapsedSeconds } from '@/nodes/utils';
import { CheckCircle2, Clock, Loader2, XCircle, Pause } from 'lucide-react';
import { openStepDetail } from '@/domains/bug-fix/step-detail-context';
import { useNodes } from '@xyflow/react';
import { useMemo } from 'react';

interface OutputTabProps {
  className?: string;
}

function StatusIcon({ status }: { status: NodeStatus }) {
  switch (status) {
    case 'IN_PROGRESS': return <Loader2 className="h-3.5 w-3.5 animate-spin" />;
    case 'COMPLETE': return <CheckCircle2 className="h-3.5 w-3.5" />;
    case 'ERROR': return <XCircle className="h-3.5 w-3.5" />;
    case 'PAUSED': return <Pause className="h-3.5 w-3.5" />;
    default: return <Clock className="h-3.5 w-3.5" />;
  }
}

/**
 * Run Timeline — the observability Layer 2 (Meso).
 *
 * Shows a step-by-step timeline of the current (or most recent) run,
 * with live streaming preview for the active step.
 */
export function OutputTab({ className }: OutputTabProps) {
  const nodeOutput = useNodeOutput();
  const history = useRunHistory();
  const phase = useRunPhase();
  const nodes = useNodes();

  const latestRun = history.runs[0];
  const isRunning = phase === 'running';

  // Helper to look up stage name from node data
  const getStageName = (agentId: string): string => {
    const node = nodes.find(n => n.id === agentId);
    return (node?.data as any)?.name ?? agentId;
  };

  // Derive stage entries — prefer live data from node-output-store;
  // fall back to history stageSnapshots when live data is gone (e.g. after refresh).
  const stageEntries = useMemo(() => {
    const agents = Object.keys(nodeOutput.progressByAgent);

    // Live path: use in-memory progress data
    if (agents.length > 0) {
      return agents.map((agentId) => {
        const progress = nodeOutput.progressByAgent[agentId] ?? [];
        const streaming = nodeOutput.streamingByAgent[agentId] ?? '';
        const lastProgress = progress[progress.length - 1];
        const isDone = lastProgress?.status === 'Done';
        const status: NodeStatus = isDone ? 'COMPLETE' : (progress.some(p => p.status.toLowerCase().includes('error')) ? 'ERROR' : 'IN_PROGRESS');
        const startedAt = progress[0]?.ts;
        const completedAt = isDone ? lastProgress?.ts : undefined;
        const elapsed = startedAt ? elapsedSeconds({ status, startedAt, completedAt }) : null;

        const streamLines = streaming.split('\n').filter(Boolean);
        const lastLine = streamLines[streamLines.length - 1] ?? '';

        return {
          id: agentId,
          name: getStageName(agentId),
          status,
          startedAt,
          completedAt,
          elapsed,
          lastProgressStatus: lastProgress?.status ?? '',
          streamingLastLine: lastLine,
          isRunning: !isDone,
        };
      });
    }

    // History fallback: reconstruct from stageSnapshots
    if (latestRun?.stageSnapshots) {
      return Object.entries(latestRun.stageSnapshots).map(([agentId, snap]) => ({
        id: agentId,
        name: getStageName(agentId),
        status: snap.status,
        startedAt: snap.startedAt,
        completedAt: snap.completedAt,
        elapsed: snap.startedAt ? elapsedSeconds({ status: snap.status, startedAt: snap.startedAt, completedAt: snap.completedAt }) : null,
        lastProgressStatus: snap.outputSummary ?? '',
        streamingLastLine: '',
        isRunning: false,
      }));
    }

    return [];
  }, [nodeOutput, latestRun]);

  // Extract per-stage output summary from the result object
  const getStageOutput = (stageName: string): string | null => {
    const result = nodeOutput.result;
    if (!result || typeof result !== 'object') return null;

    switch (stageName) {
      case 'Jira Issue Input': {
        const jira = result.jira;
        if (jira?.summary) return jira.summary;
        return null;
      }
      case 'Analyze': {
        if (result.analyze_error) return `Error: ${result.analyze_error}`;
        const analysis = result.analysis;
        if (analysis?.root_cause_hypothesis) return analysis.root_cause_hypothesis;
        if (analysis?.affected_areas?.length) return `Areas: ${analysis.affected_areas.join(', ')}`;
        return null;
      }
      case 'Patch': {
        if (result.patch_error) return `Error: ${result.patch_error}`;
        const patch = result.patch;
        if (patch?.status === 'blocked') return `Blocked: ${patch.blocker_reason ?? 'unknown'}`;
        if (patch?.files_changed?.length) return `Changed: ${patch.files_changed.join(', ')}`;
        return null;
      }
      case 'Open PR': {
        if (result.open_pr_error) return `Error: ${result.open_pr_error}`;
        const pr = result.open_pr;
        if (pr?.pr?.url) return pr.pr.url;
        if (pr?.branch) return `Branch: ${pr.branch}`;
        return null;
      }
      default:
        return null;
    }
  };

  // Format elapsed time
  const fmtElapsed = (s: number | null) => {
    if (s === null) return '';
    if (s < 60) return `${s}s`;
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${m}m${sec}s`;
  };

  // Format timestamp
  const fmtTime = (ts: number | undefined) => {
    if (!ts) return '';
    return new Date(ts).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
  };

  if (!latestRun && phase === 'idle') {
    return (
      <div className={cn('h-full overflow-y-auto', className)}>
        <div className="text-center py-8 text-muted-foreground">
          <div className="text-sm font-medium mb-1">No run yet</div>
          <div className="text-xs">Run a workflow from the canvas to see the timeline here.</div>
        </div>
      </div>
    );
  }

  return (
    <div className={cn('h-full overflow-y-auto font-mono text-sm', className)}>
      {/* Run header */}
      <div className="flex items-center gap-3 px-4 py-2 border-b bg-muted/30 sticky top-0 z-10">
        <Badge variant="outline" className={cn(
          "text-xs font-medium",
          phase === 'running' && "border-amber-400 text-amber-600",
          phase === 'complete' && "border-green-400 text-green-600",
          phase === 'error' && "border-red-400 text-red-600",
          phase === 'idle' && "border-muted text-muted-foreground",
        )}>
          {phase.toUpperCase()}
        </Badge>
        {latestRun?.issueKey && (
          <span className="text-xs text-muted-foreground">{latestRun.issueKey}</span>
        )}
        {latestRun?.startedAt && (
          <span className="text-xs text-muted-foreground">
            Started {fmtTime(latestRun.startedAt)}
          </span>
        )}
        {isRunning && (
          <Loader2 className="h-3 w-3 animate-spin text-amber-500" />
        )}
      </div>

      {/* Timeline entries */}
      <div className="px-4 py-2 space-y-1">
        {stageEntries.length === 0 && isRunning && (
          <div className="text-xs text-muted-foreground py-4 text-center">
            Waiting for first stage to report…
          </div>
        )}
        {stageEntries.map((entry) => {
          const outputSummary = getStageOutput(entry.name);
          return (
            <div
              key={entry.id}
              className={cn(
                "px-3 py-2 rounded-md transition-colors cursor-pointer",
                entry.isRunning && "bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800",
                entry.status === 'COMPLETE' && "bg-green-50/50 dark:bg-green-950/10",
                entry.status === 'ERROR' && "bg-red-50/50 dark:bg-red-950/10",
              )}
              onClick={() => openStepDetail(entry.id, entry.name)}
            >
              {/* Top row: icon + time + name + elapsed */}
              <div className="flex items-center gap-2">
                {/* Status icon */}
                <StatusIcon status={entry.status} />

                {/* Time */}
                <span className="text-[11px] text-muted-foreground w-16 shrink-0">
                  {fmtTime(entry.startedAt)}
                </span>

                {/* Stage name */}
                <span className={cn(
                  "text-xs font-medium flex-1 truncate",
                  getStatusColor(entry.status)
                )}>
                  {entry.name}
                </span>

                {/* Progress status */}
                {entry.lastProgressStatus && entry.isRunning && (
                  <span className="text-[11px] text-muted-foreground truncate max-w-[120px]">
                    {entry.lastProgressStatus}
                  </span>
                )}

                {/* Elapsed */}
                <span className={cn(
                  "text-[11px] font-medium w-12 shrink-0 text-right",
                  getStatusColor(entry.status)
                )}>
                  {fmtElapsed(entry.elapsed)}
                </span>
              </div>

              {/* Output summary row */}
              {(outputSummary || entry.streamingLastLine) && (
                <div className="mt-1 ml-7 text-[11px] text-muted-foreground truncate">
                  {entry.isRunning && entry.streamingLastLine ? (
                    <span className="italic">{entry.streamingLastLine}</span>
                  ) : outputSummary ? (
                    <span>{outputSummary}</span>
                  ) : null}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Live streaming preview */}
      {isRunning && Object.keys(nodeOutput.streamingByAgent).length > 0 && (
        <div className="border-t mt-2">
          <div className="px-4 py-1 text-[10px] uppercase tracking-wide text-muted-foreground font-medium">
            Live Output
          </div>
          <div className="px-4 py-2 text-xs text-muted-foreground max-h-[120px] overflow-y-auto whitespace-pre-wrap">
            {(() => {
              // Concatenate last 5 lines from each active agent
              const lines: string[] = [];
              for (const [agentId, stream] of Object.entries(nodeOutput.streamingByAgent)) {
                if (!stream) continue;
                const streamLines = stream.split('\n').filter(Boolean);
                const tail = streamLines.slice(-5);
                lines.push(...tail.map(l => `[${agentId}] ${l}`));
              }
              return lines.join('\n') || 'Processing…';
            })()}
            <span className="animate-pulse ml-1">▍</span>
          </div>
        </div>
      )}

      {/* Result summary (when complete) */}
      {phase === 'complete' && nodeOutput.result && (
        <div className="border-t mt-2">
          <div className="px-4 py-1 text-[10px] uppercase tracking-wide text-muted-foreground font-medium">
            Result
          </div>
          <div className="px-4 py-2 text-xs text-green-600 dark:text-green-400">
            Run completed successfully.
            {latestRun?.completedAt && ` Total: ${fmtElapsed(Math.round((latestRun.completedAt - latestRun.startedAt) / 1000))}`}
          </div>
        </div>
      )}

      {phase === 'error' && (
        <div className="border-t mt-2">
          <div className="px-4 py-1 text-[10px] uppercase tracking-wide text-muted-foreground font-medium">
            Error
          </div>
          <div className="px-4 py-2 text-xs text-red-600 dark:text-red-400">
            Run failed. Check stage details for more info.
          </div>
        </div>
      )}
    </div>
  );
}
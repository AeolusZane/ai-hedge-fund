import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DecisionTreePanel } from '@/domains/bug-fix/decision-tree-panel';
import { NodeChat } from '@/domains/bug-fix/node-chat';
import { useNodeOutput } from '@/domains/bug-fix/node-output-store';
import { useStepDetailTarget, closeStepDetail } from '@/domains/bug-fix/step-detail-context';
import { WorkspaceBrowser } from '@/domains/bug-fix/workspace-browser';
import { useFlowContext } from '@/contexts/flow-context';
import { cn } from '@/lib/utils';
import type { NodeStatus } from '@/nodes/utils';
import { getStatusColor, elapsedSeconds } from '@/nodes/utils';
import { useReactFlow } from '@xyflow/react';
import { CheckCircle2, Loader2, XCircle, Pause, ArrowLeft, FolderOpen, Play } from 'lucide-react';
import { useMemo, useState } from 'react';

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
  const reactFlow = useReactFlow();
  const { currentFlowId } = useFlowContext();
  const [workspaceOpen, setWorkspaceOpen] = useState(false);

  if (!target) return null;

  const { agentId, stageName } = target;
  const stream = nodeOutput.streamingByAgent[agentId] ?? '';
  const progressItems = nodeOutput.progressByAgent[agentId] ?? [];
  const decisionSteps = nodeOutput.decisionStepsByAgent[agentId] ?? [];
  const result = nodeOutput.result;
  const runId = nodeOutput.runId;

  // Get the actual node data for chat context
  const node = reactFlow.getNode(agentId);
  const nodeData = node?.data as Record<string, unknown> | undefined;
  const nodeConfig = useMemo(() => {
    if (!nodeData) return {};
    const config: Record<string, unknown> = {};
    for (const key of ['modelName', 'modelProvider', 'repoUrl', 'targetBranch', 'pushRemote', 'prTargetRemote']) {
      if (nodeData[key] !== undefined && nodeData[key] !== '') {
        config[key] = nodeData[key];
      }
    }
    return config;
  }, [nodeData]);

  // Update node data when Agent suggests config changes
  const handleConfigUpdate = (key: string, value: string) => {
    if (!node) return;
    reactFlow.setNodes(nodes =>
      nodes.map(n =>
        n.id === agentId
          ? { ...n, data: { ...n.data, [key]: value } }
          : n
      )
    );
  };

  // Retry: re-run from this node using saved state snapshot
  const [rerunContext, setRerunContext] = useState('');
  const [isRerunning, setIsRerunning] = useState(false);
  
  const handleRetry = async () => {
    if (!runId || !currentFlowId) {
      console.error('Missing runId or flowId for rerun');
      return;
    }
    
    setIsRerunning(true);
    try {
      const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
      const response = await fetch(`${API_BASE_URL}/workflows/bug_fix/rerun-from-node`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          flow_id: currentFlowId,
          run_id: runId,
          from_node_id: agentId,
          extra_context: rerunContext || undefined,
        }),
      });
      
      if (!response.ok) {
        const error = await response.json();
        console.error('Rerun failed:', error);
        alert(`Rerun failed: ${error.detail || 'Unknown error'}`);
      } else {
        console.log('Rerun started from node:', agentId);
        // Clear the context input after successful rerun
        setRerunContext('');
      }
    } catch (error) {
      console.error('Rerun request failed:', error);
      alert('Rerun request failed. Check console for details.');
    } finally {
      setIsRerunning(false);
    }
  };

  // Extract result slice for this stage (needed for status derivation)
  const resultSlice = useMemo(() => sliceFor(stageName, result), [stageName, result]);

  // Derive status
  const lastProgress = progressItems[progressItems.length - 1];
  const isDone = lastProgress?.status === 'Done';
  const isError = lastProgress?.status === 'Error' || !!resultSlice?.error;
  const status: NodeStatus = isDone && !resultSlice?.error
    ? 'COMPLETE'
    : isError
      ? 'ERROR'
      : (progressItems.length > 0 ? 'IN_PROGRESS' : 'IDLE') as NodeStatus;

  // Derive elapsed
  const startedAt = progressItems[0]?.ts;
  const completedAt = (isDone || isError) ? lastProgress?.ts : undefined;
  const elapsed = startedAt ? elapsedSeconds({ status, startedAt, completedAt }) : null;

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
        {runId && status !== 'IDLE' && (
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            onClick={() => setWorkspaceOpen(true)}
            title="Browse workspace files"
          >
            <FolderOpen className="h-4 w-4" />
          </Button>
        )}
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

        {/* Decision Tree — structured reasoning trace */}
        {decisionSteps.length > 0 && (
          <div>
            <DecisionTreePanel
              steps={decisionSteps}
              running={status === 'IN_PROGRESS'}
            />
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

              {/* ── Analyze stage fields ── */}

              {/* Root cause hypothesis */}
              {resultSlice.root_cause_hypothesis && (
                <div className="bg-blue-50 dark:bg-blue-950/20 border border-blue-200 dark:border-blue-800 rounded-md p-3">
                  <div className="text-xs font-semibold text-blue-600 dark:text-blue-400 mb-1">Root Cause Hypothesis</div>
                  <div className="text-xs text-muted-foreground">{resultSlice.root_cause_hypothesis}</div>
                </div>
              )}

              {/* Affected areas */}
              {resultSlice.affected_areas && Array.isArray(resultSlice.affected_areas) && resultSlice.affected_areas.length > 0 && (
                <div className="bg-muted/30 rounded-md p-3">
                  <div className="text-xs font-semibold mb-1">Affected Areas</div>
                  <div className="text-xs text-muted-foreground space-y-0.5">
                    {resultSlice.affected_areas.map((f: string, i: number) => (
                      <div key={i} className="flex items-center gap-1">
                        <span className="text-[10px] text-muted-foreground/60">•</span> {f}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Suggested approach */}
              {resultSlice.suggested_approach && (
                <div className="bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-800 rounded-md p-3">
                  <div className="text-xs font-semibold text-green-600 dark:text-green-400 mb-1">Suggested Approach</div>
                  <div className="text-xs text-muted-foreground whitespace-pre-wrap">{resultSlice.suggested_approach}</div>
                </div>
              )}

              {/* Open questions */}
              {resultSlice.open_questions && Array.isArray(resultSlice.open_questions) && resultSlice.open_questions.length > 0 && (
                <div className="bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 rounded-md p-3">
                  <div className="text-xs font-semibold text-amber-600 dark:text-amber-400 mb-1">Open Questions</div>
                  <div className="text-xs text-muted-foreground space-y-0.5">
                    {resultSlice.open_questions.map((q: string, i: number) => (
                      <div key={i} className="flex items-start gap-1">
                        <span className="text-[10px] text-muted-foreground/60 mt-0.5">?</span> {q}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Raw analysis (when JSON parse failed) */}
              {resultSlice.raw && !resultSlice.root_cause_hypothesis && (
                <div className="bg-muted/30 rounded-md p-3">
                  <div className="text-xs font-semibold mb-1">Raw Analysis</div>
                  <pre className="whitespace-pre-wrap text-xs text-muted-foreground">{resultSlice.raw}</pre>
                </div>
              )}

              {/* ── Patch stage fields ── */}

              {/* Patch blocked */}
              {resultSlice.status === 'blocked' && (
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

              {/* Patched files */}
              {resultSlice.files_changed && Array.isArray(resultSlice.files_changed) && resultSlice.files_changed.length > 0 && (
                <div className="bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-800 rounded-md p-3">
                  <div className="text-xs font-semibold text-green-600 dark:text-green-400 mb-1">
                    Files Changed ({resultSlice.files_changed.length})
                  </div>
                  <div className="text-xs text-muted-foreground space-y-0.5 font-mono">
                    {resultSlice.files_changed.map((f: string, i: number) => (
                      <div key={i}>{f}</div>
                    ))}
                  </div>
                </div>
              )}

              {/* Diff */}
              {resultSlice.diff && (
                <div className="bg-muted/30 rounded-md p-3">
                  <div className="text-xs font-semibold mb-1">Diff</div>
                  <pre className="whitespace-pre-wrap text-[11px] text-muted-foreground font-mono max-h-[300px] overflow-y-auto leading-relaxed">
                    {resultSlice.diff}
                  </pre>
                </div>
              )}

              {/* ── Open PR stage fields ── */}

              {/* Branch */}
              {resultSlice.branch && (
                <div className="bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-800 rounded-md p-3">
                  <div className="text-xs font-semibold text-green-600 dark:text-green-400 mb-1">Branch</div>
                  <div className="text-xs text-muted-foreground font-mono">{resultSlice.branch}</div>
                </div>
              )}

              {/* PR payload */}
              {resultSlice.pr && (
                <div className="bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-800 rounded-md p-3">
                  <div className="text-xs font-semibold text-green-600 dark:text-green-400 mb-1">Pull Request</div>
                  {resultSlice.pr.url && (
                    <a href={resultSlice.pr.url} target="_blank" rel="noopener noreferrer"
                      className="text-xs text-blue-600 dark:text-blue-400 hover:underline break-all">
                      {resultSlice.pr.url}
                    </a>
                  )}
                  {resultSlice.pr.id && (
                    <div className="text-xs text-muted-foreground mt-1">PR #{resultSlice.pr.id}</div>
                  )}
                  {!resultSlice.pr.url && (
                    <pre className="whitespace-pre-wrap text-xs text-muted-foreground">
                      {JSON.stringify(resultSlice.pr, null, 2)}
                    </pre>
                  )}
                </div>
              )}

              {/* ── Jira stage fields ── */}

              {resultSlice.summary && (
                <div className="bg-muted/30 rounded-md p-3">
                  <div className="text-xs font-semibold mb-1">Summary</div>
                  <div className="text-xs text-muted-foreground">{resultSlice.summary}</div>
                </div>
              )}

              {resultSlice.description && (
                <div className="bg-muted/30 rounded-md p-3">
                  <div className="text-xs font-semibold mb-1">Description</div>
                  <div className="text-xs text-muted-foreground whitespace-pre-wrap max-h-[200px] overflow-y-auto">
                    {typeof resultSlice.description === 'string'
                      ? resultSlice.description.slice(0, 2000)
                      : JSON.stringify(resultSlice.description, null, 2)}
                  </div>
                </div>
              )}

              {resultSlice.status && typeof resultSlice.status === 'string' && (
                <div className="flex gap-3 text-xs">
                  <span><span className="font-semibold">Status:</span> <span className="text-muted-foreground">{resultSlice.status}</span></span>
                  {resultSlice.priority && <span><span className="font-semibold">Priority:</span> <span className="text-muted-foreground">{resultSlice.priority}</span></span>}
                  {resultSlice.assignee && <span><span className="font-semibold">Assignee:</span> <span className="text-muted-foreground">{resultSlice.assignee}</span></span>}
                </div>
              )}

              {/* ── Generic fallback: show unrecognized keys ── */}
              {(() => {
                const knownKeys = new Set([
                  'error', 'root_cause_hypothesis', 'affected_areas', 'suggested_approach',
                  'open_questions', 'raw', 'status', 'files_changed', 'diff',
                  'blocker_reason', 'blocker_next_step', 'branch', 'pr',
                  'summary', 'description', 'priority', 'assignee', 'key',
                  'comment', 'comments', 'components', 'labels', 'issuetype',
                  'created', 'updated', 'reporter', 'creator', 'project',
                  'fixVersions', 'versions', 'resolution',
                ]);
                const unknownEntries = Object.entries(resultSlice).filter(([k]) => !knownKeys.has(k));
                if (unknownEntries.length === 0) return null;
                return (
                  <div className="bg-muted/30 rounded-md p-3 text-xs">
                    <div className="font-semibold mb-1 text-muted-foreground">Other Fields</div>
                    {unknownEntries.map(([key, val]) => (
                      <div key={key} className="mb-1">
                        <span className="font-semibold">{key}: </span>
                        <span className="text-muted-foreground">
                          {typeof val === 'string' ? val : JSON.stringify(val)}
                        </span>
                      </div>
                    ))}
                  </div>
                );
              })()}
            </div>
          </div>
        )}

        {/* Anomalies */}
        {result?.anomalies && result.anomalies.anomaly_count > 0 && (
          <div>
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium mb-2">
              Anomalies Detected ({result.anomalies.anomaly_count})
            </div>
            <div className="space-y-2">
              {result.anomalies.anomalies.map((anomaly: any, i: number) => (
                <div
                  key={i}
                  className={cn(
                    'rounded-md p-3 text-xs border',
                    anomaly.severity === 'critical'
                      ? 'bg-red-50 dark:bg-red-950/20 border-red-200 dark:border-red-800'
                      : 'bg-amber-50 dark:bg-amber-950/20 border-amber-200 dark:border-amber-800'
                  )}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <Badge
                      variant="outline"
                      className={cn(
                        'text-[10px]',
                        anomaly.severity === 'critical'
                          ? 'border-red-400 text-red-600'
                          : 'border-amber-400 text-amber-600'
                      )}
                    >
                      {anomaly.severity}
                    </Badge>
                    <span className="font-semibold text-[10px] uppercase">{anomaly.type}</span>
                  </div>
                  <div className={cn(
                    'mb-1',
                    anomaly.severity === 'critical' ? 'text-red-700 dark:text-red-300' : 'text-amber-700 dark:text-amber-300'
                  )}>
                    {anomaly.message}
                  </div>
                  {anomaly.details && Object.keys(anomaly.details).length > 0 && (
                    <details className="mt-1">
                      <summary className="cursor-pointer text-[10px] text-muted-foreground">Details</summary>
                      <pre className="mt-1 text-[10px] font-mono bg-background/50 rounded p-2 overflow-auto max-h-[100px]">
                        {JSON.stringify(anomaly.details, null, 2)}
                      </pre>
                    </details>
                  )}
                </div>
              ))}
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

      {/* Agent Chat — always available for any node */}
      <NodeChat
        nodeId={agentId}
        nodeName={stageName}
        nodeType={stageName}
        nodeConfig={nodeConfig}
        errorInfo={resultSlice?.error}
        streamingOutput={stream}
        progressTimeline={progressItems.map(p => `${fmtTime(p.ts)} ${p.status}`).join('\n')}
        nodeStatus={status}
        repoUrl={nodeConfig.repoUrl as string | undefined}
        workspacePath={runId ? `/workspace/${runId}` : undefined}
        runId={runId}
        onConfigUpdate={handleConfigUpdate}
        onRetry={handleRetry}
      />

      {/* Footer — re-run from this step */}
      {runId && status !== 'IDLE' && (
        <div className="px-4 py-2 border-t space-y-2">
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium">
            Re-run from this step
          </div>
          <textarea
            value={rerunContext}
            onChange={(e) => setRerunContext(e.target.value)}
            placeholder="Optional: add context or instructions (e.g., 'also check utils.ts')"
            className="w-full min-h-[50px] text-xs resize-none rounded-md border border-input bg-background px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-ring"
          />
          <Button
            variant="outline"
            size="sm"
            className="w-full text-xs gap-1"
            disabled={isRerunning}
            onClick={handleRetry}
          >
            {isRerunning ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <Play className="h-3 w-3" />
            )}
            {isRerunning ? 'Starting re-run...' : 'Re-run from here'}
          </Button>
        </div>
      )}

      {/* Workspace Browser Modal */}
      {runId && (
        <WorkspaceBrowser
          domain="bug_fix"
          runId={runId}
          isOpen={workspaceOpen}
          onClose={() => setWorkspaceOpen(false)}
        />
      )}
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
      // Prioritize error over empty/partial analysis
      if (result.analyze_error) return { error: result.analyze_error };
      if (result.analysis && Object.keys(result.analysis).length > 0) return result.analysis;
      return null;
    case 'Patch':
      if (result.patch_error) return { error: result.patch_error };
      if (result.patch && Object.keys(result.patch).length > 0) return result.patch;
      return null;
    case 'Open PR':
      if (result.open_pr_error) return { error: result.open_pr_error };
      if (result.open_pr && Object.keys(result.open_pr).length > 0) return result.open_pr;
      return null;
    default:
      return null;
  }
}
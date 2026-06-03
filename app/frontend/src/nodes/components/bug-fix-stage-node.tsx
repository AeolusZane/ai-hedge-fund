import { Button } from '@/components/ui/button';
import { CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { ModelSelector } from '@/components/ui/llm-selector';
import { useFlowContext } from '@/contexts/flow-context';
import { useNodeContext } from '@/contexts/node-context';
import { getModels, type LanguageModel } from '@/data/models';

import { NodeOutputDialog } from '@/domains/bug-fix/node-output-dialog';
import { useNodeOutput } from '@/domains/bug-fix/node-output-store';
import { openStepDetail } from '@/domains/bug-fix/step-detail-context';
import { useNodeState } from '@/hooks/use-node-state';
import { cn } from '@/lib/utils';
import type { NodeRunInfo, NodeStatus } from '@/nodes/utils';
import { type NodeProps } from '@xyflow/react';
import { Eye, Wrench } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import type { BugFixStageNode } from '../types';
import { getStatusColor } from '../utils';
import { NodeShell } from './node-shell';

const STAGES_THAT_USE_AN_LLM = new Set(['Analyze']);
const STAGES_THAT_NEED_REPO_URL = new Set(['Patch']);
const STAGES_THAT_NEED_TARGET_BRANCH = new Set(['Patch']);
const STAGES_THAT_NEED_PR_CONFIG = new Set(['Open PR']);

/**
 * Bug-fix stage node — the canvas counterpart to one bug_fix executor stage.
 *
 * Per-stage configuration lives directly on the node (no separate config
 * input nodes). What renders depends on `data.name`:
 *   Analyze  → ModelSelector
 *   Patch    → Repo path text input
 *   Open PR  → Repo path + Bitbucket project / repo / target branch inputs
 * All values are persisted via useNodeState and folded into node.data by
 * the run dialog when snapshotting the graph for submission.
 */
export function BugFixStageNode({
  data,
  selected,
  id,
  isConnectable,
}: NodeProps<BugFixStageNode>) {
  const { currentFlowId } = useFlowContext();
  const { getAgentNodeDataForFlow } = useNodeContext();
  const agentNodeData = getAgentNodeDataForFlow(currentFlowId?.toString() || null);
  const liveStatus = agentNodeData[id]?.status as NodeStatus | undefined;

  // Subscribe to the shared node-output store for live observability.
  // This store is persisted to localStorage, so it survives page refreshes.
  const nodeOutput = useNodeOutput();
  const stream = nodeOutput.streamingByAgent[id] ?? '';
  const progressItems = nodeOutput.progressByAgent[id] ?? [];

  // Derive status: prefer live SSE status; fall back to persisted progress
  // data so canvas nodes recover their visual state after a page refresh.
  const status: NodeStatus = liveStatus ?? deriveStatusFromProgress(progressItems, nodeOutput.phase) ?? (data.status as NodeStatus) ?? 'IDLE';
  const isInProgress = status === 'IN_PROGRESS';

  // Derive a one-line output summary from streaming or progress
  const outputSummary = useMemo(() => {
    if (status === 'ERROR') return 'Failed — check details';
    if (status === 'COMPLETE') {
      // Try to extract a meaningful summary from the result
      const result = nodeOutput.result;
      const slice = sliceFor(data.name, result);
      if (slice) {
        if (slice.error) return `Error: ${slice.error}`;
        if (slice.root_cause) return slice.root_cause;
        if (slice.patch_files) return `${slice.patch_files.length} files patched`;
        if (slice.pr_url) return `PR opened`;
        // Generic: truncate first key-value
        const firstKey = Object.keys(slice)[0];
        if (firstKey) {
          const val = slice[firstKey];
          const str = typeof val === 'string' ? val : JSON.stringify(val);
          return str.length > 60 ? str.slice(0, 57) + '…' : str;
        }
      }
      return 'Done';
    }
    // IN_PROGRESS: show last line of streaming (tail effect)
    if (isInProgress && stream) {
      const lines = stream.split('\n').filter(Boolean);
      const last = lines[lines.length - 1] ?? '';
      return last.length > 60 ? last.slice(0, 57) + '…' : last;
    }
    // IN_PROGRESS without streaming: show last progress status
    if (isInProgress && progressItems.length > 0) {
      const last = progressItems[progressItems.length - 1];
      return last.status.length > 60 ? last.status.slice(0, 57) + '…' : last.status;
    }
    return undefined;
  }, [status, stream, progressItems, nodeOutput.result, data.name, isInProgress]);

  // Derive progress percentage from progress timeline
  const progressPercent = useMemo(() => {
    if (status === 'COMPLETE') return 100;
    if (status === 'ERROR') return 100;
    if (status === 'IDLE') return 0;
    // Rough heuristic: each "Done" progress item = 33% for a 3-step stage
    const doneCount = progressItems.filter(p => p.status === 'Done').length;
    return Math.min(doneCount * 33, 99);
  }, [status, progressItems]);

  // Build NodeRunInfo from available data
  const runInfo: NodeRunInfo | undefined = useMemo(() => {
    if (status === 'IDLE') return undefined;
    const startedAt = progressItems[0]?.ts;
    let completedAt: number | undefined;
    if (status === 'COMPLETE' || status === 'ERROR') {
      // Use last progress item timestamp, or fall back to now if no progress items
      completedAt = progressItems[progressItems.length - 1]?.ts ?? Date.now();
    }
    return {
      status,
      progress: progressPercent,
      startedAt,
      completedAt,
      outputSummary,
    };
  }, [status, progressPercent, progressItems, outputSummary]);

  const needsModel = STAGES_THAT_USE_AN_LLM.has(data.name);
  const needsRepoUrl = STAGES_THAT_NEED_REPO_URL.has(data.name);
  const needsTargetBranch = STAGES_THAT_NEED_TARGET_BRANCH.has(data.name);
  const needsPrConfig = STAGES_THAT_NEED_PR_CONFIG.has(data.name);

  // Model selector state (Analyze)
  const [models, setModels] = useState<LanguageModel[]>([]);
  const [modelName, setModelName] = useNodeState<string>(id, 'modelName', '');
  const [, setModelProvider] = useNodeState<string>(id, 'modelProvider', '');

  // Repo URL (Patch only)
  const [repoUrl, setRepoUrl] = useNodeState<string>(id, 'repoUrl', '');

  // Target branch (Patch only)
  const [targetBranch, setTargetBranch] = useNodeState<string>(id, 'targetBranch', 'main');

  // PR config (Open PR only) — optional overrides, auto-detect if empty
  const [pushRemote, setPushRemote] = useNodeState<string>(id, 'pushRemote', '');
  const [prTargetRemote, setPrTargetRemote] = useNodeState<string>(id, 'prTargetRemote', '');

  // View Output dialog
  const [outputOpen, setOutputOpen] = useState(false);

  useEffect(() => {
    if (!needsModel || models.length > 0) return;
    let cancelled = false;
    getModels()
      .then((list) => {
        if (cancelled) return;
        setModels(list);
      })
      .catch(() => {
        if (!cancelled) setModels([]);
      });
    return () => {
      cancelled = true;
    };
  }, [needsModel, models.length]);

  const onModelChange = (m: LanguageModel | null) => {
    setModelName(m?.model_name ?? '');
    setModelProvider(m?.provider ?? '');
  };

  // Helper to render a labelled text field that doesn't fight React Flow
  // for pointer / key events.
  const field = (
    label: string,
    value: string,
    onChange: (v: string) => void,
    placeholder: string
  ) => (
    <div className="space-y-1">
      <label className="text-[10px] uppercase tracking-wide">{label}</label>
      <Input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="h-7 text-xs font-mono"
        onPointerDown={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.stopPropagation()}
      />
    </div>
  );

  return (
    <NodeShell
      id={id}
      selected={selected}
      isConnectable={isConnectable}
      icon={<Wrench className="h-5 w-5" />}
      iconColor={getStatusColor(status)}
      name={data.name}
      description={data.description}
      status={status}
      runInfo={runInfo}
    >
      <CardContent
        className={cn(
          'pt-2 pb-3 text-xs text-muted-foreground space-y-2',
          isInProgress && 'gradient-animation'
        )}
      >
        {/* Live streaming preview — shows last line while running */}
        {isInProgress && stream && (
          <div className="font-mono text-[11px] text-muted-foreground truncate border rounded-md px-2 py-1 bg-muted/30">
            {(() => {
              const lines = stream.split('\n').filter(Boolean);
              return lines[lines.length - 1] ?? 'Processing…';
            })()}
            <span className="animate-pulse ml-1">▍</span>
          </div>
        )}

        {needsModel && (
          <div
            className="space-y-1"
            onPointerDown={(e) => e.stopPropagation()}
            onKeyDown={(e) => e.stopPropagation()}
          >
            <label className="text-[10px] uppercase tracking-wide">Model</label>
            <ModelSelector
              models={models}
              value={modelName}
              onChange={onModelChange}
              placeholder={models.length === 0 ? 'Loading…' : 'Select an LLM'}
            />
          </div>
        )}
        {needsRepoUrl && field('Repo URL', repoUrl, setRepoUrl, 'https://github.com/org/repo.git')}
        {needsTargetBranch && field('Target branch', targetBranch, setTargetBranch, 'main')}
        {needsPrConfig && (
          <>
            {field('Push remote (optional)', pushRemote, setPushRemote, 'auto-detect fork')}
            {field('PR target remote (optional)', prTargetRemote, setPrTargetRemote, 'auto-detect main')}
          </>
        )}

        {/* View Output button — opens the step detail panel */}
        <Button
          variant="outline"
          size="sm"
          className="w-full h-6 gap-1 text-[10px]"
          onPointerDown={(e) => e.stopPropagation()}
          onClick={(e) => {
            e.stopPropagation();
            openStepDetail(id, data.name);
          }}
        >
          <Eye className="h-3 w-3" /> View output
        </Button>
        <NodeOutputDialog
          open={outputOpen}
          onOpenChange={setOutputOpen}
          agentId={id}
          stageName={data.name}
        />
      </CardContent>
    </NodeShell>
  );
}

/** Extract the result slice for a given stage name — mirrors NodeOutputDialog. */
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

/**
 * Derive a NodeStatus from persisted progress data.
 *
 * When the page is refreshed, the live SSE-driven `agentNodeData` is lost
 * (it's pure React state). But `node-output-store` persists progress items
 * to localStorage. This function reconstructs the node's visual status
 * from that persisted timeline so the canvas doesn't reset to all-IDLE.
 */
function deriveStatusFromProgress(
  progressItems: { status: string; ts: number }[],
  phase: string,
): NodeStatus | null {
  if (progressItems.length === 0) return null;
  const last = progressItems[progressItems.length - 1];
  if (last.status === 'Done') return 'COMPLETE';
  if (last.status === 'Error') return 'ERROR';
  // Has progress but not done — if the run is still active, show IN_PROGRESS
  if (phase === 'running') return 'IN_PROGRESS';
  // Run finished but this stage didn't record "Done" — likely errored or skipped
  if (phase === 'complete' || phase === 'error') return 'COMPLETE';
  return null;
}
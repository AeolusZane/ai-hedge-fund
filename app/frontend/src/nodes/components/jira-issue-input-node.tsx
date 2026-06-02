import { Button } from '@/components/ui/button';
import { CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { useFlowContext } from '@/contexts/flow-context';
import { useNodeContext } from '@/contexts/node-context';
import { useNodeOutput } from '@/domains/bug-fix/node-output-store';
import {
  requestRun,
  requestStop,
  useRunPhase,
} from '@/domains/bug-fix/run-controller';
import { useNodeState } from '@/hooks/use-node-state';
import { cn } from '@/lib/utils';
import type { NodeStatus } from '@/nodes/utils';
import { type NodeProps } from '@xyflow/react';
import { Inbox, Play, Square } from 'lucide-react';
import type { JiraIssueInputNode } from '../types';
import { getStatusColor } from '../utils';
import { NodeShell } from './node-shell';

/**
 * Canvas-resident input + fetch node for the bug_fix domain.
 *
 * Owns the Jira issue key (via useNodeState), triggers the run, AND
 * acts as the first executable step: when the executor walks the
 * graph this node performs the MCP fetch and populates the shared
 * state for downstream stages. A fetch failure terminates the run.
 */
export function JiraIssueInputNode({
  data,
  selected,
  id,
  isConnectable,
}: NodeProps<JiraIssueInputNode>) {
  const [issueKey, setIssueKey] = useNodeState<string>(id, 'issueKey', '');
  const phase = useRunPhase();
  const running = phase === 'running';
  // Run is shown when idle, Stop when running. Disabling Run on the
  // `running` flag is redundant because the button is hidden in that
  // branch anyway. Gating only on issueKey lets a stale or stuck
  // phase still recover with a single click.
  const canRun = issueKey.trim().length > 0;

  const { currentFlowId } = useFlowContext();
  const { getAgentNodeDataForFlow } = useNodeContext();
  const agentNodeData = getAgentNodeDataForFlow(currentFlowId?.toString() || null);
  const liveStatus = agentNodeData[id]?.status as NodeStatus | undefined;

  // Recover status from persisted progress data after page refresh
  const nodeOutput = useNodeOutput();
  const progressItems = nodeOutput.progressByAgent[id] ?? [];
  const persistedStatus = deriveStatusFromProgress(progressItems, nodeOutput.phase);

  const status: NodeStatus = liveStatus ?? persistedStatus ?? 'IDLE';
  const isInProgress = status === 'IN_PROGRESS';

  return (
    <NodeShell
      id={id}
      selected={selected}
      isConnectable={isConnectable}
      icon={<Inbox className="h-5 w-5" />}
      iconColor={status === 'IDLE' ? 'text-blue-500' : getStatusColor(status)}
      name={data.name}
      description={data.description}
      status={status}
      hasLeftHandle={false}
    >
      <CardContent
        className={cn(
          'pt-2 pb-3 space-y-2',
          isInProgress && 'gradient-animation'
        )}
      >
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>Input + Fetch</span>
          <span className={cn('font-mono', getStatusColor(status))}>{status}</span>
        </div>
        <label className="text-[10px] uppercase tracking-wide text-muted-foreground">
          Issue key
        </label>
        <Input
          value={issueKey}
          onChange={(e) => setIssueKey(e.target.value)}
          placeholder="e.g. BI-158957"
          className="h-7 text-xs font-mono"
          onPointerDown={(e) => e.stopPropagation()}
          onKeyDown={(e) => {
            e.stopPropagation();
            if (e.key === 'Enter' && canRun) requestRun();
          }}
        />
        <div className="pt-1 space-y-1">
          {running ? (
            <Button
              size="sm"
              variant="destructive"
              className="w-full h-7"
              onClick={requestStop}
              onPointerDown={(e) => e.stopPropagation()}
            >
              <Square className="mr-2 h-3.5 w-3.5" /> Stop
            </Button>
          ) : (
            <Button
              size="sm"
              className="w-full h-7"
              disabled={!canRun}
              onClick={requestRun}
              onPointerDown={(e) => e.stopPropagation()}
            >
              <Play className="mr-2 h-3.5 w-3.5" /> Run
            </Button>
          )}
        </div>
      </CardContent>
    </NodeShell>
  );
}

/**
 * Derive a NodeStatus from persisted progress data.
 * See bug-fix-stage-node.tsx for the same helper with full docs.
 */
function deriveStatusFromProgress(
  progressItems: { status: string; ts: number }[],
  phase: string,
): NodeStatus | null {
  if (progressItems.length === 0) return null;
  const last = progressItems[progressItems.length - 1];
  if (last.status === 'Done') return 'COMPLETE';
  if (last.status === 'Error') return 'ERROR';
  if (phase === 'running') return 'IN_PROGRESS';
  if (phase === 'complete' || phase === 'error') return 'COMPLETE';
  return null;
}

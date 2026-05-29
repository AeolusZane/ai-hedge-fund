import { CardContent } from '@/components/ui/card';
import { useFlowContext } from '@/contexts/flow-context';
import { useNodeContext } from '@/contexts/node-context';
import { cn } from '@/lib/utils';
import type { NodeStatus } from '@/nodes/utils';
import { type NodeProps } from '@xyflow/react';
import { Wrench } from 'lucide-react';
import type { BugFixStageNode } from '../types';
import { getStatusColor } from '../utils';
import { NodeShell } from './node-shell';

/**
 * Bug-fix stage node — the canvas counterpart to one bug_fix executor stage.
 *
 * Status is sourced from the shared NodeContext (same pattern as AgentNode),
 * so progress events streamed by the RunDialog can light up the right tile
 * as the executor walks the graph.
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
  const status: NodeStatus = liveStatus ?? (data.status as NodeStatus) ?? 'IDLE';
  const isInProgress = status === 'IN_PROGRESS';

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
    >
      <CardContent
        className={cn(
          'pt-2 pb-3 text-xs text-muted-foreground',
          isInProgress && 'gradient-animation'
        )}
      >
        <div className="flex items-center justify-between">
          <span>Stage</span>
          <span className={cn('font-mono', getStatusColor(status))}>{status}</span>
        </div>
      </CardContent>
    </NodeShell>
  );
}

import { CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { useFlowContext } from '@/contexts/flow-context';
import { useNodeContext } from '@/contexts/node-context';
import { useNodeState } from '@/hooks/use-node-state';
import { cn } from '@/lib/utils';
import type { NodeStatus } from '@/nodes/utils';
import { type NodeProps } from '@xyflow/react';
import { FolderGit2 } from 'lucide-react';
import type { RepoPathInputNode } from '../types';
import { getStatusColor } from '../utils';
import { NodeShell } from './node-shell';

/**
 * Holds the absolute path to the git repo Patch / Open PR will operate
 * on. Acts as a runnable node — when the executor walks the graph it
 * just copies the persisted value into shared state so downstream
 * stages can read it.
 */
export function RepoPathInputNode({
  data,
  selected,
  id,
  isConnectable,
}: NodeProps<RepoPathInputNode>) {
  const [repoPath, setRepoPath] = useNodeState<string>(id, 'repoPath', '');

  const { currentFlowId } = useFlowContext();
  const { getAgentNodeDataForFlow } = useNodeContext();
  const agentNodeData = getAgentNodeDataForFlow(currentFlowId?.toString() || null);
  const status: NodeStatus = (agentNodeData[id]?.status as NodeStatus) ?? 'IDLE';
  const isInProgress = status === 'IN_PROGRESS';

  return (
    <NodeShell
      id={id}
      selected={selected}
      isConnectable={isConnectable}
      icon={<FolderGit2 className="h-5 w-5" />}
      iconColor={status === 'IDLE' ? 'text-emerald-500' : getStatusColor(status)}
      name={data.name}
      description={data.description}
      status={status}
      hasLeftHandle={false}
    >
      <CardContent
        className={cn('pt-2 pb-3 space-y-2', isInProgress && 'gradient-animation')}
      >
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>Repo path</span>
          <span className={cn('font-mono', getStatusColor(status))}>{status}</span>
        </div>
        <Input
          value={repoPath}
          onChange={(e) => setRepoPath(e.target.value)}
          placeholder="/absolute/path/to/repo"
          className="h-7 text-xs font-mono"
          onPointerDown={(e) => e.stopPropagation()}
          onKeyDown={(e) => e.stopPropagation()}
        />
      </CardContent>
    </NodeShell>
  );
}

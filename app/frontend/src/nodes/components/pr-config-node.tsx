import { CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { useFlowContext } from '@/contexts/flow-context';
import { useNodeContext } from '@/contexts/node-context';
import { useNodeState } from '@/hooks/use-node-state';
import { cn } from '@/lib/utils';
import type { NodeStatus } from '@/nodes/utils';
import { type NodeProps } from '@xyflow/react';
import { GitPullRequest } from 'lucide-react';
import type { PrConfigNode } from '../types';
import { getStatusColor } from '../utils';
import { NodeShell } from './node-shell';

/**
 * Holds the Bitbucket coordinates Open PR will target: project key,
 * repo slug, target branch (defaults to "main"). Persisted with
 * useNodeState; the run dialog folds the values into node.data when
 * submitting so the executor can read them.
 */
export function PrConfigNode({
  data,
  selected,
  id,
  isConnectable,
}: NodeProps<PrConfigNode>) {
  const [project, setProject] = useNodeState<string>(id, 'project', '');
  const [repo, setRepo] = useNodeState<string>(id, 'repo', '');
  const [targetBranch, setTargetBranch] = useNodeState<string>(id, 'targetBranch', 'main');

  const { currentFlowId } = useFlowContext();
  const { getAgentNodeDataForFlow } = useNodeContext();
  const agentNodeData = getAgentNodeDataForFlow(currentFlowId?.toString() || null);
  const status: NodeStatus = (agentNodeData[id]?.status as NodeStatus) ?? 'IDLE';
  const isInProgress = status === 'IN_PROGRESS';

  const field = (
    label: string,
    value: string,
    onChange: (v: string) => void,
    placeholder: string,
    mono = true
  ) => (
    <div className="space-y-1">
      <label className="text-[10px] uppercase tracking-wide text-muted-foreground">
        {label}
      </label>
      <Input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={cn('h-7 text-xs', mono && 'font-mono')}
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
      icon={<GitPullRequest className="h-5 w-5" />}
      iconColor={status === 'IDLE' ? 'text-violet-500' : getStatusColor(status)}
      name={data.name}
      description={data.description}
      status={status}
      hasLeftHandle={false}
    >
      <CardContent
        className={cn('pt-2 pb-3 space-y-2', isInProgress && 'gradient-animation')}
      >
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>PR target</span>
          <span className={cn('font-mono', getStatusColor(status))}>{status}</span>
        </div>
        {field('Project key', project, setProject, 'BI')}
        {field('Repo slug', repo, setRepo, 'finebi-mobile')}
        {field('Target branch', targetBranch, setTargetBranch, 'main')}
      </CardContent>
    </NodeShell>
  );
}

import { CardContent } from '@/components/ui/card';
import { ModelSelector } from '@/components/ui/llm-selector';
import { useFlowContext } from '@/contexts/flow-context';
import { useNodeContext } from '@/contexts/node-context';
import { getModels, type LanguageModel } from '@/data/models';
import { useNodeState } from '@/hooks/use-node-state';
import { cn } from '@/lib/utils';
import type { NodeStatus } from '@/nodes/utils';
import { type NodeProps } from '@xyflow/react';
import { Wrench } from 'lucide-react';
import { useEffect, useState } from 'react';
import type { BugFixStageNode } from '../types';
import { getStatusColor } from '../utils';
import { NodeShell } from './node-shell';

const STAGES_THAT_USE_AN_LLM = new Set(['Analyze']);

/**
 * Bug-fix stage node — the canvas counterpart to one bug_fix executor stage.
 *
 * Stages that drive an LLM (currently just `Analyze`) render a per-node
 * ModelSelector and persist the choice via useNodeState. The Run dialog
 * reads each Analyze node's stored modelName / modelProvider when it
 * snapshots the graph for submission, so different Analyze nodes on the
 * same canvas can target different providers.
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

  const needsModel = STAGES_THAT_USE_AN_LLM.has(data.name);
  const [models, setModels] = useState<LanguageModel[]>([]);
  const [modelName, setModelName] = useNodeState<string>(id, 'modelName', '');
  const [, setModelProvider] = useNodeState<string>(id, 'modelProvider', '');

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
          'pt-2 pb-3 text-xs text-muted-foreground space-y-2',
          isInProgress && 'gradient-animation'
        )}
      >
        <div className="flex items-center justify-between">
          <span>Stage</span>
          <span className={cn('font-mono', getStatusColor(status))}>{status}</span>
        </div>
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
      </CardContent>
    </NodeShell>
  );
}

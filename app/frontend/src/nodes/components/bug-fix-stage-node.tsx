import { Button } from '@/components/ui/button';
import { CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { ModelSelector } from '@/components/ui/llm-selector';
import { useFlowContext } from '@/contexts/flow-context';
import { useNodeContext } from '@/contexts/node-context';
import { getModels, type LanguageModel } from '@/data/models';
import { NodeOutputDialog } from '@/domains/bug-fix/node-output-dialog';
import { useNodeState } from '@/hooks/use-node-state';
import { cn } from '@/lib/utils';
import type { NodeStatus } from '@/nodes/utils';
import { type NodeProps } from '@xyflow/react';
import { Eye, Wrench } from 'lucide-react';
import { useEffect, useState } from 'react';
import type { BugFixStageNode } from '../types';
import { getStatusColor } from '../utils';
import { NodeShell } from './node-shell';

const STAGES_THAT_USE_AN_LLM = new Set(['Analyze']);
const STAGES_THAT_NEED_REPO_PATH = new Set(['Patch', 'Open PR']);
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
  const status: NodeStatus = liveStatus ?? (data.status as NodeStatus) ?? 'IDLE';
  const isInProgress = status === 'IN_PROGRESS';

  const needsModel = STAGES_THAT_USE_AN_LLM.has(data.name);
  const needsRepoPath = STAGES_THAT_NEED_REPO_PATH.has(data.name);
  const needsPrConfig = STAGES_THAT_NEED_PR_CONFIG.has(data.name);

  // Model selector state (Analyze)
  const [models, setModels] = useState<LanguageModel[]>([]);
  const [modelName, setModelName] = useNodeState<string>(id, 'modelName', '');
  const [, setModelProvider] = useNodeState<string>(id, 'modelProvider', '');

  // Repo path (Patch + Open PR)
  const [repoPath, setRepoPath] = useNodeState<string>(id, 'repoPath', '');

  // PR target (Open PR only)
  const [project, setProject] = useNodeState<string>(id, 'project', '');
  const [repo, setRepo] = useNodeState<string>(id, 'repo', '');
  const [targetBranch, setTargetBranch] = useNodeState<string>(id, 'targetBranch', 'main');

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
        <Button
          variant="outline"
          size="sm"
          className="w-full h-6 gap-1 text-[10px]"
          onPointerDown={(e) => e.stopPropagation()}
          onClick={(e) => {
            e.stopPropagation();
            setOutputOpen(true);
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
        {needsRepoPath && field('Repo path', repoPath, setRepoPath, '/absolute/path/to/repo')}
        {needsPrConfig && (
          <>
            {field('Project key', project, setProject, 'BI')}
            {field('Repo slug', repo, setRepo, 'finebi-mobile')}
            {field('Target branch', targetBranch, setTargetBranch, 'main')}
          </>
        )}
      </CardContent>
    </NodeShell>
  );
}

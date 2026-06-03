import { Button } from '@/components/ui/button';
import { CardContent } from '@/components/ui/card';
import { useFlowContext } from '@/contexts/flow-context';
import { useNodeContext } from '@/contexts/node-context';
import { useNodeOutput } from '@/domains/bug-fix/node-output-store';
import { useNodeState } from '@/hooks/use-node-state';
import { cn } from '@/lib/utils';
import type { NodeStatus } from '@/nodes/utils';
import { getStatusColor } from '@/nodes/utils';
import { type NodeProps } from '@xyflow/react';
import { Check, ShieldCheck, X } from 'lucide-react';
import { useMemo, useState } from 'react';
import type { GateNode as GateNodeType } from '../types';
import { NodeShell } from './node-shell';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

/**
 * Gate Node — a human-in-the-loop checkpoint.
 *
 * When the executor hits a gate node, it pauses and emits a "Gate" status
 * event. This component shows approve/reject buttons and an optional
 * context textarea. The decision is POSTed to /workflows/bug_fix/gate/{run_id}/{node_id}.
 */
export function GateNode({
  data,
  selected,
  id,
  isConnectable,
}: NodeProps<GateNodeType>) {
  const { currentFlowId } = useFlowContext();
  const { getAgentNodeDataForFlow } = useNodeContext();
  const agentNodeData = getAgentNodeDataForFlow(currentFlowId?.toString() || null);
  const nodeOutput = useNodeOutput();

  const liveStatus = agentNodeData[id]?.status as NodeStatus | undefined;
  const progressItems = nodeOutput.progressByAgent[id] ?? [];

  // Derive status from live SSE status or persisted progress
  const status: NodeStatus = useMemo(() => {
    if (liveStatus && liveStatus !== 'IDLE') return liveStatus;
    if (progressItems.length === 0) return (data.status as NodeStatus) ?? 'IDLE';
    const last = progressItems[progressItems.length - 1];
    if (last.status === 'Done') return 'COMPLETE';
    if (last.status === 'Error') return 'ERROR';
    if (last.status === 'Gate') return 'PAUSED';
    if (nodeOutput.phase === 'running') return 'IN_PROGRESS';
    return 'COMPLETE';
  }, [liveStatus, progressItems, data.status, nodeOutput.phase]);

  const isWaiting = status === 'PAUSED';
  const isDecided = status === 'COMPLETE' || status === 'ERROR';

  // Gate prompt from node data
  const [prompt] = useNodeState<string>(id, 'prompt', 'Review and approve to continue');

  // Decision context textarea
  const [context, setContext] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [decision, setDecision] = useState<string | null>(null);

  const runId = nodeOutput.runId;

  const submitDecision = async (action: 'approve' | 'reject') => {
    if (!runId) {
      console.error('No run_id available for gate decision');
      return;
    }
    setSubmitting(true);
    try {
      const response = await fetch(
        `${API_BASE_URL}/workflows/bug_fix/gate/${runId}/${id}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            action,
            reason: action === 'reject' ? context || 'Rejected by user' : '',
            context: action === 'approve' ? context : '',
          }),
        }
      );
      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: 'Unknown error' }));
        console.error('Gate decision failed:', err);
      } else {
        setDecision(action);
      }
    } catch (e) {
      console.error('Gate decision failed:', e);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <NodeShell
      id={id}
      selected={selected}
      isConnectable={isConnectable}
      icon={<ShieldCheck className="h-5 w-5" />}
      iconColor={getStatusColor(status)}
      name={data.name}
      description={data.description}
      status={status}
    >
      <CardContent className="pt-2 pb-3 text-xs text-muted-foreground space-y-2">
        {/* Prompt display */}
        <div className="text-[11px] text-foreground/80 line-clamp-2">
          {prompt}
        </div>

        {/* Waiting state — show approve/reject buttons */}
        {isWaiting && (
          <div className="space-y-2">
            <textarea
              placeholder="Optional context or reason..."
              value={context}
              onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setContext(e.target.value)}
              className="w-full min-h-[60px] text-[11px] resize-none rounded-md border border-input bg-background px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-ring"
              onPointerDown={(e: React.PointerEvent) => e.stopPropagation()}
              onKeyDown={(e: React.KeyboardEvent) => e.stopPropagation()}
            />
            <div className="flex gap-1.5">
              <Button
                size="sm"
                variant="default"
                className="flex-1 h-7 text-[10px] gap-1 bg-green-600 hover:bg-green-700"
                disabled={submitting}
                onPointerDown={(e) => e.stopPropagation()}
                onClick={(e) => {
                  e.stopPropagation();
                  submitDecision('approve');
                }}
              >
                <Check className="h-3 w-3" />
                Approve
              </Button>
              <Button
                size="sm"
                variant="destructive"
                className="flex-1 h-7 text-[10px] gap-1"
                disabled={submitting}
                onPointerDown={(e) => e.stopPropagation()}
                onClick={(e) => {
                  e.stopPropagation();
                  submitDecision('reject');
                }}
              >
                <X className="h-3 w-3" />
                Reject
              </Button>
            </div>
            {submitting && (
              <div className="text-[10px] text-center text-muted-foreground animate-pulse">
                Submitting decision...
              </div>
            )}
          </div>
        )}

        {/* Decided state — show result */}
        {isDecided && decision && (
          <div className={cn(
            'flex items-center gap-1.5 text-[11px] font-medium px-2 py-1.5 rounded',
            decision === 'approve'
              ? 'bg-green-50 dark:bg-green-950/20 text-green-700 dark:text-green-400'
              : 'bg-red-50 dark:bg-red-950/20 text-red-700 dark:text-red-400'
          )}>
            {decision === 'approve' ? (
              <><Check className="h-3 w-3" /> Approved</>
            ) : (
              <><X className="h-3 w-3" /> Rejected</>
            )}
          </div>
        )}

        {/* Idle state */}
        {status === 'IDLE' && (
          <div className="text-[10px] text-muted-foreground/60 italic">
            Waiting for run to reach this gate...
          </div>
        )}
      </CardContent>
    </NodeShell>
  );
}

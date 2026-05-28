import { CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { type NodeProps } from '@xyflow/react';
import { Wrench } from 'lucide-react';
import type { NodeStatus } from '@/nodes/utils';
import type { BugFixStageNode } from '../types';
import { getStatusColor } from '../utils';
import { NodeShell } from './node-shell';

/**
 * Bug-fix stage node — the canvas counterpart to one bug_fix executor stage.
 *
 * E1: visual only. The node carries name/description/status and renders the
 * shared NodeShell with the wrench icon used elsewhere for the bug_fix
 * domain. Wiring this onto a real graph-driven Run flow is a follow-up
 * phase; today the Run button still uses the dialog.
 */
export function BugFixStageNode({
  data,
  selected,
  id,
  isConnectable,
}: NodeProps<BugFixStageNode>) {
  const status: NodeStatus = (data.status as NodeStatus) ?? 'IDLE';
  return (
    <NodeShell
      id={id}
      selected={selected}
      isConnectable={isConnectable}
      icon={<Wrench className="h-5 w-5" />}
      iconColor="text-amber-500"
      name={data.name}
      description={data.description}
      status={status}
    >
      <CardContent className="pt-2 pb-3 text-xs text-muted-foreground">
        <div className={cn('flex items-center justify-between')}>
          <span>Stage</span>
          <span className={cn('font-mono', getStatusColor(status))}>{status}</span>
        </div>
      </CardContent>
    </NodeShell>
  );
}

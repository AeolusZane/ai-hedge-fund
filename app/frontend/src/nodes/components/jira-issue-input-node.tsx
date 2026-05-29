import { CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { useNodeState } from '@/hooks/use-node-state';
import { cn } from '@/lib/utils';
import { type NodeProps } from '@xyflow/react';
import { Inbox } from 'lucide-react';
import type { JiraIssueInputNode } from '../types';
import { NodeShell } from './node-shell';

/**
 * Canvas-resident input node for the bug_fix domain.
 *
 * Holds the Jira issue key persistently (via useNodeState) so the RunDialog
 * can read it instead of asking the user every time. The dialog still falls
 * back to its own input when no input node is present on the canvas.
 */
export function JiraIssueInputNode({
  data,
  selected,
  id,
  isConnectable,
}: NodeProps<JiraIssueInputNode>) {
  const [issueKey, setIssueKey] = useNodeState<string>(id, 'issueKey', '');

  return (
    <NodeShell
      id={id}
      selected={selected}
      isConnectable={isConnectable}
      icon={<Inbox className="h-5 w-5" />}
      iconColor="text-blue-500"
      name={data.name}
      description={data.description}
      hasLeftHandle={false}
    >
      <CardContent className={cn('pt-2 pb-3 space-y-2')}>
        <label className="text-[10px] uppercase tracking-wide text-muted-foreground">
          Issue key
        </label>
        <Input
          value={issueKey}
          onChange={(e) => setIssueKey(e.target.value)}
          placeholder="e.g. BI-158957"
          className="h-7 text-xs font-mono"
          onPointerDown={(e) => e.stopPropagation()}
          onKeyDown={(e) => e.stopPropagation()}
        />
      </CardContent>
    </NodeShell>
  );
}

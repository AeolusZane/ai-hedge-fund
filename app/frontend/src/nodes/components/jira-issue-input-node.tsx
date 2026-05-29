import { Button } from '@/components/ui/button';
import { CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  requestRun,
  requestStop,
  useRunPhase,
} from '@/domains/bug-fix/run-controller';
import { useNodeState } from '@/hooks/use-node-state';
import { cn } from '@/lib/utils';
import { type NodeProps } from '@xyflow/react';
import { Inbox, Play, Square } from 'lucide-react';
import type { JiraIssueInputNode } from '../types';
import { NodeShell } from './node-shell';

/**
 * Canvas-resident input node for the bug_fix domain.
 *
 * Owns the Jira issue key (via useNodeState) and also acts as the start
 * trigger: clicking Play asks the always-mounted Run dialog to open and
 * begin executing the canvas. The dialog continues to host the progress
 * timeline and final result, but the entry point lives here on the
 * canvas instead of in the top bar.
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
  const canRun = !running && issueKey.trim().length > 0;

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
          onKeyDown={(e) => {
            e.stopPropagation();
            if (e.key === 'Enter' && canRun) requestRun();
          }}
        />
        <div className="pt-1">
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

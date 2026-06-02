import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useNodeOutput } from './node-output-store';

interface NodeOutputDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** React Flow node id. The dialog filters every store slice to this id. */
  agentId: string;
  /** Stage label rendered in the header (e.g. "Analyze"). */
  stageName: string;
}

/**
 * Per-node "what did THIS stage produce?" dialog. Subscribes to the
 * shared bug_fix run store and shows only the streaming buffer,
 * progress timeline, and result slice that belong to this agent id.
 *
 * Read-only — the actual Run is driven by the global BugFixRunDialog
 * via the run-controller. Opening this dialog while a run is in
 * flight still updates live because the store is shared.
 */
export function NodeOutputDialog({
  open,
  onOpenChange,
  agentId,
  stageName,
}: NodeOutputDialogProps) {
  const { streamingByAgent, progressByAgent, result, phase } = useNodeOutput();
  const stream = streamingByAgent[agentId] ?? '';
  const progress = progressByAgent[agentId] ?? [];
  const running = phase === 'running';

  // Each stage publishes its output under a known key on the run's
  // complete payload; pull the slice that belongs to this stage.
  const slice = sliceFor(stageName, result);

  const empty = !stream && progress.length === 0 && !slice && !running;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {stageName}
            <Badge variant="outline" className="text-[10px] font-mono">
              {agentId.slice(0, 24)}
            </Badge>
          </DialogTitle>
          <DialogDescription>
            Live output and result for this node only. Updates as the
            shared run progresses.
          </DialogDescription>
        </DialogHeader>

        {empty && (
          <div className="text-xs text-muted-foreground py-4 text-center">
            Nothing here yet — kick off a run from the Jira Issue Input node.
          </div>
        )}

        {progress.length > 0 && (
          <div className="border rounded-md p-2 max-h-32 overflow-y-auto text-xs font-mono space-y-0.5">
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
              Status timeline
            </div>
            {progress.map((p, i) => (
              <div key={i} className="text-muted-foreground">{p.status}</div>
            ))}
          </div>
        )}

        {(stream || (running && !slice)) && (
          <div className="border rounded-md p-2 space-y-1">
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
              {running ? 'Streaming…' : 'LLM output'}
            </div>
            <pre className="whitespace-pre-wrap font-mono text-[11px] bg-muted/30 rounded p-2 max-h-72 overflow-auto">
              {stream || '(no streaming output for this stage)'}
              {running && <span className="animate-pulse">▍</span>}
            </pre>
          </div>
        )}

        {slice && (
          <div className="border rounded-md p-2 space-y-1">
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
              Result
            </div>
            <pre className="whitespace-pre-wrap font-mono text-[11px] bg-muted/30 rounded p-2 max-h-72 overflow-auto">
              {JSON.stringify(slice, null, 2)}
            </pre>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function sliceFor(stageName: string, result: any): any {
  if (!result || typeof result !== 'object') return null;
  switch (stageName) {
    case 'Jira Issue Input':
      return result.jira ?? null;
    case 'Analyze':
      return result.analysis ?? (result.analyze_error ? { error: result.analyze_error } : null);
    case 'Patch':
      return result.patch ?? (result.patch_error ? { error: result.patch_error } : null);
    case 'Open PR':
      return result.open_pr ?? (result.open_pr_error ? { error: result.open_pr_error } : null);
    default:
      return null;
  }
}

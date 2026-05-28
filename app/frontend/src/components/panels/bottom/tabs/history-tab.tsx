import { useFlowContext } from '@/contexts/flow-context';
import { api } from '@/services/api';
import { FlowRunDetail, FlowRunStatus, FlowRunSummary } from '@/services/types';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { RefreshCw, ChevronRight, ChevronDown } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

interface HistoryTabProps {
  className?: string;
}

const statusVariant: Record<FlowRunStatus, 'success' | 'secondary' | 'destructive' | 'outline'> = {
  COMPLETE: 'success',
  IN_PROGRESS: 'secondary',
  ERROR: 'destructive',
  IDLE: 'outline',
};

function formatDuration(started?: string | null, completed?: string | null): string {
  if (!started || !completed) return '-';
  const ms = new Date(completed).getTime() - new Date(started).getTime();
  if (ms < 1000) return `${ms}ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)}s`;
  return `${Math.floor(s / 60)}m ${Math.floor(s % 60)}s`;
}

function formatTime(iso?: string | null): string {
  if (!iso) return '-';
  return new Date(iso).toLocaleString();
}

export function HistoryTab({ className }: HistoryTabProps) {
  const { currentFlowId } = useFlowContext();
  const [runs, setRuns] = useState<FlowRunSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [detailById, setDetailById] = useState<Record<number, FlowRunDetail>>({});
  const [detailLoadingId, setDetailLoadingId] = useState<number | null>(null);

  const fetchRuns = useCallback(async () => {
    if (currentFlowId == null) {
      setRuns([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const list = await api.getFlowRuns(currentFlowId);
      setRuns(list);
    } catch (e: any) {
      setError(e?.message ?? 'Failed to load runs');
    } finally {
      setLoading(false);
    }
  }, [currentFlowId]);

  useEffect(() => {
    fetchRuns();
  }, [fetchRuns]);

  const toggleExpand = useCallback(
    async (runId: number) => {
      if (expandedId === runId) {
        setExpandedId(null);
        return;
      }
      setExpandedId(runId);
      if (!detailById[runId] && currentFlowId != null) {
        setDetailLoadingId(runId);
        try {
          const detail = await api.getFlowRun(currentFlowId, runId);
          setDetailById((prev) => ({ ...prev, [runId]: detail }));
        } catch (e) {
          // Leave it empty; error shown inline
        } finally {
          setDetailLoadingId(null);
        }
      }
    },
    [expandedId, detailById, currentFlowId]
  );

  if (currentFlowId == null) {
    return (
      <div className={cn('h-full flex items-center justify-center text-muted-foreground text-sm', className)}>
        Save the flow first to start recording run history.
      </div>
    );
  }

  return (
    <div className={cn('h-full flex flex-col font-mono text-sm', className)}>
      <div className="flex items-center justify-between px-2 py-1 border-b">
        <div className="text-xs text-muted-foreground">
          {loading ? 'Loading…' : `${runs.length} run${runs.length === 1 ? '' : 's'}`}
        </div>
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={fetchRuns} aria-label="Refresh">
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
        </Button>
      </div>

      {error && (
        <div className="px-3 py-2 text-destructive text-xs border-b">{error}</div>
      )}

      <div className="flex-1 overflow-y-auto">
        {runs.length === 0 && !loading && (
          <div className="text-center py-8 text-muted-foreground">
            No runs yet. Click Run on the canvas to create one.
          </div>
        )}

        {runs.map((run) => {
          const expanded = expandedId === run.id;
          const detail = detailById[run.id];
          return (
            <div key={run.id} className="border-b">
              <button
                type="button"
                onClick={() => toggleExpand(run.id)}
                className="w-full flex items-center gap-2 px-3 py-2 hover-bg text-left"
              >
                {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                <span className="font-semibold w-12">#{run.run_number}</span>
                <Badge variant={statusVariant[run.status] ?? 'outline'} className="text-[10px]">
                  {run.status}
                </Badge>
                <span className="text-xs text-muted-foreground flex-1 truncate">
                  {formatTime(run.started_at ?? run.created_at)}
                </span>
                <span className="text-xs text-muted-foreground">
                  {formatDuration(run.started_at, run.completed_at)}
                </span>
              </button>

              {expanded && (
                <div className="px-6 py-2 bg-muted/30">
                  {detailLoadingId === run.id && (
                    <div className="text-xs text-muted-foreground">Loading…</div>
                  )}

                  {run.status === 'ERROR' && run.error_message && (
                    <div className="mb-2">
                      <div className="text-xs font-semibold text-destructive mb-1">Error</div>
                      <pre className="whitespace-pre-wrap text-xs text-destructive">{run.error_message}</pre>
                    </div>
                  )}

                  {detail?.results && (
                    <>
                      {detail.results.decisions && (
                        <div className="mb-3">
                          <div className="text-xs font-semibold mb-1">Decisions</div>
                          <pre className="whitespace-pre-wrap text-xs bg-background p-2 rounded">
                            {JSON.stringify(detail.results.decisions, null, 2)}
                          </pre>
                        </div>
                      )}

                      {detail.results.analyst_signals && (
                        <div className="mb-3">
                          <div className="text-xs font-semibold mb-1">Analyst Signals</div>
                          <pre className="whitespace-pre-wrap text-xs bg-background p-2 rounded max-h-64 overflow-auto">
                            {JSON.stringify(detail.results.analyst_signals, null, 2)}
                          </pre>
                        </div>
                      )}

                      {detail.results.current_prices && (
                        <div>
                          <div className="text-xs font-semibold mb-1">Prices</div>
                          <pre className="whitespace-pre-wrap text-xs bg-background p-2 rounded">
                            {JSON.stringify(detail.results.current_prices, null, 2)}
                          </pre>
                        </div>
                      )}
                    </>
                  )}

                  {detail && !detail.results && run.status !== 'ERROR' && (
                    <div className="text-xs text-muted-foreground">No results captured.</div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

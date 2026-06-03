import { useEffect, useState, useCallback } from 'react';
import { Bug, ExternalLink, History, Play, RefreshCw, CheckCircle2, XCircle, Clock, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

interface JiraBug {
  key: string;
  summary: string;
  status: string;
  priority: string;
  assignee: string;
}

interface BugFixRun {
  id: string;
  jira_issue: string;
  summary: string;
  status: 'running' | 'in_progress' | 'complete' | 'error' | 'idle';
  current_stage: string;
  started_at: string;
  completed_at?: string;
  pr_url?: string;
  stages_completed: string[];
}

const STAGES = ['Analyze', 'Patch', 'Test', 'Open PR'];

const statusConfig: Record<string, { icon: React.ReactNode; color: string; label: string }> = {
  running: { icon: <Clock className="h-3 w-3 animate-spin" />, color: 'bg-blue-500', label: 'Running' },
  in_progress: { icon: <Clock className="h-3 w-3 animate-spin" />, color: 'bg-blue-500', label: 'Running' },
  complete: { icon: <CheckCircle2 className="h-3 w-3" />, color: 'bg-green-500', label: 'Done' },
  error: { icon: <XCircle className="h-3 w-3" />, color: 'bg-red-500', label: 'Failed' },
  idle: { icon: <Clock className="h-3 w-3" />, color: 'bg-gray-400', label: 'Idle' },
};

export function BugFixDashboard() {
  const [bugs, setBugs] = useState<JiraBug[]>([]);
  const [runs, setRuns] = useState<BugFixRun[]>([]);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState<'active' | 'bugs' | 'history'>('active');
  const [triggering, setTriggering] = useState<string | null>(null);

  const fetchBugs = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/bug-fix/jira/bugs');
      if (res.ok) {
        const data = await res.json();
        setBugs(data.bugs || []);
      }
    } catch (err) {
      console.error('Failed to fetch bugs:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchRuns = useCallback(async () => {
    try {
      const res = await fetch('/bug-fix/runs');
      if (res.ok) {
        const data = await res.json();
        setRuns(data.runs || []);
      }
    } catch (err) {
      console.error('Failed to fetch runs:', err);
    }
  }, []);

  const triggerFix = async (issueKey: string) => {
    setTriggering(issueKey);
    try {
      const res = await fetch('/bug-fix/trigger', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          jira_issue: issueKey,
        }),
      });
      if (res.ok) {
        await fetchRuns();
        setTab('active');
      }
    } catch (err) {
      console.error('Failed to trigger fix:', err);
    } finally {
      setTriggering(null);
    }
  };

  useEffect(() => {
    fetchBugs();
    fetchRuns();
  }, [fetchBugs, fetchRuns]);

  useEffect(() => {
    const interval = setInterval(fetchRuns, 3000);
    return () => clearInterval(interval);
  }, [fetchRuns]);

  const activeRuns = runs.filter(r => r.status === 'running' || r.status === 'in_progress' || r.status === 'idle');
  const completedRuns = runs.filter(r => r.status === 'complete' || r.status === 'error');

  return (
    <div className="min-h-screen bg-background">
      {/* Header — mobile-first */}
      <header className="sticky top-0 z-10 bg-background/95 backdrop-blur border-b px-4 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Bug className="h-5 w-5 text-red-500" />
            <h1 className="text-lg font-bold">Bug Fix</h1>
          </div>
          <Button onClick={() => { fetchBugs(); fetchRuns(); }} variant="ghost" size="icon" className="h-8 w-8">
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </header>

      {/* Tab bar — bottom on mobile, top on desktop */}
      <nav className="sticky top-[57px] z-10 bg-background/95 backdrop-blur border-b px-4">
        <div className="flex">
          {([
            { key: 'active' as const, label: 'Active', count: activeRuns.length },
            { key: 'bugs' as const, label: 'Jira Bugs', count: bugs.length },
            { key: 'history' as const, label: 'Archive', count: completedRuns.length },
          ]).map(t => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`flex-1 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                tab === t.key
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground'
              }`}
            >
              {t.label}
              {t.count > 0 && (
                <span className="ml-1.5 px-1.5 py-0.5 text-xs rounded-full bg-muted">
                  {t.count}
                </span>
              )}
            </button>
          ))}
        </div>
      </nav>

      {/* Content */}
      <main className="p-4 pb-20 space-y-3">
        {/* Active runs */}
        {tab === 'active' && (
          activeRuns.length === 0 ? (
            <div className="text-center py-16 text-muted-foreground">
              <Bug className="h-12 w-12 mx-auto mb-3 opacity-20" />
              <p>No active fixes</p>
              <p className="text-sm mt-1">Go to Jira Bugs tab to start one</p>
            </div>
          ) : (
            activeRuns.map(run => {
              const cfg = statusConfig[run.status] || statusConfig.idle;
              return (
                <Card key={run.id} className="overflow-hidden">
                  <CardContent className="p-4 space-y-3">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <Badge variant="outline" className="shrink-0 font-mono text-xs">
                            {run.jira_issue}
                          </Badge>
                          <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full text-white ${cfg.color}`}>
                            {cfg.icon} {cfg.label}
                          </span>
                        </div>
                        <p className="text-sm font-medium truncate">{run.summary || 'Processing...'}</p>
                      </div>
                    </div>
                    {/* Stage progress */}
                    <div className="flex items-center gap-1">
                      {STAGES.map((stage, i) => {
                        const done = run.stages_completed.includes(stage.toLowerCase().replace(' ', '_'));
                        const current = run.current_stage?.toLowerCase() === stage.toLowerCase();
                        return (
                          <div key={stage} className="flex items-center flex-1">
                            <div className={`flex-1 h-1.5 rounded-full transition-colors ${
                              done ? 'bg-green-500' : current ? 'bg-blue-500 animate-pulse' : 'bg-muted'
                            }`} />
                            {i < STAGES.length - 1 && <div className="w-1" />}
                          </div>
                        );
                      })}
                    </div>
                    <div className="flex justify-between text-[10px] text-muted-foreground">
                      {STAGES.map(stage => (
                        <span key={stage} className="flex-1 text-center">{stage}</span>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              );
            })
          )
        )}

        {/* Jira bugs list */}
        {tab === 'bugs' && (
          loading ? (
            <div className="text-center py-16 text-muted-foreground">
              <RefreshCw className="h-6 w-6 animate-spin mx-auto mb-2" />
              <p>Loading from Jira...</p>
            </div>
          ) : bugs.length === 0 ? (
            <div className="text-center py-16 text-muted-foreground">
              <CheckCircle2 className="h-12 w-12 mx-auto mb-3 text-green-500 opacity-40" />
              <p>No bugs found</p>
            </div>
          ) : (
            bugs.map(bug => {
              const isFixing = activeRuns.some(r => r.jira_issue === bug.key);
              return (
                <Card key={bug.key} className="overflow-hidden">
                  <CardContent className="p-0">
                    <div className="flex items-center gap-3 p-4">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <a
                            href={`https://jira.fineres.com/browse/${bug.key}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="font-mono text-xs text-blue-600 hover:underline flex items-center gap-0.5"
                          >
                            {bug.key}
                            <ExternalLink className="h-3 w-3" />
                          </a>
                          <Badge variant="outline" className="text-[10px] px-1.5">
                            {bug.priority}
                          </Badge>
                        </div>
                        <p className="text-sm font-medium line-clamp-2">{bug.summary}</p>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {bug.assignee || 'Unassigned'}
                        </p>
                      </div>
                      <Button
                        size="sm"
                        variant={isFixing ? 'secondary' : 'default'}
                        disabled={isFixing || triggering === bug.key}
                        onClick={() => triggerFix(bug.key)}
                        className="shrink-0 h-9 px-3"
                      >
                        {isFixing ? (
                          <span className="flex items-center gap-1 text-xs">
                            <Clock className="h-3 w-3 animate-spin" /> Fixing
                          </span>
                        ) : triggering === bug.key ? (
                          <RefreshCw className="h-3 w-3 animate-spin" />
                        ) : (
                          <span className="flex items-center gap-1 text-xs">
                            <Play className="h-3 w-3" /> Fix
                          </span>
                        )}
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              );
            })
          )
        )}

        {/* History / Archive */}
        {tab === 'history' && (
          completedRuns.length === 0 ? (
            <div className="text-center py-16 text-muted-foreground">
              <History className="h-12 w-12 mx-auto mb-3 opacity-20" />
              <p>No completed fixes yet</p>
            </div>
          ) : (
            completedRuns.map(run => {
              const cfg = statusConfig[run.status] || statusConfig.idle;
              return (
                <Card key={run.id} className="overflow-hidden">
                  <CardContent className="p-4">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <Badge variant="outline" className="shrink-0 font-mono text-xs">
                            {run.jira_issue}
                          </Badge>
                          <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full text-white ${cfg.color}`}>
                            {cfg.icon} {cfg.label}
                          </span>
                        </div>
                        <p className="text-sm font-medium truncate">{run.summary}</p>
                        <p className="text-xs text-muted-foreground mt-1">
                          {run.completed_at
                            ? new Date(run.completed_at).toLocaleString()
                            : new Date(run.started_at).toLocaleString()}
                        </p>
                      </div>
                      {run.pr_url && (
                        <a
                          href={run.pr_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="shrink-0"
                        >
                          <Button variant="outline" size="sm" className="h-8 px-2">
                            <span className="text-xs">PR</span>
                            <ChevronRight className="h-3 w-3 ml-0.5" />
                          </Button>
                        </a>
                      )}
                    </div>
                  </CardContent>
                </Card>
              );
            })
          )
        )}
      </main>
    </div>
  );
}

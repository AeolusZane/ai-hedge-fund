import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Activity, Brain, CheckCircle2, ChevronDown, ChevronRight, ChevronLeft, Clock,
  Edit3, ExternalLink, Filter, Lightbulb, Search, Star, Tag,
  TrendingDown, TrendingUp, Trash2, X, Zap, AlertTriangle, BarChart3,
  BookOpen, Target, ArrowUp, ArrowDown, Minus, MessageSquare, Bug,
  RefreshCw, GitPullRequest
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter
} from '@/components/ui/dialog';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  type EvolutionRun,
  type EvolutionRunDetail,
  type EvolutionExperience,
  type MetricsSummary,
  type HealthScore,
  type EvolutionMetrics,
  listRuns,
  getRunDetail,
  submitFeedback,
  listExperiences,
  updateExperience,
  deleteExperience,
  getMetricsTimeline,
  getMetricsSummary,
  getHealthScore,
  syncPrFeedback,
  syncAllPrFeedback,
} from './evolution-api';

// ─── Constants ───────────────────────────────────────────────────────────────

const DIFFICULTY_COLORS: Record<string, string> = {
  L1: 'bg-green-100 text-green-800 border-green-200',
  L2: 'bg-blue-100 text-blue-800 border-blue-200',
  L3: 'bg-orange-100 text-orange-800 border-orange-200',
  L4: 'bg-red-100 text-red-800 border-red-200',
};

const RATING_LABELS: Record<number, string> = {
  1: 'Completely Wrong',
  2: 'Right Direction, Poor Execution',
  3: 'Mostly Correct',
  4: 'Correct',
  5: 'Excellent',
};

const TREND_ICONS: Record<string, React.ReactNode> = {
  improving: <TrendingUp className="h-4 w-4 text-green-500" />,
  declining: <TrendingDown className="h-4 w-4 text-red-500" />,
  stable: <Minus className="h-4 w-4 text-gray-400" />,
  no_data: <Minus className="h-4 w-4 text-gray-300" />,
};

// ─── Star Rating Component ───────────────────────────────────────────────────

function StarRating({
  value,
  onChange,
  readonly = false,
  size = 'md',
}: {
  value: number;
  onChange?: (v: number) => void;
  readonly?: boolean;
  size?: 'sm' | 'md';
}) {
  const starSize = size === 'sm' ? 'h-3 w-3' : 'h-5 w-5';
  return (
    <div className="flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map((star) => (
        <Star
          key={star}
          className={`${starSize} ${
            star <= value
              ? 'fill-yellow-400 text-yellow-400'
              : 'text-gray-300'
          } ${!readonly ? 'cursor-pointer hover:text-yellow-300' : ''}`}
          onClick={() => !readonly && onChange?.(star)}
        />
      ))}
    </div>
  );
}

// ─── Difficulty Badge ────────────────────────────────────────────────────────

function DifficultyBadge({ level }: { level: string }) {
  if (!level) return <Badge variant="outline" className="text-xs">Unknown</Badge>;
  return (
    <Badge variant="outline" className={`text-xs ${DIFFICULTY_COLORS[level] || ''}`}>
      {level}
    </Badge>
  );
}

// ─── Runs Timeline Panel ─────────────────────────────────────────────────────

function RunsTimelinePanel() {
  const [runs, setRuns] = useState<EvolutionRun[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [difficultyFilter, setDifficultyFilter] = useState('');
  const [reviewFilter, setReviewFilter] = useState<'all' | 'reviewed' | 'pending'>('all');
  const [selectedRun, setSelectedRun] = useState<EvolutionRunDetail | null>(null);
  const [syncingId, setSyncingId] = useState<number | null>(null);
  const [syncAll, setSyncAll] = useState(false);
  const [syncMessage, setSyncMessage] = useState<{ type: 'success' | 'info'; text: string } | null>(null);

  const loadRuns = useCallback(async () => {
    setLoading(true);
    try {
      const result = await listRuns({
        limit: 100,
        difficulty: difficultyFilter,
        reviewed_only: reviewFilter === 'reviewed',
        search,
      });
      setRuns(result.runs);
      setTotal(result.total);
    } catch (e) {
      console.error('Failed to load runs:', e);
    } finally {
      setLoading(false);
    }
  }, [difficultyFilter, reviewFilter, search]);

  useEffect(() => { loadRuns(); }, [loadRuns]);

  const handleViewDetail = async (run: EvolutionRun) => {
    try {
      const detail = await getRunDetail(run.id);
      setSelectedRun(detail);
    } catch (e) {
      console.error('Failed to load run detail:', e);
    }
  };

  const handleSyncPrFeedback = async (run: EvolutionRun) => {
    if (!run.pr_id) return;
    setSyncingId(run.id);
    try {
      const result = await syncPrFeedback(run.id);
      if (result.synced) {
        const sentimentEmoji = result.sentiment === 'positive' ? '👍' : result.sentiment === 'negative' ? '👎' : '😐';
        const lessonText = result.lesson ? ` · Lesson: "${result.lesson.slice(0, 60)}${result.lesson.length > 60 ? '...' : ''}"` : '';
        setSyncMessage({
          type: 'success',
          text: `${sentimentEmoji} Rating ${result.rating}/5 (${result.sentiment})${lessonText}`,
        });
      } else {
        setSyncMessage({ type: 'info', text: result.message || 'No reviewer comments found on PR yet' });
      }
      loadRuns();
    } catch (e) {
      setSyncMessage({ type: 'info', text: 'Sync failed — PR may not have review comments yet' });
    } finally {
      setSyncingId(null);
      setTimeout(() => setSyncMessage(null), 6000);
    }
  };

  const handleSyncAll = async () => {
    setSyncAll(true);
    try {
      const result = await syncAllPrFeedback();
      setSyncMessage({
        type: result.synced > 0 ? 'success' : 'info',
        text: `Checked ${result.total_checked} PRs, synced ${result.synced} feedback`,
      });
      loadRuns();
    } catch (e) {
      setSyncMessage({ type: 'info', text: 'Bulk sync failed' });
    } finally {
      setSyncAll(false);
      setTimeout(() => setSyncMessage(null), 5000);
    }
  };

  const filteredRuns = reviewFilter === 'pending'
    ? runs.filter((r) => r.human_rating === null)
    : runs;

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <Input
            placeholder="Search by issue key, summary, or lesson..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <div className="flex items-center gap-1">
          {['', 'L1', 'L2', 'L3', 'L4'].map((level) => (
            <Button
              key={level}
              variant={difficultyFilter === level ? 'default' : 'outline'}
              size="sm"
              onClick={() => setDifficultyFilter(level)}
              className="text-xs"
            >
              {level || 'All'}
            </Button>
          ))}
        </div>
        <div className="flex items-center gap-1">
          {(['all', 'reviewed', 'pending'] as const).map((f) => (
            <Button
              key={f}
              variant={reviewFilter === f ? 'default' : 'outline'}
              size="sm"
              onClick={() => setReviewFilter(f)}
              className="text-xs capitalize"
            >
              {f}
            </Button>
          ))}
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={handleSyncAll}
          disabled={syncAll}
          className="text-xs flex items-center gap-1"
          title="Sync feedback from all PRs"
        >
          <RefreshCw className={`h-3 w-3 ${syncAll ? 'animate-spin' : ''}`} />
          Sync PRs
        </Button>
        <span className="text-xs text-gray-500 ml-auto">
          {filteredRuns.length} of {total} runs
        </span>
      </div>

      {/* Run Cards */}
      {loading ? (
        <div className="text-center py-12 text-gray-400">Loading runs...</div>
      ) : filteredRuns.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <Activity className="h-8 w-8 mx-auto mb-2 opacity-50" />
          <p>No runs found. Trigger a bug fix to see results here.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {filteredRuns.map((run) => (
            <Card key={run.id} className="hover:shadow-md transition-shadow">
              <CardContent className="p-4">
                <div className="flex items-start gap-3">
                  {/* Status icon */}
                  <div className="mt-1">
                    {run.first_fix_success === 1 ? (
                      <CheckCircle2 className="h-5 w-5 text-green-500" />
                    ) : run.first_fix_success === 0 ? (
                      <X className="h-5 w-5 text-red-400" />
                    ) : (
                      <Clock className="h-5 w-5 text-gray-400" />
                    )}
                  </div>

                  {/* Main content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-mono text-xs text-gray-500">{run.issue_key}</span>
                      <DifficultyBadge level={run.difficulty_level} />
                      {run.first_fix_success === 1 && (
                        <Badge variant="outline" className="text-xs bg-green-50 text-green-700 border-green-200">
                          First Fix
                        </Badge>
                      )}
                      {run.first_fix_success === 0 && (
                        <Badge variant="outline" className="text-xs text-gray-500">
                          {run.iteration_count} iterations
                        </Badge>
                      )}
                    </div>
                    <p className="text-sm font-medium truncate">{run.issue_summary}</p>
                    <div className="flex items-center gap-3 mt-2 text-xs text-gray-500">
                      {run.knowledge_used_count > 0 && (
                        <span className="flex items-center gap-1">
                          <Brain className="h-3 w-3" />
                          {run.knowledge_used_count} experiences used
                        </span>
                      )}
                      {run.lesson && (
                        <span className="flex items-center gap-1 truncate max-w-[300px]">
                          <Lightbulb className="h-3 w-3 text-yellow-500" />
                          {run.lesson}
                        </span>
                      )}
                      <span className="flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {run.duration_seconds.toFixed(1)}s
                      </span>
                    </div>
                    {/* Rating */}
                    {run.human_rating && (
                      <div className="flex items-center gap-2 mt-2">
                        <StarRating value={run.human_rating} readonly size="sm" />
                        {run.human_feedback && (
                          <span className="text-xs text-gray-500 truncate max-w-[200px]">
                            "{run.human_feedback}"
                          </span>
                        )}
                      </div>
                    )}
                  </div>

                   {/* Actions */}
                   <div className="flex items-center gap-1 shrink-0">
                     <Button
                       variant="ghost"
                       size="sm"
                       onClick={() => handleViewDetail(run)}
                       className="text-xs"
                     >
                       <ChevronRight className="h-4 w-4" />
                     </Button>
                     {run.pr_url && (
                       <Button
                         variant="ghost"
                         size="sm"
                         onClick={() => window.open(run.pr_url, '_blank')}
                         className="text-xs"
                         title="Open PR in Bitbucket"
                       >
                         <GitPullRequest className="h-4 w-4" />
                       </Button>
                     )}
                     {run.pr_id && !run.human_rating && (
                       <Button
                         variant="ghost"
                         size="sm"
                         onClick={() => handleSyncPrFeedback(run)}
                         disabled={syncingId === run.id}
                         className="text-xs"
                         title="Sync feedback from PR"
                       >
                         <RefreshCw className={`h-4 w-4 ${syncingId === run.id ? 'animate-spin' : ''}`} />
                       </Button>
                     )}
                   </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Run Detail Dialog */}
      <Dialog open={!!selectedRun} onOpenChange={() => setSelectedRun(null)}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <span className="font-mono text-sm">{selectedRun?.issue_key}</span>
              <DifficultyBadge level={selectedRun?.difficulty_level || ''} />
            </DialogTitle>
          </DialogHeader>
          {selectedRun && (
            <div className="space-y-4 text-sm">
              <div>
                <h4 className="font-medium mb-1">{selectedRun.issue_summary}</h4>
                <p className="text-gray-600 text-xs whitespace-pre-wrap">
                  {selectedRun.issue_description?.slice(0, 500)}
                </p>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <h5 className="font-medium text-xs text-gray-500 uppercase mb-1">Root Cause</h5>
                  <p className="text-xs">{selectedRun.root_cause || selectedRun.root_cause_hypothesis || 'N/A'}</p>
                </div>
                <div>
                  <h5 className="font-medium text-xs text-gray-500 uppercase mb-1">Patch Strategy</h5>
                  <p className="text-xs">{selectedRun.patch_strategy || 'N/A'}</p>
                </div>
              </div>

              {selectedRun.files_changed.length > 0 && (
                <div>
                  <h5 className="font-medium text-xs text-gray-500 uppercase mb-1">Files Changed</h5>
                  <div className="flex flex-wrap gap-1">
                    {selectedRun.files_changed.map((f) => (
                      <Badge key={f} variant="outline" className="text-xs font-mono">{f}</Badge>
                    ))}
                  </div>
                </div>
              )}

              {selectedRun.knowledge_used.length > 0 && (
                <div>
                  <h5 className="font-medium text-xs text-gray-500 uppercase mb-1">
                    Knowledge Used ({selectedRun.knowledge_used.length})
                  </h5>
                  <div className="space-y-1">
                    {selectedRun.knowledge_used.map((k) => (
                      <div key={k.id} className="text-xs bg-gray-50 p-2 rounded">
                        <span className="font-mono text-gray-400">#{k.id}</span>{' '}
                        <span className="text-gray-600">{k.lesson}</span>
                        <span className="text-gray-400 ml-2">score: {k.score.toFixed(2)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {selectedRun.lesson && (
                <div>
                  <h5 className="font-medium text-xs text-gray-500 uppercase mb-1">Lesson Learned</h5>
                  <p className="text-xs bg-yellow-50 p-2 rounded border border-yellow-100">
                    {selectedRun.lesson}
                  </p>
                  {selectedRun.lesson_tags.length > 0 && (
                    <div className="flex gap-1 mt-1">
                      {selectedRun.lesson_tags.map((t) => (
                        <Badge key={t} variant="secondary" className="text-xs">{t}</Badge>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* PR Linkage */}
              {selectedRun.pr_url && (
                <div>
                  <h5 className="font-medium text-xs text-gray-500 uppercase mb-1">Pull Request</h5>
                  <div className="flex items-center gap-2">
                    <a
                      href={selectedRun.pr_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-blue-600 hover:underline flex items-center gap-1"
                    >
                      <GitPullRequest className="h-3 w-3" />
                      PR #{selectedRun.pr_id}
                      <ExternalLink className="h-3 w-3" />
                    </a>
                    {selectedRun.pr_feedback_synced_at && (
                      <Badge variant="outline" className="text-xs bg-green-50 text-green-700 border-green-200">
                        Feedback synced
                      </Badge>
                    )}
                    {selectedRun.pr_id && !selectedRun.human_rating && (
                      <Button
                        variant="outline"
                        size="sm"
                        className="text-xs h-6"
                        onClick={() => {
                          handleSyncPrFeedback(selectedRun);
                          setSelectedRun(null);
                        }}
                      >
                        <RefreshCw className="h-3 w-3 mr-1" />
                        Sync from PR
                      </Button>
                    )}
                  </div>
                  <p className="text-xs text-gray-400 mt-1">
                    Feedback is collected on the PR. Review code there and leave a rating comment.
                  </p>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>

       {/* Sync Message Toast */}
       {syncMessage && (
         <div className={`p-3 rounded-lg text-sm flex items-center gap-2 ${
           syncMessage.type === 'success'
             ? 'bg-green-50 text-green-700 border border-green-200'
             : 'bg-blue-50 text-blue-700 border border-blue-200'
         }`}>
           {syncMessage.type === 'success' ? (
             <CheckCircle2 className="h-4 w-4" />
           ) : (
             <AlertTriangle className="h-4 w-4" />
           )}
           {syncMessage.text}
           <Button variant="ghost" size="sm" className="ml-auto h-6 w-6 p-0" onClick={() => setSyncMessage(null)}>
             <X className="h-3 w-3" />
           </Button>
         </div>
       )}
    </div>
  );
}

// ─── Experience Browser Panel ────────────────────────────────────────────────

function ExperienceBrowserPanel() {
  const [experiences, setExperiences] = useState<EvolutionExperience[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [tagFilter, setTagFilter] = useState('');
  const [editingExp, setEditingExp] = useState<EvolutionExperience | null>(null);
  const [editForm, setEditForm] = useState({ lesson: '', lesson_tags: '' });

  const loadExperiences = useCallback(async () => {
    setLoading(true);
    try {
      const result = await listExperiences({ limit: 100, tag: tagFilter, search });
      setExperiences(result.experiences);
      setTotal(result.total);
    } catch (e) {
      console.error('Failed to load experiences:', e);
    } finally {
      setLoading(false);
    }
  }, [tagFilter, search]);

  useEffect(() => { loadExperiences(); }, [loadExperiences]);

  const handleDelete = async (id: number) => {
    if (!confirm('Delete this experience? This cannot be undone.')) return;
    try {
      await deleteExperience(id);
      loadExperiences();
    } catch (e) {
      console.error('Failed to delete:', e);
    }
  };

  const handleEdit = (exp: EvolutionExperience) => {
    setEditForm({
      lesson: exp.lesson,
      lesson_tags: exp.lesson_tags.join(', '),
    });
    setEditingExp(exp);
  };

  const handleSaveEdit = async () => {
    if (!editingExp) return;
    try {
      await updateExperience(editingExp.id, {
        lesson: editForm.lesson,
        lesson_tags: editForm.lesson_tags.split(',').map((t) => t.trim()).filter(Boolean),
      });
      setEditingExp(null);
      loadExperiences();
    } catch (e) {
      console.error('Failed to update:', e);
    }
  };

  const reviewedCount = experiences.filter((e) => e.human_rating !== null).length;

  // Collect all unique tags
  const allTags = Array.from(new Set(experiences.flatMap((e) => e.lesson_tags))).sort();

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <Input
            placeholder="Search experiences..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        {allTags.length > 0 && (
          <select
            value={tagFilter}
            onChange={(e) => setTagFilter(e.target.value)}
            className="border rounded px-2 py-1 text-sm"
          >
            <option value="">All Tags</option>
            {allTags.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        )}
        <span className="text-xs text-gray-500 ml-auto">
          {total} experiences · {reviewedCount} reviewed · {total - reviewedCount} pending
        </span>
      </div>

      {/* Experience Cards */}
      {loading ? (
        <div className="text-center py-12 text-gray-400">Loading...</div>
      ) : experiences.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <BookOpen className="h-8 w-8 mx-auto mb-2 opacity-50" />
          <p>No experiences yet. They will appear as the agent fixes bugs.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {experiences.map((exp) => (
            <Card key={exp.id} className="hover:shadow-sm transition-shadow">
              <CardContent className="p-3">
                <div className="flex items-start gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs text-gray-400 font-mono">#{exp.id}</span>
                      <span className="font-mono text-xs text-gray-500">{exp.issue_key}</span>
                      <DifficultyBadge level={exp.difficulty_level} />
                      {exp.human_rating && <StarRating value={exp.human_rating} readonly size="sm" />}
                    </div>
                    {exp.lesson ? (
                      <p className="text-sm">{exp.lesson}</p>
                    ) : (
                      <p className="text-sm text-gray-400 italic">No lesson extracted</p>
                    )}
                    <div className="flex items-center gap-2 mt-1">
                      {exp.lesson_tags.map((t) => (
                        <Badge key={t} variant="secondary" className="text-xs">{t}</Badge>
                      ))}
                      <span className="text-xs text-gray-400 ml-auto">
                        Applied {exp.lesson_applied}x
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <Button variant="ghost" size="sm" onClick={() => handleEdit(exp)}>
                      <Edit3 className="h-3 w-3" />
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => handleDelete(exp.id)}>
                      <Trash2 className="h-3 w-3 text-red-400" />
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Edit Dialog */}
      <Dialog open={!!editingExp} onOpenChange={() => setEditingExp(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Experience #{editingExp?.id}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="text-sm font-medium">Lesson</label>
              <textarea
                className="w-full mt-1 p-2 border rounded text-sm min-h-[80px]"
                value={editForm.lesson}
                onChange={(e) => setEditForm({ ...editForm, lesson: e.target.value })}
              />
            </div>
            <div>
              <label className="text-sm font-medium">Tags (comma-separated)</label>
              <Input
                value={editForm.lesson_tags}
                onChange={(e) => setEditForm({ ...editForm, lesson_tags: e.target.value })}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditingExp(null)}>Cancel</Button>
            <Button onClick={handleSaveEdit}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ─── Metrics Charts Panel ────────────────────────────────────────────────────

function MetricsChartsPanel() {
  const [metrics, setMetrics] = useState<EvolutionMetrics[]>([]);
  const [summary, setSummary] = useState<MetricsSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [metricsResult, summaryResult] = await Promise.all([
          getMetricsTimeline(200),
          getMetricsSummary(),
        ]);
        setMetrics(metricsResult.metrics);
        setSummary(summaryResult);
      } catch (e) {
        console.error('Failed to load metrics:', e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) {
    return <div className="text-center py-12 text-gray-400">Loading metrics...</div>;
  }

  if (!summary || summary.total_runs === 0) {
    return (
      <div className="text-center py-12 text-gray-400">
        <BarChart3 className="h-8 w-8 mx-auto mb-2 opacity-50" />
        <p>No metrics data yet. Complete some bug fixes to see evolution charts.</p>
      </div>
    );
  }

  // Build learning curve data points
  const learningCurve = metrics.map((m, i) => ({
    x: i + 1,
    y: m.cumulative_first_fix_rate * 100,
  }));

  const maxY = Math.max(...learningCurve.map((p) => p.y), 10);
  const chartWidth = 500;
  const chartHeight = 200;
  const padding = 40;

  // SVG path for learning curve
  const points = learningCurve.map((p, i) => {
    const x = padding + (i / Math.max(learningCurve.length - 1, 1)) * (chartWidth - padding * 2);
    const y = chartHeight - padding - (p.y / 100) * (chartHeight - padding * 2);
    return `${x},${y}`;
  });
  const pathD = points.length > 1 ? `M ${points.join(' L ')}` : '';

  return (
    <div className="space-y-6">
      {/* Overall Stats */}
      <div className="grid grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4 text-center">
            <p className="text-2xl font-bold">{summary.overall_first_fix_rate}%</p>
            <p className="text-xs text-gray-500">First Fix Rate</p>
            <div className="flex justify-center mt-1">{TREND_ICONS[summary.trend]}</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <p className="text-2xl font-bold">{summary.overall_avg_iterations}</p>
            <p className="text-xs text-gray-500">Avg Iterations</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <p className="text-2xl font-bold">{summary.overall_knowledge_utilization}%</p>
            <p className="text-xs text-gray-500">Knowledge Utilization</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <p className="text-2xl font-bold">{summary.total_runs}</p>
            <p className="text-xs text-gray-500">Total Runs</p>
          </CardContent>
        </Card>
      </div>

      {/* Learning Curve */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Learning Curve — First Fix Rate Over Time</CardTitle>
        </CardHeader>
        <CardContent>
          {learningCurve.length < 2 ? (
            <p className="text-xs text-gray-400 text-center py-4">Need at least 2 runs to show trend</p>
          ) : (
            <svg viewBox={`0 0 ${chartWidth} ${chartHeight}`} className="w-full h-48">
              {/* Grid lines */}
              {[0, 25, 50, 75, 100].map((v) => {
                const y = chartHeight - padding - (v / 100) * (chartHeight - padding * 2);
                return (
                  <g key={v}>
                    <line x1={padding} y1={y} x2={chartWidth - padding} y2={y} stroke="#e5e7eb" strokeWidth="1" />
                    <text x={padding - 5} y={y + 4} textAnchor="end" className="text-[10px] fill-gray-400">
                      {v}%
                    </text>
                  </g>
                );
              })}
              {/* Line */}
              <path d={pathD} fill="none" stroke="#3b82f6" strokeWidth="2" />
              {/* Points */}
              {learningCurve.map((p, i) => {
                const x = padding + (i / Math.max(learningCurve.length - 1, 1)) * (chartWidth - padding * 2);
                const y = chartHeight - padding - (p.y / 100) * (chartHeight - padding * 2);
                return <circle key={i} cx={x} cy={y} r="3" fill="#3b82f6" />;
              })}
            </svg>
          )}
        </CardContent>
      </Card>

      {/* Difficulty Breakdown */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Fix Rate by Difficulty</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {['L1', 'L2', 'L3', 'L4'].map((level) => {
              const data = summary.by_difficulty[level];
              const rate = data?.first_fix_rate || 0;
              const count = data?.count || 0;
              const barColor = rate >= 70 ? 'bg-green-500' : rate >= 40 ? 'bg-blue-500' : rate >= 20 ? 'bg-orange-500' : 'bg-red-400';

              return (
                <div key={level} className="flex items-center gap-3">
                  <DifficultyBadge level={level} />
                  <div className="flex-1">
                    <div className="h-6 bg-gray-100 rounded overflow-hidden relative">
                      <div
                        className={`h-full ${barColor} transition-all duration-500`}
                        style={{ width: `${rate}%` }}
                      />
                      <span className="absolute inset-0 flex items-center px-2 text-xs font-medium">
                        {rate}%
                      </span>
                    </div>
                  </div>
                  <span className="text-xs text-gray-400 w-12 text-right">{count} runs</span>
                  {rate < 30 && count > 0 && (
                    <AlertTriangle className="h-4 w-4 text-orange-400" />
                  )}
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Knowledge Utilization Trend */}
      {metrics.length >= 2 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Knowledge Utilization Trend</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 gap-4 text-center">
              {(() => {
                const recent = metrics.slice(-10);
                const earlier = metrics.slice(-20, -10);
                const recentRecall = recent.length > 0
                  ? recent.reduce((s, m) => s + (m.knowledge_recalled > 0 ? m.knowledge_used / m.knowledge_recalled : 0), 0) / recent.length
                  : 0;
                const earlierRecall = earlier.length > 0
                  ? earlier.reduce((s, m) => s + (m.knowledge_recalled > 0 ? m.knowledge_used / m.knowledge_recalled : 0), 0) / earlier.length
                  : 0;
                const trend = recentRecall > earlierRecall + 0.05 ? 'up' : recentRecall < earlierRecall - 0.05 ? 'down' : 'flat';

                return (
                  <>
                    <div>
                      <p className="text-lg font-bold">{Math.round(earlierRecall * 100)}%</p>
                      <p className="text-xs text-gray-500">Earlier (runs {earlier.length > 0 ? `-${earlier.length * 2}` : 'N/A'} to -{earlier.length})</p>
                    </div>
                    <div>
                      <p className="text-lg font-bold">{Math.round(recentRecall * 100)}%</p>
                      <p className="text-xs text-gray-500">Recent (last {recent.length})</p>
                    </div>
                    <div>
                      <div className="flex items-center justify-center gap-1">
                        {trend === 'up' && <ArrowUp className="h-5 w-5 text-green-500" />}
                        {trend === 'down' && <ArrowDown className="h-5 w-5 text-red-500" />}
                        {trend === 'flat' && <Minus className="h-5 w-5 text-gray-400" />}
                      </div>
                      <p className="text-xs text-gray-500">Trend</p>
                    </div>
                  </>
                );
              })()}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ─── Health Score Panel ──────────────────────────────────────────────────────

function HealthScorePanel() {
  const [health, setHealth] = useState<HealthScore | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getHealthScore()
      .then(setHealth)
      .catch((e) => console.error('Failed to load health:', e))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <div className="text-center py-12 text-gray-400">Loading health score...</div>;
  }

  if (!health || health.score === 0) {
    return (
      <div className="text-center py-12 text-gray-400">
        <Target className="h-8 w-8 mx-auto mb-2 opacity-50" />
        <p>Not enough data to compute health score. Need at least 3 runs.</p>
      </div>
    );
  }

  const scoreColor = health.score >= 70 ? 'text-green-600' : health.score >= 40 ? 'text-yellow-600' : 'text-red-600';
  const scoreRing = health.score >= 70 ? '#22c55e' : health.score >= 40 ? '#eab308' : '#ef4444';

  const dimensionLabels: Record<string, { label: string; icon: React.ReactNode }> = {
    learning_speed: { label: 'Learning Speed', icon: <Zap className="h-4 w-4" /> },
    knowledge_utilization: { label: 'Knowledge Use', icon: <Brain className="h-4 w-4" /> },
    fix_quality: { label: 'Fix Quality', icon: <CheckCircle2 className="h-4 w-4" /> },
    knowledge_quality: { label: 'Knowledge Quality', icon: <BookOpen className="h-4 w-4" /> },
  };

  // SVG donut chart
  const radius = 60;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (health.score / 100) * circumference;

  return (
    <div className="space-y-6">
      {/* Score Circle */}
      <div className="flex justify-center">
        <div className="relative">
          <svg width="160" height="160" className="transform -rotate-90">
            <circle cx="80" cy="80" r={radius} fill="none" stroke="#e5e7eb" strokeWidth="12" />
            <circle
              cx="80"
              cy="80"
              r={radius}
              fill="none"
              stroke={scoreRing}
              strokeWidth="12"
              strokeDasharray={circumference}
              strokeDashoffset={offset}
              strokeLinecap="round"
              className="transition-all duration-1000"
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className={`text-3xl font-bold ${scoreColor}`}>{health.score}</span>
            <span className="text-xs text-gray-500">/ 100</span>
          </div>
        </div>
      </div>

      {/* Dimension Cards */}
      <div className="grid grid-cols-2 gap-4">
        {Object.entries(health.dimensions).map(([key, dim]) => {
          const info = dimensionLabels[key] || { label: key, icon: <Activity className="h-4 w-4" /> };
          const dimColor = dim.score >= 70 ? 'text-green-600' : dim.score >= 40 ? 'text-yellow-600' : 'text-red-600';

          return (
            <Card key={key}>
              <CardContent className="p-4">
                <div className="flex items-center gap-2 mb-2">
                  {info.icon}
                  <span className="text-sm font-medium">{info.label}</span>
                  <span className="ml-auto">{TREND_ICONS[dim.trend]}</span>
                </div>
                <p className={`text-2xl font-bold ${dimColor}`}>{dim.score}</p>
                <div className="h-1.5 bg-gray-100 rounded mt-2">
                  <div
                    className={`h-full rounded transition-all ${
                      dim.score >= 70 ? 'bg-green-500' : dim.score >= 40 ? 'bg-yellow-500' : 'bg-red-400'
                    }`}
                    style={{ width: `${dim.score}%` }}
                  />
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Suggestions */}
      {health.suggestions.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-orange-500" />
              Suggestions
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2">
              {health.suggestions.map((s, i) => (
                <li key={i} className="text-sm text-gray-600 flex items-start gap-2">
                  <span className="text-orange-400 mt-0.5">•</span>
                  {s}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ─── Main Dashboard ──────────────────────────────────────────────────────────

export function EvolutionDashboard() {
  const navigate = useNavigate();
  return (
    <div className="h-full flex flex-col">
      <div className="p-4 border-b">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => navigate('/bug-fix')}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <div>
            <h1 className="text-lg font-semibold flex items-center gap-2">
              <Activity className="h-5 w-5 text-blue-500" />
              Evolution Dashboard
            </h1>
            <p className="text-xs text-gray-500 mt-0.5">
              Track how the agent learns from each bug fix
            </p>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-4">
        <Tabs defaultValue="runs" className="space-y-4">
          <TabsList>
            <TabsTrigger value="runs" className="text-sm">
              <Activity className="h-3.5 w-3.5 mr-1.5" />
              Runs
            </TabsTrigger>
            <TabsTrigger value="experiences" className="text-sm">
              <BookOpen className="h-3.5 w-3.5 mr-1.5" />
              Experiences
            </TabsTrigger>
            <TabsTrigger value="metrics" className="text-sm">
              <BarChart3 className="h-3.5 w-3.5 mr-1.5" />
              Metrics
            </TabsTrigger>
            <TabsTrigger value="health" className="text-sm">
              <Target className="h-3.5 w-3.5 mr-1.5" />
              Health
            </TabsTrigger>
          </TabsList>

          <TabsContent value="runs">
            <RunsTimelinePanel />
          </TabsContent>
          <TabsContent value="experiences">
            <ExperienceBrowserPanel />
          </TabsContent>
          <TabsContent value="metrics">
            <MetricsChartsPanel />
          </TabsContent>
          <TabsContent value="health">
            <HealthScorePanel />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}

/**
 * Evolution Dashboard API service layer
 */

const API_BASE = '/api';

// ─── Types ───────────────────────────────────────────────────────────────────

export interface EvolutionRun {
  id: number;
  issue_key: string;
  issue_summary: string;
  bug_type: string;
  difficulty_level: string;
  first_fix_success: number | null;
  iteration_count: number;
  duration_seconds: number;
  human_rating: number | null;
  human_feedback: string;
  reviewed_at: string | null;
  created_at: string;
  lesson: string;
  lesson_tags: string[];
  knowledge_used_count: number;
}

export interface EvolutionRunDetail extends EvolutionRun {
  issue_description: string;
  root_cause: string;
  root_cause_hypothesis: string;
  affected_areas: string[];
  suggested_approach: string[];
  confidence: number;
  patch_summary: string;
  files_changed: string[];
  patch_strategy: string;
  knowledge_used: Array<{ id: number; score: number; lesson: string }>;
  lesson_applied: number;
  components: string[];
  labels: string[];
  run_id: string;
}

export interface EvolutionExperience {
  id: number;
  issue_key: string;
  issue_summary: string;
  bug_type: string;
  difficulty_level: string;
  lesson: string;
  lesson_tags: string[];
  lesson_applied: number;
  human_rating: number | null;
  human_feedback: string;
  reviewed_at: string | null;
  created_at: string;
}

export interface EvolutionMetrics {
  id: number;
  created_at: string;
  run_id: string;
  experience_id: number | null;
  difficulty_level: string;
  first_fix_success: number | null;
  iteration_count: number;
  duration_seconds: number;
  knowledge_recalled: number;
  knowledge_used: number;
  code_cache_hit: number;
  code_cache_miss: number;
  cumulative_first_fix_rate: number;
  cumulative_avg_iterations: number;
  cumulative_knowledge_utilization: number;
  human_rating: number | null;
  issue_key?: string;
  issue_summary?: string;
  lesson?: string;
}

export interface MetricsSummary {
  total_runs: number;
  by_difficulty: Record<string, {
    count: number;
    first_fix_rate: number;
    avg_iterations: number;
  }>;
  overall_first_fix_rate: number;
  overall_avg_iterations: number;
  overall_knowledge_utilization: number;
  trend: 'improving' | 'declining' | 'stable' | 'no_data';
}

export interface HealthScore {
  score: number;
  dimensions: {
    learning_speed: { score: number; trend: string };
    knowledge_utilization: { score: number; trend: string };
    fix_quality: { score: number; trend: string };
    knowledge_quality: { score: number; trend: string };
  };
  suggestions: string[];
}

export interface FeedbackRequest {
  rating: number;
  feedback: string;
  difficulty: string;
}

export interface ExperienceUpdateRequest {
  lesson?: string;
  lesson_tags?: string[];
  difficulty_level?: string;
  human_feedback?: string;
  human_rating?: number;
  bug_type?: string;
  patch_summary?: string;
  patch_strategy?: string;
}

// ─── API Functions ───────────────────────────────────────────────────────────

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${url}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!response.ok) {
    const error = await response.text();
    throw new Error(`API error: ${response.status} - ${error}`);
  }
  return response.json();
}

// Runs (Experiences)
export async function listRuns(params: {
  limit?: number;
  offset?: number;
  difficulty?: string;
  min_rating?: number;
  reviewed_only?: boolean;
  search?: string;
} = {}): Promise<{ total: number; runs: EvolutionRun[] }> {
  const searchParams = new URLSearchParams();
  if (params.limit) searchParams.set('limit', String(params.limit));
  if (params.offset) searchParams.set('offset', String(params.offset));
  if (params.difficulty) searchParams.set('difficulty', params.difficulty);
  if (params.min_rating) searchParams.set('min_rating', String(params.min_rating));
  if (params.reviewed_only) searchParams.set('reviewed_only', 'true');
  if (params.search) searchParams.set('search', params.search);
  
  return fetchJson(`/evolution/runs?${searchParams}`);
}

export async function getRunDetail(experienceId: number): Promise<EvolutionRunDetail> {
  return fetchJson(`/evolution/runs/${experienceId}`);
}

export async function submitFeedback(
  experienceId: number,
  feedback: FeedbackRequest
): Promise<{ success: boolean; experience_id: number; rating: number }> {
  return fetchJson(`/evolution/runs/${experienceId}/feedback`, {
    method: 'POST',
    body: JSON.stringify(feedback),
  });
}

// Experiences
export async function listExperiences(params: {
  limit?: number;
  offset?: number;
  tag?: string;
  difficulty?: string;
  min_rating?: number;
  reviewed_only?: boolean;
  search?: string;
} = {}): Promise<{ total: number; experiences: EvolutionExperience[] }> {
  const searchParams = new URLSearchParams();
  if (params.limit) searchParams.set('limit', String(params.limit));
  if (params.offset) searchParams.set('offset', String(params.offset));
  if (params.tag) searchParams.set('tag', params.tag);
  if (params.difficulty) searchParams.set('difficulty', params.difficulty);
  if (params.min_rating) searchParams.set('min_rating', String(params.min_rating));
  if (params.reviewed_only) searchParams.set('reviewed_only', 'true');
  if (params.search) searchParams.set('search', params.search);
  
  return fetchJson(`/evolution/experiences?${searchParams}`);
}

export async function getExperience(experienceId: number): Promise<EvolutionRunDetail> {
  return fetchJson(`/evolution/experiences/${experienceId}`);
}

export async function updateExperience(
  experienceId: number,
  updates: ExperienceUpdateRequest
): Promise<{ success: boolean; experience_id: number }> {
  return fetchJson(`/evolution/experiences/${experienceId}`, {
    method: 'PUT',
    body: JSON.stringify(updates),
  });
}

export async function deleteExperience(
  experienceId: number
): Promise<{ success: boolean; experience_id: number }> {
  return fetchJson(`/evolution/experiences/${experienceId}`, {
    method: 'DELETE',
  });
}

// Metrics
export async function getMetricsTimeline(
  limit: number = 100
): Promise<{ metrics: EvolutionMetrics[] }> {
  return fetchJson(`/evolution/metrics?limit=${limit}`);
}

export async function getMetricsSummary(): Promise<MetricsSummary> {
  return fetchJson('/evolution/metrics/summary');
}

// Health
export async function getHealthScore(): Promise<HealthScore> {
  return fetchJson('/evolution/health');
}

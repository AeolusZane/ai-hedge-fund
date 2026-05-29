// Cross-domain types. Finance-specific shapes (hedge fund requests,
// backtest results, portfolio positions) were removed when the project
// was scoped down to the coding/bug-fix domain.

export enum ModelProvider {
  OPENAI = 'OpenAI',
  ANTHROPIC = 'Anthropic',
  DEEPSEEK = 'DeepSeek',
  GOOGLE = 'Google',
  GROQ = 'Groq',
  OLLAMA = 'Ollama',
}

export type FlowRunStatus = 'IDLE' | 'IN_PROGRESS' | 'COMPLETE' | 'ERROR';

export interface FlowRunSummary {
  id: number;
  flow_id: number;
  status: FlowRunStatus;
  run_number: number;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
}

export interface FlowRunDetail extends FlowRunSummary {
  updated_at: string | null;
  request_data: Record<string, any> | null;
  results: Record<string, any> | null;
}

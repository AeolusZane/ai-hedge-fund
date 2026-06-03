/**
 * Agent Platform API client.
 *
 * Talks to the backend's /api/v1/agents endpoints for managing
 * external agents, triggering runs, and fetching status/outputs.
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export interface Agent {
  id: number;
  name: string;
  description?: string;
  endpoint: string;
  schedule?: string;
  is_active: boolean;
  input_keys?: string[];
  output_keys?: string[];
  color?: string;
  icon?: string;
  last_run_at?: string;
  last_run_status?: string;
  created_at: string;
}

export interface AgentRun {
  id: number;
  run_id: string;
  agent_name: string;
  status: string;
  progress?: number;
  message?: string;
  metrics?: Record<string, unknown>;
  started_at?: string;
  completed_at?: string;
  duration_seconds?: number;
  trigger_type: string;
  error_message?: string;
  created_at: string;
}

export interface AgentOutput {
  key?: string;
  data: unknown;
  created_at: string;
}

export interface AgentConnection {
  id: number;
  source_agent_id: number;
  source_output_key?: string;
  target_agent_id: number;
  target_input_key?: string;
  flow_id?: number;
}

export interface CreateAgentRequest {
  name: string;
  description?: string;
  endpoint: string;
  schedule?: string;
  input_keys?: string[];
  output_keys?: string[];
  color?: string;
  icon?: string;
}

export interface UpdateAgentRequest {
  description?: string;
  endpoint?: string;
  schedule?: string;
  input_keys?: string[];
  output_keys?: string[];
  is_active?: boolean;
  color?: string;
  icon?: string;
}

export const agentApi = {
  // ── CRUD ──────────────────────────────────────────────────────────

  list: async (): Promise<Agent[]> => {
    const response = await fetch(`${API_BASE_URL}/api/v1/agents`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  },

  get: async (agentId: number): Promise<Agent> => {
    const response = await fetch(`${API_BASE_URL}/api/v1/agents/${agentId}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  },

  create: async (data: CreateAgentRequest): Promise<Agent> => {
    const response = await fetch(`${API_BASE_URL}/api/v1/agents`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  },

  update: async (agentId: number, data: UpdateAgentRequest): Promise<Agent> => {
    const response = await fetch(`${API_BASE_URL}/api/v1/agents/${agentId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  },

  delete: async (agentId: number): Promise<void> => {
    const response = await fetch(`${API_BASE_URL}/api/v1/agents/${agentId}`, {
      method: 'DELETE',
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
  },

  // ── Trigger ───────────────────────────────────────────────────────

  trigger: async (agentId: number, config?: Record<string, unknown>): Promise<AgentRun> => {
    const response = await fetch(`${API_BASE_URL}/api/v1/agents/${agentId}/trigger`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ config, trigger_type: 'manual' }),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  },

  // ── Runs ──────────────────────────────────────────────────────────

  getRuns: async (agentId: number, limit = 20): Promise<AgentRun[]> => {
    const response = await fetch(`${API_BASE_URL}/api/v1/agents/${agentId}/runs?limit=${limit}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  },

  // ── Outputs ───────────────────────────────────────────────────────

  getOutputs: async (agentId: number): Promise<{ run_id: string; completed_at?: string; outputs: AgentOutput[] }> => {
    const response = await fetch(`${API_BASE_URL}/api/v1/agents/${agentId}/outputs`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  },

  // ── Connections ───────────────────────────────────────────────────

  listConnections: async (flowId?: number): Promise<AgentConnection[]> => {
    const url = flowId
      ? `${API_BASE_URL}/api/v1/agents/connections?flow_id=${flowId}`
      : `${API_BASE_URL}/api/v1/agents/connections`;
    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  },

  createConnection: async (data: {
    source_agent_id: number;
    source_output_key?: string;
    target_agent_id: number;
    target_input_key?: string;
    flow_id?: number;
  }): Promise<{ id: number }> => {
    const response = await fetch(`${API_BASE_URL}/api/v1/agents/connections`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  },

  deleteConnection: async (connId: number): Promise<void> => {
    const response = await fetch(`${API_BASE_URL}/api/v1/agents/connections/${connId}`, {
      method: 'DELETE',
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
  },
};

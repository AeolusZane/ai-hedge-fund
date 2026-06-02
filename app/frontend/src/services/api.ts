import { LanguageModel } from '@/data/models';
import { FlowRunDetail, FlowRunSummary } from '@/services/types';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

/**
 * Generic platform API client. Domain-specific run logic (e.g. bug_fix)
 * talks to /workflows/{domain}/run directly from its own dialog code;
 * everything in here is cross-domain (LLM model list, JSON storage,
 * flow run history).
 */
export const api = {
  getLanguageModels: async (): Promise<LanguageModel[]> => {
    const response = await fetch(`${API_BASE_URL}/language-models/`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    return data.models;
  },

  saveJsonFile: async (filename: string, data: any): Promise<void> => {
    const response = await fetch(`${API_BASE_URL}/storage/save-json`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename, data }),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
  },

  getFlowRuns: async (flowId: number, limit = 50): Promise<FlowRunSummary[]> => {
    const response = await fetch(`${API_BASE_URL}/flows/${flowId}/runs/?limit=${limit}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  },

  getFlowRun: async (flowId: number, runId: number): Promise<FlowRunDetail> => {
    const response = await fetch(`${API_BASE_URL}/flows/${flowId}/runs/${runId}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  },

  deleteFlowRun: async (flowId: number, runId: number): Promise<void> => {
    const response = await fetch(`${API_BASE_URL}/flows/${flowId}/runs/${runId}`, {
      method: 'DELETE',
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
  },

  deleteAllFlowRuns: async (flowId: number): Promise<void> => {
    const response = await fetch(`${API_BASE_URL}/flows/${flowId}/runs/`, {
      method: 'DELETE',
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
  },
};

import { AppNode } from "@/nodes/types";

export interface NodeTypeDefinition {
  createNode: (position: { x: number; y: number }) => AppNode;
}

const generateUniqueIdSuffix = (): string => {
  const chars = 'abcdefghijklmnopqrstuvwxyz0123456789';
  let result = '';
  for (let i = 0; i < 6; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return result;
};

export const extractBaseAgentKey = (uniqueId: string): string => {
  const parts = uniqueId.split('_');
  if (parts.length >= 2) {
    const lastPart = parts[parts.length - 1];
    if (lastPart.length === 6 && /^[a-z0-9]+$/.test(lastPart)) {
      return parts.slice(0, -1).join('_');
    }
  }
  return uniqueId;
};

// One factory for every bug_fix stage tile so we don't repeat boilerplate.
const bugFixStage = (name: string, description: string): NodeTypeDefinition => ({
  createNode: (position) => ({
    id: `${name.toLowerCase().replace(/[^a-z0-9]+/g, '_')}_${generateUniqueIdSuffix()}`,
    type: 'bug-fix-stage-node',
    position,
    data: { name, description, status: 'Idle' },
  }),
});

const nodeTypeDefinitions: Record<string, NodeTypeDefinition> = {
  'Jira Issue Input': {
    createNode: (position) => ({
      id: `jira_issue_input_${generateUniqueIdSuffix()}`,
      type: 'jira-issue-input-node',
      position,
      data: {
        name: 'Jira Issue Input',
        description: 'Persistent issue key consumed by the bug_fix runner.',
      },
    }),
  },
  Analyze: bugFixStage(
    'Analyze',
    'Reason about the root cause from the Jira description + linked code.'
  ),
  Patch: bugFixStage(
    'Patch',
    'Apply a code change that addresses the root cause.'
  ),
  Test: bugFixStage('Test', 'Run tests / lint to validate the patch.'),
  'Open PR': bugFixStage(
    'Open PR',
    'Open a pull request and link it back to the Jira issue.'
  ),
  Gate: {
    createNode: (position) => ({
      id: `gate_${generateUniqueIdSuffix()}`,
      type: 'gate-node',
      position,
      data: {
        name: 'Gate',
        description: 'Human review checkpoint — pauses execution until approved.',
        status: 'Idle',
      },
    }),
  },
  'External Agent': {
    createNode: (position) => ({
      id: `external_agent_${generateUniqueIdSuffix()}`,
      type: 'external-agent-node',
      position,
      data: {
        agentId: 0,
        agentName: 'New Agent',
        endpoint: 'http://localhost:8001/run',
        inputKeys: [],
        outputKeys: [],
        color: '#6366f1',
      },
    }),
  },
  'Register Agent': {
    createNode: (position) => ({
      id: `register_agent_${generateUniqueIdSuffix()}`,
      type: 'external-agent-node',
      position,
      data: {
        agentId: 0,
        agentName: 'Register New Agent',
        endpoint: '',
        inputKeys: [],
        outputKeys: [],
        color: '#10b981',
      },
    }),
  },
};

export async function getNodeTypeDefinition(componentName: string): Promise<NodeTypeDefinition | null> {
  return nodeTypeDefinitions[componentName] || null;
}

export async function getNodeIdForComponent(componentName: string): Promise<string | null> {
  const def = await getNodeTypeDefinition(componentName);
  if (!def) return null;
  return def.createNode({ x: 0, y: 0 }).id;
}

export const clearNodeTypeDefinitionsCache = () => {
  // No async cache to clear in single-domain mode; kept for callers.
};

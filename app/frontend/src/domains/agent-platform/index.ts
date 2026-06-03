import { Bot, Plus, Settings, Sparkles } from 'lucide-react';
import { registerDomain } from '@/core/domain-registry';
import type { DomainPack } from '@/core/types/domain-pack';
import type { WorkflowTemplate } from '@/core/types/workflow-template';
import { AgentBuilderNode } from '@/nodes/components/agent-builder-node';
import { ExternalAgentNode } from '@/nodes/components/external-agent-node';

/**
 * Agent Platform domain — manages external agents that run independently
 * and report back via callbacks. The platform handles scheduling,
 * monitoring, and data routing between agents.
 */

const agentPlatformTemplate: WorkflowTemplate = {
  id: 'agent_platform.basic',
  name: 'Basic Agent Chain',
  description: 'Two connected agents with data flow',
  nodes: [
    { key: 'agent1', componentName: 'External Agent', offsetX: 0, offsetY: 0 },
    { key: 'agent2', componentName: 'External Agent', offsetX: 350, offsetY: 0 },
  ],
  edges: [
    { source: 'agent1', target: 'agent2' },
  ],
};

const agentPlatformDomain: DomainPack = {
  id: 'agent_platform',
  name: 'Agent Platform',
  description: 'External agents with scheduling & monitoring',
  icon: Bot,
  nodeTypes: [
    {
      id: 'external-agent-node',
      component: ExternalAgentNode,
      defaultData: {
        agentId: 0,
        agentName: 'New Agent',
        endpoint: 'http://localhost:8001/run',
        inputKeys: [],
        outputKeys: [],
        color: '#6366f1',
      },
    },
    {
      id: 'agent-builder-node',
      component: AgentBuilderNode,
      defaultData: {
        agentId: `agent_${Date.now()}`,
        agentName: 'New Agent',
        description: '',
        skills: [],
        status: 'draft',
        color: '#8b5cf6',
      },
    },
  ],
  getComponentGroups: async () => [
    {
      name: 'Agents',
      icon: Bot,
      iconColor: 'text-indigo-500',
      items: [
        { name: 'External Agent', icon: Bot },
      ],
    },
    {
      name: 'Builder',
      icon: Sparkles,
      iconColor: 'text-purple-500',
      items: [
        { name: 'Create Agent', icon: Sparkles },
      ],
    },
    {
      name: 'Actions',
      icon: Settings,
      iconColor: 'text-gray-500',
      items: [
        { name: 'Register Agent', icon: Plus },
      ],
    },
  ],
  templates: [agentPlatformTemplate],
};

registerDomain(agentPlatformDomain);

export { agentPlatformDomain };

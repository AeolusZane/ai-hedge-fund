import { MessageItem } from '@/contexts/node-context';
import type { BuiltInNode, Node } from '@xyflow/react';
import type { AgentBuilderNodeData } from '@/nodes/components/agent-builder-node';
import type { ExternalAgentNodeData } from '@/nodes/components/external-agent-node';

export type NodeMessage = MessageItem;

export type JsonOutputNode = Node<{ name: string; description: string; status: string }, 'json-output-node'>;
export type BugFixStageNode = Node<{ name: string; description: string; status: string }, 'bug-fix-stage-node'>;
export type JiraIssueInputNode = Node<{ name: string; description: string }, 'jira-issue-input-node'>;
export type GateNode = Node<{ name: string; description: string; status: string }, 'gate-node'>;
export type ExternalAgentNode = Node<ExternalAgentNodeData, 'external-agent-node'>;
export type AgentBuilderNodeType = Node<AgentBuilderNodeData, 'agent-builder-node'>;
export type AppNode = BuiltInNode | JsonOutputNode | BugFixStageNode | JiraIssueInputNode | GateNode | ExternalAgentNode | AgentBuilderNodeType;

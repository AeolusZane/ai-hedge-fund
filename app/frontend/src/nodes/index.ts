import { Edge, type NodeTypes } from '@xyflow/react';

import { BugFixStageNode } from './components/bug-fix-stage-node';
import { ExternalAgentNode } from './components/external-agent-node';
import { GateNode } from './components/gate-node';
import { JiraIssueInputNode } from './components/jira-issue-input-node';
import { JsonOutputNode } from './components/json-output-node';
import { type AppNode } from './types';

export * from './types';

export const initialNodes: AppNode[] = [];

export const initialEdges: Edge[] = [];

export const nodeTypes = {
  'bug-fix-stage-node': BugFixStageNode,
  'external-agent-node': ExternalAgentNode,
  'gate-node': GateNode,
  'jira-issue-input-node': JiraIssueInputNode,
  'json-output-node': JsonOutputNode,
} satisfies NodeTypes;

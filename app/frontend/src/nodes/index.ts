import { Edge, type NodeTypes } from '@xyflow/react';

import { BugFixStageNode } from './components/bug-fix-stage-node';
import { JiraIssueInputNode } from './components/jira-issue-input-node';
import { type AppNode } from './types';

export * from './types';

export const initialNodes: AppNode[] = [];

export const initialEdges: Edge[] = [];

export const nodeTypes = {
  'bug-fix-stage-node': BugFixStageNode,
  'jira-issue-input-node': JiraIssueInputNode,
} satisfies NodeTypes;

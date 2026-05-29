import { Edge, type NodeTypes } from '@xyflow/react';

import { BugFixStageNode } from './components/bug-fix-stage-node';
import { JiraIssueInputNode } from './components/jira-issue-input-node';
import { JsonOutputNode } from './components/json-output-node';
import { PrConfigNode } from './components/pr-config-node';
import { RepoPathInputNode } from './components/repo-path-input-node';
import { type AppNode } from './types';

export * from './types';

export const initialNodes: AppNode[] = [];

export const initialEdges: Edge[] = [];

export const nodeTypes = {
  'bug-fix-stage-node': BugFixStageNode,
  'jira-issue-input-node': JiraIssueInputNode,
  'repo-path-input-node': RepoPathInputNode,
  'pr-config-node': PrConfigNode,
  'json-output-node': JsonOutputNode,
} satisfies NodeTypes;

import { MessageItem } from '@/contexts/node-context';
import type { BuiltInNode, Node } from '@xyflow/react';

export type NodeMessage = MessageItem;

export type JsonOutputNode = Node<{ name: string; description: string; status: string }, 'json-output-node'>;
export type BugFixStageNode = Node<{ name: string; description: string; status: string }, 'bug-fix-stage-node'>;
export type JiraIssueInputNode = Node<{ name: string; description: string }, 'jira-issue-input-node'>;
export type AppNode = BuiltInNode | JsonOutputNode | BugFixStageNode | JiraIssueInputNode;

import { Brain, Code, GitPullRequest, Inbox, TestTube, Wrench } from 'lucide-react';
import { registerDomain } from '@/core/domain-registry';
import type { DomainPack } from '@/core/types/domain-pack';
import type { WorkflowTemplate } from '@/core/types/workflow-template';
import { BugFixRunDialog } from './run-dialog';

// Five-node chain. Per-stage configuration (repo path on Patch /
// Open PR, Bitbucket coords on Open PR, model on Analyze) lives
// directly on the stage tiles — no separate config input nodes.
const bugFixTemplate: WorkflowTemplate = {
  id: 'bug_fix.full',
  name: 'Bug Fix',
  description: 'Jira → Analyze → Patch → Test → Open PR',
  nodes: [
    { key: 'jira',    componentName: 'Jira Issue Input', offsetX: 0,    offsetY: 0 },
    { key: 'analyze', componentName: 'Analyze',          offsetX: 320,  offsetY: 0 },
    { key: 'patch',   componentName: 'Patch',            offsetX: 640,  offsetY: 0 },
    { key: 'test',    componentName: 'Test',             offsetX: 960,  offsetY: 0 },
    { key: 'open_pr', componentName: 'Open PR',          offsetX: 1280, offsetY: 0 },
  ],
  edges: [
    { source: 'jira',    target: 'analyze' },
    { source: 'analyze', target: 'patch'   },
    { source: 'patch',   target: 'test'    },
    { source: 'test',    target: 'open_pr' },
  ],
};

const bugFixDomain: DomainPack = {
  id: 'bug_fix',
  name: 'Bug Fix',
  description: 'Jira → patch → PR',
  icon: Wrench,
  nodeTypes: [],
  getComponentGroups: async () => [
    {
      name: 'Inputs',
      icon: Inbox,
      iconColor: 'text-blue-500',
      items: [{ name: 'Jira Issue Input', icon: Inbox }],
    },
    {
      name: 'Bug Fix Stages',
      icon: Wrench,
      iconColor: 'text-amber-500',
      items: [
        { name: 'Analyze', icon: Brain },
        { name: 'Patch', icon: Code },
        { name: 'Test', icon: TestTube },
        { name: 'Open PR', icon: GitPullRequest },
      ],
    },
  ],
  RunDialog: BugFixRunDialog,
  templates: [bugFixTemplate],
};

registerDomain(bugFixDomain);

export { bugFixDomain };

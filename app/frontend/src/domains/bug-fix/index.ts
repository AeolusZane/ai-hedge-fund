import { Brain, Code, FolderGit2, GitPullRequest, Inbox, TestTube, Wrench } from 'lucide-react';
// Fetch Jira merged into Jira Issue Input — no separate Inbox tile under
// Stages. Inbox icon is still used for the input tile in the Inputs group.
import { registerDomain } from '@/core/domain-registry';
import type { DomainPack } from '@/core/types/domain-pack';
import type { WorkflowTemplate } from '@/core/types/workflow-template';
import { BugFixRunDialog } from './run-dialog';

// Layout: two horizontal rows. Inputs across the top; stages chained
// left-to-right along the bottom. Connections fan from the inputs into
// the stage they belong to so the topological executor populates state
// in the right order.
const bugFixTemplate: WorkflowTemplate = {
  id: 'bug_fix.full',
  name: 'Bug Fix',
  description: 'Jira → Analyze → Patch → Test → Open PR (full chain)',
  nodes: [
    { key: 'jira',     componentName: 'Jira Issue Input', offsetX: 0,    offsetY: 0   },
    { key: 'repo',     componentName: 'Repo Path Input',  offsetX: 320,  offsetY: 0   },
    { key: 'pr_cfg',   componentName: 'PR Config',        offsetX: 960,  offsetY: 0   },
    { key: 'analyze',  componentName: 'Analyze',          offsetX: 0,    offsetY: 260 },
    { key: 'patch',    componentName: 'Patch',            offsetX: 320,  offsetY: 260 },
    { key: 'test',     componentName: 'Test',             offsetX: 640,  offsetY: 260 },
    { key: 'open_pr',  componentName: 'Open PR',          offsetX: 960,  offsetY: 260 },
  ],
  edges: [
    { source: 'jira',    target: 'analyze' },
    { source: 'analyze', target: 'patch'   },
    { source: 'repo',    target: 'patch'   },
    { source: 'patch',   target: 'test'    },
    { source: 'test',    target: 'open_pr' },
    { source: 'pr_cfg',  target: 'open_pr' },
  ],
};

// Phase E1: the canvas can host bug-fix stage tiles, but the Run button still
// drives execution through the RunDialog. A later phase will read the
// canvas graph and post graph_nodes/edges to /workflows/bug_fix/run.
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
      items: [
        { name: 'Jira Issue Input', icon: Inbox },
        { name: 'Repo Path Input', icon: FolderGit2 },
        { name: 'PR Config', icon: GitPullRequest },
      ],
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

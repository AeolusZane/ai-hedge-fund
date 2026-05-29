import { Brain, Code, GitPullRequest, Inbox, TestTube, Wrench } from 'lucide-react';
// Fetch Jira merged into Jira Issue Input — no separate Inbox tile under
// Stages. Inbox icon is still used for the input tile in the Inputs group.
import { registerDomain } from '@/core/domain-registry';
import type { DomainPack } from '@/core/types/domain-pack';
import { BugFixRunDialog } from './run-dialog';

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
};

registerDomain(bugFixDomain);

export { bugFixDomain };

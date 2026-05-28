import { Wrench } from 'lucide-react';
import { registerDomain } from '@/core/domain-registry';
import type { DomainPack } from '@/core/types/domain-pack';
import { BugFixRunDialog } from './run-dialog';

const bugFixDomain: DomainPack = {
  id: 'bug_fix',
  name: 'Bug Fix',
  description: 'Jira → patch → PR',
  icon: Wrench,
  nodeTypes: [],
  // No draggable components yet — the palette shows its empty state and the
  // user drives runs entirely through the RunDialog.
  getComponentGroups: async () => [],
  RunDialog: BugFixRunDialog,
};

registerDomain(bugFixDomain);

export { bugFixDomain };

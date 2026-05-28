import { Wrench } from 'lucide-react';
import { registerDomain } from '@/core/domain-registry';
import type { DomainPack } from '@/core/types/domain-pack';

// Stub domain pack used to prove the multi-domain plumbing. The backend
// executor (app/backend/domains/bug_fix) simulates a Jira-bug fix flow;
// here we only contribute a switcher entry. RunForm/ResultView land in
// a later phase when the generic run experience is built.
const NoopComponent = () => null;

const bugFixDomain: DomainPack = {
  id: 'bug_fix',
  name: 'Bug Fix',
  description: 'Jira → patch → PR (stub)',
  icon: Wrench,
  nodeTypes: [],
  componentGroups: [],
  RunForm: NoopComponent,
  ResultView: NoopComponent,
};

registerDomain(bugFixDomain);

export { bugFixDomain };

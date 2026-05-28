import { TrendingUp } from 'lucide-react';
import { registerDomain } from '@/core/domain-registry';
import type { DomainPack } from '@/core/types/domain-pack';
import { getComponentGroups as getFinanceComponentGroups } from '@/data/sidebar-components';

// The finance pack still re-uses the shared frontend tree (`data/`, `nodes/`)
// today. Node types and the run/result UIs will move under this pack in the
// physical-migration phase; for now we just point the platform at the
// existing finance palette via `getComponentGroups`.
const NoopComponent = () => null;

const financeDomain: DomainPack = {
  id: 'finance',
  name: 'Hedge Fund',
  description: 'Multi-analyst stock trading workflow',
  icon: TrendingUp,
  nodeTypes: [],
  getComponentGroups: getFinanceComponentGroups,
  RunForm: NoopComponent,
  ResultView: NoopComponent,
};

registerDomain(financeDomain);

export { financeDomain };

import { TrendingUp } from 'lucide-react';
import { registerDomain } from '@/core/domain-registry';
import type { DomainPack } from '@/core/types/domain-pack';
import { getComponentGroups as getFinanceComponentGroups } from '@/data/sidebar-components';

// The finance pack still re-uses the shared frontend tree (`data/`, `nodes/`)
// today. Node types will move under this pack in the physical-migration
// phase; running stays canvas-driven so no RunDialog is provided.
const financeDomain: DomainPack = {
  id: 'finance',
  name: 'Hedge Fund',
  description: 'Multi-analyst stock trading workflow',
  icon: TrendingUp,
  nodeTypes: [],
  getComponentGroups: getFinanceComponentGroups,
};

registerDomain(financeDomain);

export { financeDomain };

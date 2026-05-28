import { TrendingUp } from 'lucide-react';
import { registerDomain } from '@/core/domain-registry';
import type { DomainPack } from '@/core/types/domain-pack';

// Phase-5 stub. The real node types, run form, and result view still live
// in the shared frontend tree today and will be relocated into this pack in
// the next phase. We register a thin descriptor now so the platform's domain
// switcher has something to point at and downstream code can resolve
// `domainRegistry.get('finance')`.
const NoopComponent = () => null;

const financeDomain: DomainPack = {
  id: 'finance',
  name: 'Hedge Fund',
  description: 'Multi-analyst stock trading workflow',
  icon: TrendingUp,
  nodeTypes: [],
  componentGroups: [],
  RunForm: NoopComponent,
  ResultView: NoopComponent,
};

registerDomain(financeDomain);

export { financeDomain };

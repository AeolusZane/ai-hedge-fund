import { createContext, ReactNode, useContext, useMemo, useState } from 'react';
import { domainRegistry } from '@/core/domain-registry';
import type { DomainPack } from '@/core/types/domain-pack';

interface DomainContextValue {
  /** All DomainPacks currently registered (snapshot at provider mount). */
  available: DomainPack[];
  /** The active domain pack — never null while a domain is registered. */
  current: DomainPack | null;
  /** Switch to another domain by id. No-op if id is not registered. */
  setCurrentDomain: (id: string) => void;
}

const DomainContext = createContext<DomainContextValue | null>(null);

export function DomainProvider({ children }: { children: ReactNode }) {
  // Snapshot the registry once. Domains register at module import time, so
  // anything that wants to appear in the switcher must be imported before
  // the app mounts.
  const available = useMemo(() => domainRegistry.list(), []);
  const [currentId, setCurrentId] = useState<string | null>(
    available[0]?.id ?? null
  );

  const value = useMemo<DomainContextValue>(() => {
    const current = currentId ? domainRegistry.get(currentId) ?? null : null;
    return {
      available,
      current,
      setCurrentDomain: (id: string) => {
        if (domainRegistry.get(id)) {
          setCurrentId(id);
        }
      },
    };
  }, [available, currentId]);

  return <DomainContext.Provider value={value}>{children}</DomainContext.Provider>;
}

export function useDomain(): DomainContextValue {
  const ctx = useContext(DomainContext);
  if (!ctx) {
    throw new Error('useDomain must be used within a DomainProvider');
  }
  return ctx;
}

import type { DomainPack } from './types/domain-pack';

/**
 * Frontend-side registry of available DomainPacks.
 *
 * Each domain entry calls `registerDomain(pack)` at import time. The platform
 * shell asks the registry for the currently active domain and falls back to
 * the first registered one when no explicit choice has been made.
 */
class DomainRegistry {
  private packs = new Map<string, DomainPack>();

  register(pack: DomainPack): void {
    if (this.packs.has(pack.id)) {
      throw new Error(`DomainPack '${pack.id}' is already registered`);
    }
    this.packs.set(pack.id, pack);
  }

  get(id: string): DomainPack | undefined {
    return this.packs.get(id);
  }

  list(): DomainPack[] {
    return Array.from(this.packs.values());
  }
}

export const domainRegistry = new DomainRegistry();

/** Convenience re-export so domain packs don't need to know about the singleton. */
export function registerDomain(pack: DomainPack): void {
  domainRegistry.register(pack);
}

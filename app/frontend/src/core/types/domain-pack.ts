import type { ComponentType } from 'react';
import type { ComponentGroup } from './component-group';

/**
 * Static description of a workflow domain that the platform can host.
 *
 * The platform shell stays domain-agnostic — it renders the canvas, the
 * Flow list, the History tab, etc. — and asks the active DomainPack for
 * whatever is domain-specific: which nodes can be dropped onto the canvas,
 * what shape the "start run" form takes, how to render the result payload.
 */
export interface DomainPack {
  /** Stable id, used both as the backend executor key and as a URL segment. */
  id: string;

  /** Human-readable name shown in the domain switcher. */
  name: string;

  /** One-line description for the domain switcher tooltip. */
  description?: string;

  /** Optional icon component for the switcher. */
  icon?: ComponentType<{ className?: string }>;

  /**
   * React Flow node-type registrations.
   * The platform merges these into ReactFlow's `nodeTypes` map at mount.
   * Today this is reserved for the upcoming physical-migration phase;
   * the current finance pack still registers its node types globally
   * through `nodes/index.ts`.
   */
  nodeTypes: DomainNodeType[];

  /**
   * Resolves the groups shown in the right-side palette for this domain.
   * Returning a Promise lets a domain hit its own backend (e.g. finance
   * fetches the analyst list from /hedge-fund/agents). Returning `[]`
   * causes the palette to show its empty state.
   */
  getComponentGroups: () => Promise<ComponentGroup[]>;

  /**
   * Optional self-contained run UI. When present, the platform exposes a
   * Run button next to the domain switcher that opens this dialog. The
   * dialog owns its own form, submission, SSE consumption, and result
   * display — domains that drive runs via the canvas (e.g. finance) can
   * leave this undefined.
   */
  RunDialog?: ComponentType<DomainRunDialogProps>;
}

export interface DomainNodeType {
  /** Matches React Flow's node `type` field. */
  id: string;
  /** The React component that renders the node body. */
  component: ComponentType<any>;
  /** Optional default data merged when the node is dropped onto the canvas. */
  defaultData?: Record<string, unknown>;
}

export interface DomainRunDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

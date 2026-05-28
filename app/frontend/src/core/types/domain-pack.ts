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
   * Form rendered when the user clicks Run. Receives a callback that
   * should be invoked with the domain-specific request payload; the
   * platform attaches `flow_id`, `graph_nodes`, `graph_edges`, etc.
   */
  RunForm: ComponentType<DomainRunFormProps>;

  /**
   * Renderer for a completed run's `results` blob. Used by the History
   * tab when expanding a row, and by the Output tab while streaming.
   */
  ResultView: ComponentType<DomainResultViewProps>;
}

export interface DomainNodeType {
  /** Matches React Flow's node `type` field. */
  id: string;
  /** The React component that renders the node body. */
  component: ComponentType<any>;
  /** Optional default data merged when the node is dropped onto the canvas. */
  defaultData?: Record<string, unknown>;
}

export interface DomainComponentGroup {
  id: string;
  label: string;
  /** Ids of DomainNodeType entries shown under this group. */
  nodeTypeIds: string[];
}

export interface DomainRunFormProps {
  /** Called by the form when the user submits — payload is forwarded to
   *  the backend executor for this domain. */
  onSubmit: (payload: Record<string, unknown>) => void;
  /** Whether a run is already in flight, so the form can disable submit. */
  isRunning: boolean;
}

export interface DomainResultViewProps {
  /** The `results` blob produced by the backend executor. */
  result: Record<string, unknown>;
}

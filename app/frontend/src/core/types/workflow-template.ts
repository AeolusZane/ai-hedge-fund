/**
 * Domain-contributed workflow template — a pre-wired set of canvas
 * nodes plus the edges between them. Clicking a template in the right
 * palette spawns the whole graph at the viewport centre.
 */
export interface WorkflowTemplate {
  /** Stable id, used as the React key in the dropdown. */
  id: string;
  /** Human-readable label shown in the dropdown. */
  name: string;
  /** One-line description shown under the name. */
  description?: string;
  nodes: WorkflowTemplateNode[];
  edges: WorkflowTemplateEdge[];
}

export interface WorkflowTemplateNode {
  /** Reference key used by edges below — not the React Flow node id. */
  key: string;
  /** Component name registered in `data/node-mappings.ts` (e.g. "Analyze"). */
  componentName: string;
  /** Offset from the viewport centre when the template lands on canvas. */
  offsetX: number;
  offsetY: number;
  /** Optional initial useNodeState seed for the new node. */
  state?: Record<string, unknown>;
}

export interface WorkflowTemplateEdge {
  /** Template node `key` of the source. */
  source: string;
  /** Template node `key` of the target. */
  target: string;
}

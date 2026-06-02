import { type Edge, type Node, getConnectedEdges } from '@xyflow/react';

export type NodeStatus = 'IDLE' | 'IN_PROGRESS' | 'COMPLETE' | 'ERROR' | 'PAUSED';

/** Rich run-time info for a node — used by the observability layer. */
export interface NodeRunInfo {
  status: NodeStatus;
  /** 0–100 progress percentage (only meaningful when IN_PROGRESS). */
  progress?: number;
  /** Timestamp (ms) when this stage started. */
  startedAt?: number;
  /** Timestamp (ms) when this stage completed. */
  completedAt?: number;
  /** One-line output summary (e.g. "1 MEDIUM: token in localStorage"). */
  outputSummary?: string;
}

/** Derive elapsed seconds from start/end timestamps. */
export function elapsedSeconds(info: NodeRunInfo): number | null {
  if (!info.startedAt) return null;
  const end = info.completedAt ?? Date.now();
  return Math.round((end - info.startedAt) / 1000);
}

/**
 * Returns the appropriate background color class based on node status
 */
export function getStatusColor(status: NodeStatus): string {
  switch (status) {
    case 'IN_PROGRESS':
      return 'text-amber-500 dark:text-amber-400';
    case 'COMPLETE':
      return 'text-green-500 dark:text-green-400';
    case 'ERROR':
      return 'text-red-500 dark:text-red-400';
    case 'PAUSED':
      return 'text-amber-500 dark:text-amber-400';
    default:
      return 'text-muted-foreground';
  }
}

/** Background / fill color for status bars and badges. */
export function getStatusBg(status: NodeStatus): string {
  switch (status) {
    case 'IN_PROGRESS':
      return 'bg-amber-500 dark:bg-amber-400';
    case 'COMPLETE':
      return 'bg-green-500 dark:bg-green-400';
    case 'ERROR':
      return 'bg-red-500 dark:bg-red-400';
    case 'PAUSED':
      return 'bg-amber-500 dark:bg-amber-400';
    default:
      return 'bg-muted';
  }
}

/**
 * Finds all nodes that are part of a complete path from a start node to an end node
 * @param params - Object containing parameters
 * @param params.startNodeId - The ID of the starting node
 * @param params.endNodeId - The ID of the end/target node
 * @param params.nodes - All nodes in the flow
 * @param params.edges - All edges in the flow
 * @returns A Set of node IDs that are part of a complete path
 */
export function getNodesInCompletePaths({
  startNodeId,
  endNodeId,
  nodes,
  edges
}: {
  startNodeId: string;
  endNodeId: string;
  nodes: Node[];
  edges: Edge[];
}): Set<string> {
  const connectedEdges = getConnectedEdges(nodes, edges);
  const selectedAgents = new Set<string>();
  
  // Helper function to find all paths from start to end
  const findCompletePaths = (
    currentNode: string,
    visited: Set<string>,
    currentPath: string[]
  ) => {
    // Add current node to visited and current path
    visited.add(currentNode);
    currentPath.push(currentNode);
    
    // If we've reached the end node, we've found a complete path
    if (currentNode === endNodeId) {
      // Add all nodes in this path to selectedAgents
      currentPath.forEach(node => selectedAgents.add(node));
      visited.delete(currentNode);
      currentPath.pop();
      return;
    }
    
    // Find all edges where current node is the source
    const outgoingEdges = connectedEdges.filter(edge => edge.source === currentNode);
    
    // Explore each outgoing edge
    for (const edge of outgoingEdges) {
      if (!visited.has(edge.target)) {
        findCompletePaths(edge.target, visited, currentPath);
      }
    }
    
    // Backtrack
    visited.delete(currentNode);
    currentPath.pop();
  };
  
  // Start the path finding from the start node
  findCompletePaths(startNodeId, new Set<string>(), []);
  
  return selectedAgents;
}

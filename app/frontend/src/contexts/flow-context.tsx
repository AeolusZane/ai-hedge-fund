import { useDomain } from '@/core/contexts/domain-context';
import type { WorkflowTemplate } from '@/core/types/workflow-template';
import { getNodeTypeDefinition } from '@/data/node-mappings';
import { flowConnectionManager } from '@/hooks/use-flow-connection';
import { clearAllNodeStates, getAllNodeStates, setNodeInternalState, setCurrentFlowId as setNodeStateFlowId } from '@/hooks/use-node-state';
import { switchFlowContext as switchOutputContext } from '@/domains/bug-fix/node-output-store';
import { switchHistoryContext } from '@/domains/bug-fix/run-history-store';
import { flowService } from '@/services/flow-service';
import { Flow } from '@/types/flow';
import { MarkerType, ReactFlowInstance, useReactFlow, XYPosition } from '@xyflow/react';
import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from 'react';

interface FlowContextType {
  addComponentToFlow: (componentName: string) => Promise<void>;
  addTemplateToFlow: (template: WorkflowTemplate) => Promise<void>;
  saveCurrentFlow: (name?: string, description?: string) => Promise<Flow | null>;
  loadFlow: (flow: Flow) => Promise<void>;
  createNewFlow: () => Promise<void>;
  currentFlowId: number | null;
  currentFlowName: string;
  isUnsaved: boolean;
  reactFlowInstance: ReactFlowInstance;
}

const FlowContext = createContext<FlowContextType | null>(null);

export function useFlowContext() {
  const context = useContext(FlowContext);
  if (!context) {
    throw new Error('useFlowContext must be used within a FlowProvider');
  }
  return context;
}

interface FlowProviderProps {
  children: ReactNode;
}

export function FlowProvider({ children }: FlowProviderProps) {
  const reactFlowInstance = useReactFlow();
  const { current: currentDomain } = useDomain();
  const [currentFlowId, setCurrentFlowId] = useState<number | null>(null);
  const [currentFlowName, setCurrentFlowName] = useState('Untitled Flow');
  const [isUnsaved, setIsUnsaved] = useState(false);

  // Sync flowId to persisted stores so they hydrate on tab switch / refresh
  useEffect(() => {
    const idStr = currentFlowId?.toString() ?? null;
    switchOutputContext(idStr);
    switchHistoryContext(idStr);
  }, [currentFlowId]);

  // Calculate viewport center position with optional randomness
  const getViewportPosition = useCallback((addRandomness = false): XYPosition => {
    let position: XYPosition = { x: 0, y: 0 }; // Default position
    
    try {
      const { zoom, x, y } = reactFlowInstance.getViewport();
      
      // Get the React Flow container dimensions instead of window dimensions
      const flowContainer = document.querySelector('.react-flow__viewport')?.parentElement;
      const containerWidth = flowContainer?.clientWidth || window.innerWidth;
      const containerHeight = flowContainer?.clientHeight || window.innerHeight;
      
      position = {
        x: (containerWidth / 2 - x) / zoom,
        y: (containerHeight / 2 - y) / zoom,
      };
    } catch (err) {
      console.warn('Could not get viewport', err);
    }
    
    if (addRandomness) {
      position.x += Math.random() * 300;
      position.y = 0;
    }
    
    return position;
  }, [reactFlowInstance]);

  // Mark flow as unsaved when changes are made
  const markAsUnsaved = useCallback(() => {
    setIsUnsaved(true);
  }, []);

  // Save current flow
  const saveCurrentFlow = useCallback(async (name?: string, description?: string): Promise<Flow | null> => {
    try {
      const nodes = reactFlowInstance.getNodes();
      const edges = reactFlowInstance.getEdges();
      const viewport = reactFlowInstance.getViewport();
      
      // Collect all node internal states (from use-node-state)
      const nodeStates = getAllNodeStates();
      const nodeInternalStates = Object.fromEntries(nodeStates);

      // Create structured data - nodeContextData will be added by enhanced save functions
      const data = {
        nodeStates: nodeInternalStates,  // use-node-state data
        // nodeContextData will be added separately by enhanced save functions
      };

      if (currentFlowId) {
        // Update existing flow
        const updatedFlow = await flowService.updateFlow(currentFlowId, {
          name: name || currentFlowName,
          description,
          nodes,
          edges,
          viewport,
          data,
        });
        setCurrentFlowName(updatedFlow.name);
        setIsUnsaved(false);
        // Remember this flow as the last selected
        localStorage.setItem('lastSelectedFlowId', updatedFlow.id.toString());
        // Ensure the flow ID is set for node state isolation
        setNodeStateFlowId(updatedFlow.id.toString());
        return updatedFlow;
      } else {
        // Create new flow under the currently active domain so the
        // sidebar listing and tabs filter correctly when switching.
        const newFlow = await flowService.createFlow({
          name: name || currentFlowName,
          description,
          nodes,
          edges,
          viewport,
          data,
          domain: currentDomain?.id,
        });
        setCurrentFlowId(newFlow.id);
        setCurrentFlowName(newFlow.name);
        setIsUnsaved(false);
        // Remember this flow as the last selected
        localStorage.setItem('lastSelectedFlowId', newFlow.id.toString());
        // Set the flow ID for node state isolation
        setNodeStateFlowId(newFlow.id.toString());
        return newFlow;
      }
    } catch (error) {
      console.error('Failed to save flow:', error);
      return null;
    }
  }, [reactFlowInstance, currentFlowId, currentFlowName, currentDomain]);

  // Load a flow
  const loadFlow = useCallback(async (flow: Flow) => {
    try {
      // CRITICAL: Set the current flow ID FIRST, before rendering nodes
      // This ensures useNodeState hooks initialize with the correct flow ID
      setNodeStateFlowId(flow.id.toString());
      setCurrentFlowId(flow.id);
      setCurrentFlowName(flow.name);
      
      // DO NOT clear configuration state when loading flows - useNodeState handles flow isolation automatically
      // Only restore additional internal states if they exist in the flow data
      if (flow.data) {
        // Handle backward compatibility - data might be direct nodeStates or structured data
        const dataToRestore = flow.data.nodeStates || flow.data;
        
        if (dataToRestore) {
          Object.entries(dataToRestore).forEach(([nodeId, nodeState]) => {
            setNodeInternalState(nodeId, nodeState as Record<string, any>);
          });
        }
        
        // nodeContextData restoration will be handled by enhanced load functions
      }
      
      // Now render the nodes - useNodeState hooks will initialize with correct flow ID
      reactFlowInstance.setNodes(flow.nodes || []);
      reactFlowInstance.setEdges(flow.edges || []);
      
      if (flow.viewport) {
        reactFlowInstance.setViewport(flow.viewport);
      } else {
        // Fit view if no viewport data
        setTimeout(() => {
          reactFlowInstance.fitView();
        }, 100);
      }

      setIsUnsaved(false);
      
      // Remember this flow as the last selected
      localStorage.setItem('lastSelectedFlowId', flow.id.toString());

      // IMPORTANT: Allow components to mount first, then recover connection state
      // This ensures useFlowConnection hooks are initialized before recovery
      setTimeout(() => {
        // Check if this flow has any stale processing states and recover them
        const connection = flowConnectionManager.getConnection(flow.id.toString());
        if (connection.state === 'idle') {
          // No active connection, so any IN_PROGRESS states are stale and should be reset
          console.log(`Flow ${flow.id} loaded - checking for stale connection states`);
        }
      }, 100);
    } catch (error) {
      console.error('Failed to load flow:', error);
    }
  }, [reactFlowInstance]);

  // Create a new flow
  const createNewFlow = useCallback(async () => {
    try {
      // CRITICAL: Reset flow ID FIRST, before clearing nodes
      setNodeStateFlowId(null);
      setCurrentFlowId(null);
      setCurrentFlowName('Untitled Flow');
      
      // Clear all node states for the current flow
      clearAllNodeStates();
      
      // Clear the React Flow canvas
      reactFlowInstance.setNodes([]);
      reactFlowInstance.setEdges([]);
      reactFlowInstance.setViewport({ x: 0, y: 0, zoom: 1 });

      setIsUnsaved(false);

      // Clear any active connections when creating a new flow
      // Note: We don't have a current flow ID to clear, so this is mainly cleanup
      console.log('Created new flow - any previous connections should be cleaned up');
    } catch (error) {
      console.error('Failed to create new flow:', error);
    }
  }, [reactFlowInstance]);

  // Add a single node to the flow
  const addSingleNodeToFlow = useCallback(async (componentName: string) => {
    try {
      const nodeTypeDefinition = await getNodeTypeDefinition(componentName);
      if (!nodeTypeDefinition) {
        console.warn(`No node type definition found for component: ${componentName}`);
        return;
      }

      const position = getViewportPosition(false);
      const newNode = nodeTypeDefinition.createNode(position);
      reactFlowInstance.setNodes((nodes) => [...nodes, newNode]);
      markAsUnsaved();
    } catch (error) {
      console.error(`Failed to add component ${componentName} to flow:`, error);
    }
  }, [reactFlowInstance, getViewportPosition, markAsUnsaved]);

  // Multi-node grouping was a finance-only convenience; in the coding
  // branch every palette item maps to a single canvas node.
  const addComponentToFlow = useCallback(async (componentName: string) => {
    await addSingleNodeToFlow(componentName);
  }, [addSingleNodeToFlow]);

  // Drop a multi-node template onto the canvas. Positions are relative
  // to the viewport centre; edges connect template-node keys to the
  // actual React Flow ids we just generated.
  const addTemplateToFlow = useCallback(async (template: WorkflowTemplate) => {
    if (!template.nodes.length) return;
    const basePosition = getViewportPosition(false);

    const keyToId = new Map<string, string>();
    const created: any[] = [];
    for (const tn of template.nodes) {
      const def = await getNodeTypeDefinition(tn.componentName);
      if (!def) {
        console.warn(`No node type definition for "${tn.componentName}" in template "${template.id}"`);
        continue;
      }
      const node = def.createNode({
        x: basePosition.x + tn.offsetX,
        y: basePosition.y + tn.offsetY,
      });
      keyToId.set(tn.key, node.id);
      if (tn.state) setNodeInternalState(node.id, tn.state);
      created.push(node);
    }

    const newEdges = template.edges
      .map((e) => {
        const source = keyToId.get(e.source);
        const target = keyToId.get(e.target);
        if (!source || !target) return null;
        return {
          id: `${source}-${target}`,
          source,
          target,
          markerEnd: { type: MarkerType.ArrowClosed },
        };
      })
      .filter((e): e is NonNullable<typeof e> => e !== null);

    reactFlowInstance.setNodes((nodes) => [...nodes, ...created]);
    reactFlowInstance.setEdges((edges) => [...edges, ...newEdges]);
    markAsUnsaved();

    // Pan + zoom so the template is on-screen.
    setTimeout(() => {
      reactFlowInstance.fitView({ padding: 0.2, duration: 500 });
    }, 100);
  }, [reactFlowInstance, getViewportPosition, markAsUnsaved]);

  const value = {
    addComponentToFlow,
    addTemplateToFlow,
    saveCurrentFlow,
    loadFlow,
    createNewFlow,
    currentFlowId,
    currentFlowName,
    isUnsaved,
    reactFlowInstance,
  };

  return (
    <FlowContext.Provider value={value}>
      {children}
    </FlowContext.Provider>
  );
} 
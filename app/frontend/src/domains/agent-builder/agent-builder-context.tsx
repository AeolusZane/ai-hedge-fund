import { createContext, useContext, useState, ReactNode, useCallback } from 'react';
import type { AgentBuilderNodeData } from '@/nodes/components/agent-builder-node';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  toolCalls?: Array<{
    name: string;
    args: Record<string, unknown>;
  }>;
}

export interface AgentConfig {
  id: string;
  name: string;
  description?: string;
  skills: Array<{ name: string; description: string }>;
  systemPrompt?: string;
  engine: 'claude-code';
}

interface AgentBuilderContextType {
  // Current active builder node
  activeNodeId: string | null;
  activeNodeData: AgentBuilderNodeData | null;
  
  // Chat state
  messages: ChatMessage[];
  isStreaming: boolean;
  
  // Agent config being built
  agentConfig: AgentConfig | null;
  
  // Actions
  openBuilderChat: (nodeId: string, nodeData: AgentBuilderNodeData) => void;
  closeBuilderChat: () => void;
  addMessage: (message: ChatMessage) => void;
  updateAgentConfig: (config: Partial<AgentConfig>) => void;
  setStreaming: (streaming: boolean) => void;
  clearMessages: () => void;
}

const AgentBuilderContext = createContext<AgentBuilderContextType | undefined>(undefined);

export function AgentBuilderProvider({ children }: { children: ReactNode }) {
  const [activeNodeId, setActiveNodeId] = useState<string | null>(null);
  const [activeNodeData, setActiveNodeData] = useState<AgentBuilderNodeData | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [agentConfig, setAgentConfig] = useState<AgentConfig | null>(null);

  const openBuilderChat = useCallback((nodeId: string, nodeData: AgentBuilderNodeData) => {
    setActiveNodeId(nodeId);
    setActiveNodeData(nodeData);
    
    // Initialize agent config if not exists
    if (!agentConfig || agentConfig.id !== nodeData.agentId) {
      setAgentConfig({
        id: nodeData.agentId,
        name: nodeData.agentName,
        description: nodeData.description,
        skills: nodeData.skills || [],
        engine: 'claude-code',
      });
    }
  }, [agentConfig]);

  const closeBuilderChat = useCallback(() => {
    setActiveNodeId(null);
    setActiveNodeData(null);
  }, []);

  const addMessage = useCallback((message: ChatMessage) => {
    setMessages(prev => [...prev, message]);
  }, []);

  const updateAgentConfig = useCallback((config: Partial<AgentConfig>) => {
    setAgentConfig(prev => prev ? { ...prev, ...config } : null);
  }, []);

  const setStreaming = useCallback((streaming: boolean) => {
    setIsStreaming(streaming);
  }, []);

  const clearMessages = useCallback(() => {
    setMessages([]);
  }, []);

  return (
    <AgentBuilderContext.Provider
      value={{
        activeNodeId,
        activeNodeData,
        messages,
        isStreaming,
        agentConfig,
        openBuilderChat,
        closeBuilderChat,
        addMessage,
        updateAgentConfig,
        setStreaming,
        clearMessages,
      }}
    >
      {children}
    </AgentBuilderContext.Provider>
  );
}

export function useAgentBuilder() {
  const context = useContext(AgentBuilderContext);
  if (!context) {
    throw new Error('useAgentBuilder must be used within AgentBuilderProvider');
  }
  return context;
}

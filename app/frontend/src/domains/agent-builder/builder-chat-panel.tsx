import { useState, useRef, useEffect } from 'react';
import { Send, X, Sparkles, Bot, User, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useAgentBuilder, type ChatMessage } from './agent-builder-context';
import { cn } from '@/lib/utils';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export function BuilderChatPanel() {
  const {
    activeNodeId,
    activeNodeData,
    messages,
    isStreaming,
    agentConfig,
    addMessage,
    updateAgentConfig,
    setStreaming,
    closeBuilderChat,
    clearMessages,
  } = useAgentBuilder();

  const [inputValue, setInputValue] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  const handleSend = async () => {
    if (!inputValue.trim() || isStreaming || !agentConfig) return;

    const userMessage: ChatMessage = {
      id: `msg_${Date.now()}`,
      role: 'user',
      content: inputValue.trim(),
      timestamp: Date.now(),
    };

    addMessage(userMessage);
    setInputValue('');
    setStreaming(true);

    // Create assistant message placeholder
    const assistantMessageId = `msg_${Date.now()}_assistant`;
    const assistantMessage: ChatMessage = {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      timestamp: Date.now(),
      toolCalls: [],
    };
    addMessage(assistantMessage);

    // Set up abort controller
    abortControllerRef.current = new AbortController();

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/agent-builder/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          agent_id: agentConfig.id,
          agent_config: agentConfig,
          message: userMessage.content,
          conversation_history: messages.map(m => ({
            role: m.role,
            content: m.content,
          })),
        }),
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();
      let accumulatedContent = '';
      let accumulatedToolCalls: ChatMessage['toolCalls'] = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n').filter(line => line.startsWith('data: '));

        for (const line of lines) {
          const data = line.slice(6);
          if (data === '[DONE]') continue;

          try {
            const event = JSON.parse(data);

            if (event.type === 'token') {
              accumulatedContent += event.content;
              // Update the assistant message with accumulated content
              updateMessageContent(assistantMessageId, accumulatedContent, accumulatedToolCalls);
            } else if (event.type === 'tool_call') {
              accumulatedToolCalls.push({
                name: event.name,
                args: event.args,
              });
              // Handle tool calls that update agent config
              handleToolCall(event.name, event.args);
              updateMessageContent(assistantMessageId, accumulatedContent, accumulatedToolCalls);
            } else if (event.type === 'config_update') {
              updateAgentConfig(event.agent);
            } else if (event.type === 'error') {
              accumulatedContent += `\n\nError: ${event.message}`;
              updateMessageContent(assistantMessageId, accumulatedContent, accumulatedToolCalls);
            }
          } catch (e) {
            console.error('Failed to parse SSE event:', e);
          }
        }
      }
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        console.log('Request aborted');
      } else {
        console.error('Chat error:', error);
        const errorMessage: ChatMessage = {
          id: `msg_${Date.now()}_error`,
          role: 'assistant',
          content: 'Sorry, an error occurred. Please try again.',
          timestamp: Date.now(),
        };
        addMessage(errorMessage);
      }
    } finally {
      setStreaming(false);
      abortControllerRef.current = null;
    }
  };

  const updateMessageContent = (
    messageId: string,
    content: string,
    toolCalls: ChatMessage['toolCalls']
  ) => {
    // We need to update the message in place
    // This is a bit tricky with the current context setup
    // For now, we'll use a workaround by removing and re-adding
    // In production, you'd want a proper update mechanism
    const msgIndex = messages.findIndex(m => m.id === messageId);
    if (msgIndex >= 0) {
      const updatedMessages = [...messages];
      updatedMessages[msgIndex] = {
        ...updatedMessages[msgIndex],
        content,
        toolCalls,
      };
      // Direct state update would be better, but this works for now
    }
  };

  const handleToolCall = (name: string, args: Record<string, unknown>) => {
    switch (name) {
      case 'set_agent_name':
        updateAgentConfig({ name: args.name as string });
        break;
      case 'set_agent_description':
        updateAgentConfig({ description: args.description as string });
        break;
      case 'add_skill':
        if (agentConfig) {
          const newSkill = {
            name: args.name as string,
            description: args.description as string,
          };
          updateAgentConfig({
            skills: [...agentConfig.skills, newSkill],
          });
        }
        break;
      case 'set_system_prompt':
        updateAgentConfig({ systemPrompt: args.prompt as string });
        break;
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  if (!activeNodeId || !activeNodeData) {
    return null;
  }

  return (
    <div className="flex flex-col h-full bg-panel">
      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b">
        <div className="flex items-center gap-2">
          <div className="flex items-center justify-center h-8 w-8 rounded-lg bg-purple-500/20 text-purple-500">
            <Bot className="h-5 w-5" />
          </div>
          <div>
            <div className="font-semibold text-sm">{agentConfig?.name || 'New Agent'}</div>
            <div className="text-xs text-muted-foreground">Agent Builder</div>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={clearMessages}
            className="h-7 px-2 text-xs"
          >
            Clear
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={closeBuilderChat}
            className="h-7 w-7 p-0"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Agent Config Summary */}
      {agentConfig && (
        <div className="p-3 border-b bg-muted/30">
          <div className="text-xs text-muted-foreground mb-1">Current Config</div>
          <div className="flex flex-wrap gap-1">
            {agentConfig.description && (
              <Badge variant="secondary" className="text-[10px]">
                {agentConfig.description.slice(0, 30)}
                {agentConfig.description.length > 30 ? '...' : ''}
              </Badge>
            )}
            {agentConfig.skills.map(skill => (
              <Badge key={skill.name} variant="outline" className="text-[10px] text-purple-500">
                <Sparkles className="h-2.5 w-2.5 mr-0.5" />
                {skill.name}
              </Badge>
            ))}
            {agentConfig.skills.length === 0 && !agentConfig.description && (
              <span className="text-xs text-muted-foreground">No skills defined yet</span>
            )}
          </div>
        </div>
      )}

      {/* Messages */}
      <ScrollArea className="flex-1 p-3">
        <div className="space-y-4">
          {messages.length === 0 && (
            <div className="text-center text-sm text-muted-foreground py-8">
              <Sparkles className="h-8 w-8 mx-auto mb-2 text-purple-500/50" />
              <p>Start designing your agent!</p>
              <p className="text-xs mt-1">Try: "I want to build an agent that analyzes CSV data"</p>
            </div>
          )}
          {messages.map((message) => (
            <div
              key={message.id}
              className={cn(
                'flex gap-2',
                message.role === 'user' ? 'justify-end' : 'justify-start'
              )}
            >
              {message.role === 'assistant' && (
                <div className="flex-shrink-0 h-6 w-6 rounded-full bg-purple-500/20 flex items-center justify-center">
                  <Bot className="h-3.5 w-3.5 text-purple-500" />
                </div>
              )}
              <div
                className={cn(
                  'max-w-[80%] rounded-lg px-3 py-2 text-sm',
                  message.role === 'user'
                    ? 'bg-blue-500 text-white'
                    : 'bg-muted'
                )}
              >
                <div className="whitespace-pre-wrap">{message.content}</div>
                {message.toolCalls && message.toolCalls.length > 0 && (
                  <div className="mt-2 pt-2 border-t border-border/50">
                    {message.toolCalls.map((tc, i) => (
                      <div key={i} className="text-xs opacity-70 flex items-center gap-1">
                        <Sparkles className="h-3 w-3" />
                        <span>{tc.name}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
              {message.role === 'user' && (
                <div className="flex-shrink-0 h-6 w-6 rounded-full bg-blue-500/20 flex items-center justify-center">
                  <User className="h-3.5 w-3.5 text-blue-500" />
                </div>
              )}
            </div>
          ))}
          {isStreaming && messages[messages.length - 1]?.content === '' && (
            <div className="flex gap-2">
              <div className="flex-shrink-0 h-6 w-6 rounded-full bg-purple-500/20 flex items-center justify-center">
                <Bot className="h-3.5 w-3.5 text-purple-500" />
              </div>
              <div className="bg-muted rounded-lg px-3 py-2">
                <Loader2 className="h-4 w-4 animate-spin text-purple-500" />
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      </ScrollArea>

      {/* Input */}
      <div className="p-3 border-t">
        <div className="flex gap-2">
          <Input
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Describe your agent..."
            disabled={isStreaming}
            className="flex-1"
          />
          <Button
            onClick={handleSend}
            disabled={!inputValue.trim() || isStreaming}
            size="sm"
            className="h-9 w-9 p-0"
          >
            {isStreaming ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}

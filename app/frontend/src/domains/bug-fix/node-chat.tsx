import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import { Send, Loader2, Bot, User, RotateCcw } from 'lucide-react';
import { useState, useRef, useEffect, useCallback } from 'react';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  toolCalls?: Array<{ name: string; args: Record<string, unknown> }>;
}

interface NodeChatProps {
  nodeId: string;
  nodeName: string;
  nodeType: string;
  nodeConfig: Record<string, unknown>;
  errorInfo?: string;
  streamingOutput?: string;
  progressTimeline?: string;
  nodeStatus?: string;
  repoUrl?: string;
  workspacePath?: string;
  runId?: number | null;
  onConfigUpdate?: (key: string, value: string) => void;
  onRetry?: () => void;
}

export function NodeChat({
  nodeId,
  nodeName,
  nodeType,
  nodeConfig,
  errorInfo,
  streamingOutput,
  progressTimeline,
  nodeStatus,
  repoUrl,
  workspacePath,
  runId,
  onConfigUpdate,
  onRetry,
}: NodeChatProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [pendingRetry, setPendingRetry] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const messagesRef = useRef<Message[]>([]);
  messagesRef.current = messages;

  // Load persisted messages on mount
  useEffect(() => {
    if (!runId || loaded) return;
    fetch(`${API_BASE_URL}/workflows/bug_fix/chat/${runId}/${nodeId}`)
      .then(res => res.ok ? res.json() : { messages: [] })
      .then(data => {
        if (data.messages?.length > 0) {
          setMessages(data.messages);
        }
        setLoaded(true);
      })
      .catch(() => setLoaded(true));
  }, [runId, nodeId, loaded]);

  // Save messages to backend
  const saveMessages = useCallback((msgs: Message[]) => {
    if (!runId || msgs.length === 0) return;
    fetch(`${API_BASE_URL}/workflows/bug_fix/chat/${runId}/${nodeId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        messages: msgs.map(m => ({ role: m.role, content: m.content, tool_calls: m.toolCalls })),
      }),
    }).catch(() => {/* silent fail */});
  }, [runId, nodeId]);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const sendMessage = async () => {
    if (!input.trim() || isStreaming) return;

    const userMessage: Message = { role: 'user', content: input.trim() };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsStreaming(true);
    setPendingRetry(false);

    abortControllerRef.current = new AbortController();

    try {
      const response = await fetch(`${API_BASE_URL}/workflows/bug_fix/node-chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          node_id: nodeId,
          node_name: nodeName,
          node_type: nodeType,
          message: userMessage.content,
          conversation_history: messages.map(m => ({ role: m.role, content: m.content })),
          node_config: nodeConfig,
          error_info: errorInfo,
          streaming_output: streamingOutput,
          progress_timeline: progressTimeline,
          node_status: nodeStatus,
          repo_url: repoUrl,
          workspace_path: workspacePath,
        }),
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();
      let assistantContent = '';
      const toolCalls: Array<{ name: string; args: Record<string, unknown> }> = [];
      let streamDone = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done || streamDone) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const data = line.slice(6).trim();
          if (!data) continue;

          try {
            const event = JSON.parse(data);

            if (event.type === 'token') {
              assistantContent += event.content;
              setMessages(prev => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                if (last?.role === 'assistant') {
                  updated[updated.length - 1] = { ...last, content: assistantContent };
                } else {
                  updated.push({ role: 'assistant', content: assistantContent });
                }
                return updated;
              });
            } else if (event.type === 'tool_call') {
              toolCalls.push({ name: event.name, args: event.args });

              // Handle tool calls
              if (event.name === 'update_config' && onConfigUpdate) {
                const { key, value } = event.args as { key: string; value: string };
                onConfigUpdate(key, value);
              } else if (event.name === 'retry_node') {
                setPendingRetry(true);
              }
            } else if (event.type === 'error') {
              assistantContent += `\n\n[Error: ${event.message}]`;
            } else if (event.type === 'done') {
              streamDone = true;
              break;
            }
          } catch {
            // Skip malformed JSON
          }
        }
      }

      // Finalize assistant message with tool calls
      if (toolCalls.length > 0) {
        setMessages(prev => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last?.role === 'assistant') {
            updated[updated.length - 1] = { ...last, toolCalls };
          }
          return updated;
        });
      }
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: `[Error: ${(err as Error).message}]`,
        }]);
      }
    } finally {
      setIsStreaming(false);
      abortControllerRef.current = null;
      // Persist messages after each exchange
      saveMessages(messagesRef.current);
    }
  };

  const handleRetry = () => {
    if (onRetry) {
      onRetry();
      setPendingRetry(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="flex flex-col border-t" style={{ height: '320px' }}>
      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {messages.length === 0 && (
          <div className="text-xs text-muted-foreground text-center py-4">
            {nodeStatus === 'IN_PROGRESS'
              ? 'Ask me about the current progress or what I\'m working on'
              : nodeStatus === 'ERROR'
              ? 'Ask me about the error or suggest a fix'
              : 'Ask me anything about this step'}
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={cn(
            'flex gap-2 text-xs',
            msg.role === 'user' ? 'justify-end' : 'justify-start'
          )}>
            {msg.role === 'assistant' && (
              <Bot className="h-4 w-4 shrink-0 mt-0.5 text-blue-500" />
            )}
            <div className={cn(
              'rounded-lg px-3 py-2 max-w-[95%]',
              msg.role === 'user'
                ? 'bg-blue-500 text-white'
                : 'bg-muted/50 text-foreground'
            )}>
              <div className="whitespace-pre-wrap">{msg.content}</div>
              {msg.toolCalls && msg.toolCalls.length > 0 && (
                <div className="mt-2 pt-2 border-t border-border/50 space-y-1">
                  {msg.toolCalls.map((tc, j) => (
                    <div key={j} className="text-[10px] text-muted-foreground">
                      <span className="font-mono">{tc.name}</span>
                      {tc.name === 'update_config' && (
                        <span>: {String(tc.args.key)} = {String(tc.args.value)}</span>
                      )}
                      {tc.name === 'retry_node' && <span>: retry requested</span>}
                    </div>
                  ))}
                </div>
              )}
            </div>
            {msg.role === 'user' && (
              <User className="h-4 w-4 shrink-0 mt-0.5 text-blue-500" />
            )}
          </div>
        ))}
        {isStreaming && messages[messages.length - 1]?.role !== 'assistant' && (
          <div className="flex gap-2 text-xs">
            <Bot className="h-4 w-4 shrink-0 mt-0.5 text-blue-500" />
            <div className="bg-muted/50 rounded-lg px-3 py-2">
              <Loader2 className="h-3 w-3 animate-spin" />
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Retry button */}
      {pendingRetry && (
        <div className="px-4 py-2 border-t bg-green-50 dark:bg-green-950/20">
          <Button
            size="sm"
            variant="default"
            className="w-full gap-2"
            onClick={handleRetry}
          >
            <RotateCcw className="h-3 w-3" />
            Confirm Retry
          </Button>
        </div>
      )}

      {/* Input */}
      <div className="px-4 py-2 border-t flex gap-2">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            nodeStatus === 'IN_PROGRESS'
              ? 'Ask about progress or current status...'
              : nodeStatus === 'ERROR'
              ? 'Ask about the error or suggest a fix...'
              : 'Ask anything about this step...'
          }
          disabled={isStreaming}
          className="text-xs h-8"
        />
        <Button
          size="icon"
          variant="outline"
          className="h-8 w-8 shrink-0"
          onClick={sendMessage}
          disabled={!input.trim() || isStreaming}
        >
          {isStreaming ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <Send className="h-3 w-3" />
          )}
        </Button>
      </div>
    </div>
  );
}

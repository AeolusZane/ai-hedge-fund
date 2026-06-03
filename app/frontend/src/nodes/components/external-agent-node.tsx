import { type NodeProps, Handle, Position } from '@xyflow/react';
import { Bot, Play, RefreshCw, Clock, CheckCircle2, XCircle, Loader2 } from 'lucide-react';
import { useState, useEffect } from 'react';

import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { agentApi, type Agent, type AgentRun } from '@/services/agent-api';

export interface ExternalAgentNodeData {
  agentId: number;
  agentName: string;
  endpoint: string;
  schedule?: string;
  inputKeys?: string[];
  outputKeys?: string[];
  color?: string;
  lastRunStatus?: string;
  lastRunAt?: string;
}

export type ExternalAgentNode = Node<ExternalAgentNodeData, 'external-agent-node'>;

export function ExternalAgentNode({
  data,
  selected,
  id,
  isConnectable,
}: NodeProps<ExternalAgentNode>) {
  const [agent, setAgent] = useState<Agent | null>(null);
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [isTriggering, setIsTriggering] = useState(false);
  const [currentRun, setCurrentRun] = useState<AgentRun | null>(null);

  // Fetch agent details and recent runs
  useEffect(() => {
    if (data.agentId) {
      loadAgent();
      loadRuns();
    }
  }, [data.agentId]);

  // Poll for status updates when running
  useEffect(() => {
    if (currentRun && currentRun.status === 'running') {
      const interval = setInterval(async () => {
        const updatedRuns = await agentApi.getRuns(data.agentId, 1);
        if (updatedRuns.length > 0) {
          setCurrentRun(updatedRuns[0]);
          if (updatedRuns[0].status !== 'running') {
            loadRuns();
          }
        }
      }, 2000);
      return () => clearInterval(interval);
    }
  }, [currentRun, data.agentId]);

  const loadAgent = async () => {
    try {
      const a = await agentApi.get(data.agentId);
      setAgent(a);
    } catch (err) {
      console.error('Failed to load agent:', err);
    }
  };

  const loadRuns = async () => {
    try {
      const r = await agentApi.getRuns(data.agentId, 5);
      setRuns(r);
      if (r.length > 0 && r[0].status === 'running') {
        setCurrentRun(r[0]);
      } else {
        setCurrentRun(null);
      }
    } catch (err) {
      console.error('Failed to load runs:', err);
    }
  };

  const handleTrigger = async () => {
    setIsTriggering(true);
    try {
      const run = await agentApi.trigger(data.agentId);
      setCurrentRun(run);
      await loadRuns();
    } catch (err) {
      console.error('Failed to trigger agent:', err);
    } finally {
      setIsTriggering(false);
    }
  };

  const getStatusColor = (status?: string) => {
    switch (status) {
      case 'success': return 'text-green-500';
      case 'failed': return 'text-red-500';
      case 'running': return 'text-blue-500';
      case 'pending': return 'text-yellow-500';
      default: return 'text-gray-400';
    }
  };

  const getStatusIcon = (status?: string) => {
    switch (status) {
      case 'success': return <CheckCircle2 className="h-3 w-3" />;
      case 'failed': return <XCircle className="h-3 w-3" />;
      case 'running': return <Loader2 className="h-3 w-3 animate-spin" />;
      case 'pending': return <Clock className="h-3 w-3" />;
      default: return null;
    }
  };

  const formatTime = (dateStr?: string) => {
    if (!dateStr) return 'Never';
    const date = new Date(dateStr);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'Just now';
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
  };

  const nodeColor = data.color || '#6366f1';
  const isRunning = currentRun?.status === 'running';
  const progress = currentRun?.progress ?? 0;

  return (
    <div
      className={cn(
        "react-flow__node-default relative select-none cursor-pointer p-0 rounded-lg border border-node transition-all duration-200 w-72",
        !selected && "hover:border-node-hover hover:shadow-lg",
        selected && "border-node-selected shadow-xl",
        isRunning && "node-in-progress",
      )}
      data-id={id}
      data-nodeid={id}
    >
      {isRunning && <div className="animated-border-container"></div>}

      {/* Input handle */}
      <Handle
        type="target"
        position={Position.Left}
        className="w-3 h-3 rounded-full bg-blue-500 border-2 border-card absolute left-0 top-1/2 -translate-x-1/2 -translate-y-1/2 z-10"
        isConnectable={isConnectable}
      />

      <div className="overflow-hidden rounded-lg">
        <Card className="bg-node rounded-none overflow-hidden border-none">
          {/* Header */}
          <CardHeader className="p-3 bg-node flex flex-row items-center space-x-2 rounded-t-sm">
            <div
              className="flex items-center justify-center h-8 w-8 rounded-lg"
              style={{ backgroundColor: `${nodeColor}20`, color: nodeColor }}
            >
              <Bot className="h-5 w-5" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-title font-semibold text-primary truncate">
                {data.agentName}
              </div>
              <div className="text-[10px] text-muted-foreground truncate">
                {data.endpoint}
              </div>
            </div>
            {agent?.last_run_status && (
              <Badge variant="outline" className={cn("text-[10px] px-1.5", getStatusColor(agent.last_run_status))}>
                {getStatusIcon(agent.last_run_status)}
                <span className="ml-1">{agent.last_run_status}</span>
              </Badge>
            )}
          </CardHeader>

          {/* Body */}
          <CardContent className="p-3 space-y-3">
            {/* I/O Ports */}
            <div className="space-y-2">
              {data.inputKeys && data.inputKeys.length > 0 && (
                <div>
                  <div className="text-[10px] font-semibold text-blue-500 uppercase tracking-wide mb-1">
                    IN
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {data.inputKeys.map((key) => (
                      <Badge key={key} variant="secondary" className="text-[10px] px-1.5 py-0">
                        {key}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
              {data.outputKeys && data.outputKeys.length > 0 && (
                <div>
                  <div className="text-[10px] font-semibold text-green-500 uppercase tracking-wide mb-1">
                    OUT
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {data.outputKeys.map((key) => (
                      <Badge key={key} variant="secondary" className="text-[10px] px-1.5 py-0">
                        {key}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Progress bar when running */}
            {isRunning && (
              <div className="space-y-1">
                <div className="flex justify-between text-[10px] text-muted-foreground">
                  <span>{currentRun?.message || 'Running...'}</span>
                  <span>{progress}%</span>
                </div>
                <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                  <div
                    className="h-full bg-blue-500 transition-all duration-500"
                    style={{ width: `${Math.max(progress, 5)}%` }}
                  />
                </div>
              </div>
            )}

            {/* Schedule info */}
            {data.schedule && (
              <div className="flex items-center gap-1 text-[10px] text-muted-foreground">
                <Clock className="h-3 w-3" />
                <span>{data.schedule}</span>
              </div>
            )}

            {/* Last run info */}
            {agent?.last_run_at && (
              <div className="text-[10px] text-muted-foreground">
                Last run: {formatTime(agent.last_run_at)}
              </div>
            )}

            {/* Trigger button */}
            <Button
              size="sm"
              variant="outline"
              className="w-full h-7 text-xs"
              onClick={handleTrigger}
              disabled={isTriggering || isRunning}
            >
              {isTriggering ? (
                <Loader2 className="h-3 w-3 animate-spin mr-1" />
              ) : isRunning ? (
                <RefreshCw className="h-3 w-3 mr-1 animate-spin" />
              ) : (
                <Play className="h-3 w-3 mr-1" />
              )}
              {isRunning ? 'Running...' : 'Trigger'}
            </Button>
          </CardContent>
        </Card>
      </div>

      {/* Output handle */}
      <Handle
        type="source"
        position={Position.Right}
        className="w-3 h-3 rounded-full bg-green-500 border-2 border-card absolute right-0 top-1/2 translate-x-1/2 -translate-y-1/2 z-10"
        isConnectable={isConnectable}
      />
    </div>
  );
}

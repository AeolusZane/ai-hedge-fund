import { type NodeProps, Handle, Position } from '@xyflow/react';
import { Bot, Sparkles, MessageSquare } from 'lucide-react';
import { useState } from 'react';

import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { useAgentBuilder } from '@/domains/agent-builder/agent-builder-context';

export interface AgentBuilderNodeData {
  agentId: string;
  agentName: string;
  description?: string;
  skills?: Array<{ name: string; description: string }>;
  status?: 'draft' | 'building' | 'ready';
  color?: string;
}

export type AgentBuilderNode = Node<AgentBuilderNodeData, 'agent-builder-node'>;

export function AgentBuilderNode({
  data,
  selected,
  id,
  isConnectable,
}: NodeProps<AgentBuilderNode>) {
  const { openBuilderChat } = useAgentBuilder();
  const [isHovered, setIsHovered] = useState(false);

  const nodeColor = data.color || '#8b5cf6'; // Purple for builder
  const status = data.status || 'draft';
  const skills = data.skills || [];

  const getStatusBadge = () => {
    switch (status) {
      case 'building':
        return (
          <Badge variant="outline" className="text-[10px] px-1.5 text-blue-500 border-blue-500">
            <Sparkles className="h-3 w-3 mr-1 animate-pulse" />
            Building
          </Badge>
        );
      case 'ready':
        return (
          <Badge variant="outline" className="text-[10px] px-1.5 text-green-500 border-green-500">
            Ready
          </Badge>
        );
      default:
        return (
          <Badge variant="outline" className="text-[10px] px-1.5 text-gray-400">
            Draft
          </Badge>
        );
    }
  };

  const handleOpenChat = (e: React.MouseEvent) => {
    e.stopPropagation();
    openBuilderChat(id, data);
  };

  return (
    <div
      className={cn(
        "react-flow__node-default relative select-none cursor-pointer p-0 rounded-lg border border-node transition-all duration-200 w-72",
        !selected && "hover:border-node-hover hover:shadow-lg",
        selected && "border-node-selected shadow-xl",
        status === 'building' && "node-in-progress",
      )}
      data-id={id}
      data-nodeid={id}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {status === 'building' && <div className="animated-border-container"></div>}

      {/* Input handle */}
      <Handle
        type="target"
        position={Position.Left}
        className="w-3 h-3 rounded-full bg-purple-500 border-2 border-card absolute left-0 top-1/2 -translate-x-1/2 -translate-y-1/2 z-10"
        isConnectable={isConnectable}
      />

      <div className="overflow-hidden rounded-lg">
        <Card className="bg-node rounded-none overflow-hidden border-none">
          {/* Header */}
          <CardHeader className="p-3 bg-node flex flex-row items-center space-x-2 rounded-t-sm">
            <div
              className="flex items-center justify-center h-8 w-8 rounded-lg relative"
              style={{ backgroundColor: `${nodeColor}20`, color: nodeColor }}
            >
              <Bot className="h-5 w-5" />
              <Sparkles className="h-3 w-3 absolute -top-1 -right-1 text-yellow-500" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-title font-semibold text-primary truncate">
                {data.agentName}
              </div>
              <div className="text-[10px] text-muted-foreground truncate">
                Agent Builder
              </div>
            </div>
            {getStatusBadge()}
          </CardHeader>

          {/* Body */}
          <CardContent className="p-3 space-y-3">
            {/* Description */}
            {data.description && (
              <div className="text-xs text-muted-foreground line-clamp-2">
                {data.description}
              </div>
            )}

            {/* Skills */}
            {skills.length > 0 && (
              <div>
                <div className="text-[10px] font-semibold text-purple-500 uppercase tracking-wide mb-1">
                  Skills ({skills.length})
                </div>
                <div className="flex flex-wrap gap-1">
                  {skills.slice(0, 3).map((skill) => (
                    <Badge key={skill.name} variant="secondary" className="text-[10px] px-1.5 py-0">
                      {skill.name}
                    </Badge>
                  ))}
                  {skills.length > 3 && (
                    <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                      +{skills.length - 3}
                    </Badge>
                  )}
                </div>
              </div>
            )}

            {/* Chat button - appears on hover or when selected */}
            {(isHovered || selected) && (
              <Button
                size="sm"
                variant="outline"
                className="w-full h-7 text-xs"
                onClick={handleOpenChat}
              >
                <MessageSquare className="h-3 w-3 mr-1" />
                Chat to Design
              </Button>
            )}

            {/* Placeholder when not hovered */}
            {!isHovered && !selected && skills.length === 0 && !data.description && (
              <div className="text-center text-xs text-muted-foreground py-2">
                Click to start designing with AI
              </div>
            )}
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

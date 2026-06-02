import { Card, CardHeader } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { elapsedSeconds, getStatusBg, getStatusColor, type NodeRunInfo, type NodeStatus } from '@/nodes/utils';
import { Handle, Position } from '@xyflow/react';
import { Loader2, Pause, CheckCircle2, XCircle } from 'lucide-react';
import { ReactNode } from 'react';

export interface NodeShellProps {
  id: string;
  selected?: boolean;
  isConnectable?: boolean;
  icon: ReactNode;
  iconColor?: string;
  name: string;
  description?: string;
  children: ReactNode;
  hasLeftHandle?: boolean;
  hasRightHandle?: boolean;
  status?: NodeStatus;
  /** Rich run info — when provided, a status bar appears at the bottom. */
  runInfo?: NodeRunInfo;
  width?: string;
}

function StatusIcon({ status }: { status: NodeStatus }) {
  switch (status) {
    case 'IN_PROGRESS':
      return <Loader2 className="h-3 w-3 animate-spin" />;
    case 'COMPLETE':
      return <CheckCircle2 className="h-3 w-3" />;
    case 'ERROR':
      return <XCircle className="h-3 w-3" />;
    case 'PAUSED':
      return <Pause className="h-3 w-3" />;
    default:
      return null;
  }
}

export function NodeShell({
  id,
  selected,
  isConnectable,
  icon,
  iconColor,
  name,
  description,
  children,
  hasLeftHandle = true,
  hasRightHandle = true,
  status = 'IDLE',
  runInfo,
  width = 'w-64',
}: NodeShellProps) {
  const isInProgress = status === 'IN_PROGRESS';
  const isPaused = status === 'PAUSED';
  const showStatusBar = status !== 'IDLE' && runInfo;
  const elapsed = runInfo ? elapsedSeconds(runInfo) : null;
  const progress = runInfo?.progress ?? 0;

  return (
    <div
      className={cn(
        "react-flow__node-default relative select-none cursor-pointer p-0 rounded-lg border border-node transition-all duration-200",
        width,
        !selected && "hover:border-node-hover hover:shadow-lg",
        selected && "border-node-selected shadow-xl",
        isInProgress && "node-in-progress",
        isPaused && "node-in-progress",
        status === 'ERROR' && "border-red-400 dark:border-red-600",
      )}
      data-id={id}
      data-nodeid={id}
    >
      {isInProgress && (
        <div className="animated-border-container"></div>
      )}
      {hasLeftHandle && (
        <Handle
          type="target"
          position={Position.Left}
          className="w-3 h-3 rounded-full bg-gray-500 border-2 border-card absolute left-0 top-1/2 -translate-x-1/2 -translate-y-1/2 z-10 transition-all duration-200 hover:bg-gray-500 hover:w-4 hover:h-4 hover:shadow-[0_0_5px_2px_rgba(59,130,246,0.3)]"
          isConnectable={isConnectable}
        />
      )}
      <div className="overflow-hidden rounded-lg">
        <Card className="bg-node rounded-none overflow-hidden border-none">
          <CardHeader className="p-3 bg-node flex flex-row items-center space-x-2 rounded-t-sm">
            <div className={cn(
              "flex items-center justify-center h-8 w-8 rounded-lg text-primary",
              isInProgress ? "gradient-animation" : iconColor
            )}>
              {icon}
            </div>
            <div className="text-title font-semibold text-primary">
              {name || "Custom Component"}
            </div>
            {showStatusBar && (
              <div className={cn("ml-auto flex items-center gap-1 text-[10px] font-medium", getStatusColor(status))}>
                <StatusIcon status={status} />
                {elapsed !== null && `${elapsed}s`}
              </div>
            )}
          </CardHeader>
          {description && (
            <div className="px-3 py-2 text-subtitle text-primary text-left">
              {description}
            </div>
          )}
          {children}
          {/* Status bar at the bottom of the node */}
          {showStatusBar && (
            <div className="border-t border-node">
              {/* Thin progress bar */}
              {(isInProgress || isPaused) && (
                <div className="h-1 bg-muted overflow-hidden">
                  <div
                    className={cn(
                      "h-full transition-all duration-500",
                      getStatusBg(status),
                      isPaused && "animate-pulse"
                    )}
                    style={{ width: `${Math.max(progress, 8)}%` }}
                  />
                </div>
              )}
              {status === 'COMPLETE' && (
                <div className="h-1 bg-muted overflow-hidden">
                  <div className={cn("h-full", getStatusBg(status))} style={{ width: '100%' }} />
                </div>
              )}
              {status === 'ERROR' && (
                <div className="h-1 bg-muted overflow-hidden">
                  <div className={cn("h-full", getStatusBg(status))} style={{ width: '100%' }} />
                </div>
              )}
              {/* Output summary line */}
              {runInfo?.outputSummary && (
                <div className={cn(
                  "px-3 py-1.5 text-[11px] truncate",
                  getStatusColor(status)
                )}>
                  {runInfo.outputSummary}
                </div>
              )}
            </div>
          )}
        </Card>
      </div>
      {hasRightHandle && (
        <Handle
          type="source"
          position={Position.Right}
          className="w-3 h-3 rounded-full bg-gray-500 border-2 border-card absolute right-0 top-1/2 translate-x-1/2 -translate-y-1/2 z-10 transition-all duration-200 hover:bg-gray-500 hover:w-4 hover:h-4 hover:shadow-[0_0_5px_2px_rgba(59,130,246,0.3)]"
          isConnectable={isConnectable}
        />
      )}
    </div>
  );
}
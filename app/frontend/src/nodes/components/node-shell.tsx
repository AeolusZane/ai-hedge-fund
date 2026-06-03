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

  // Handle colors based on node status
  const handleColor = status === 'COMPLETE' ? 'bg-green-500' 
    : status === 'ERROR' ? 'bg-red-500'
    : isInProgress ? 'bg-amber-500'
    : 'bg-slate-400';
  const handleGlow = isInProgress ? 'shadow-[0_0_8px_3px_rgba(245,158,11,0.4)]' : '';

  return (
    <div
      className={cn(
        "react-flow__node-default relative select-none cursor-pointer p-0 rounded-lg border border-node transition-all duration-300",
        width,
        !selected && "hover:border-node-hover hover:shadow-lg",
        selected && "border-node-selected shadow-xl",
        isInProgress && "node-in-progress",
        isPaused && "node-in-progress",
        status === 'COMPLETE' && "border-green-400 dark:border-green-600 shadow-[0_0_12px_2px_rgba(34,197,94,0.2)]",
        status === 'ERROR' && "border-red-400 dark:border-red-600 shadow-[0_0_12px_2px_rgba(239,68,68,0.25)] node-error-shake",
      )}
      data-id={id}
      data-nodeid={id}
    >
      {isInProgress && (
        <div className="animated-border-container"></div>
      )}
      {status === 'COMPLETE' && (
        <div className="absolute inset-0 rounded-lg border-2 border-green-500/30 pointer-events-none"></div>
      )}
      {hasLeftHandle && (
        <Handle
          type="target"
          position={Position.Left}
          className={cn(
            "w-4 h-4 rounded-full border-2 border-card absolute left-0 top-1/2 -translate-x-1/2 -translate-y-1/2 z-10 transition-all duration-300",
            "hover:w-5 hover:h-5 hover:shadow-[0_0_12px_4px_rgba(59,130,246,0.5)]",
            handleColor,
            handleGlow
          )}
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
          className={cn(
            "w-4 h-4 rounded-full border-2 border-card absolute right-0 top-1/2 translate-x-1/2 -translate-y-1/2 z-10 transition-all duration-300",
            "hover:w-5 hover:h-5 hover:shadow-[0_0_12px_4px_rgba(59,130,246,0.5)]",
            handleColor,
            handleGlow
          )}
          isConnectable={isConnectable}
        />
      )}
    </div>
  );
}
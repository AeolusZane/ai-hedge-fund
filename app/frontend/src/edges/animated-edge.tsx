import { BaseEdge, getBezierPath, type EdgeProps, useStore } from '@xyflow/react';
import { useMemo } from 'react';
import type { NodeStatus } from '@/nodes/utils';

/**
 * AnimatedEdge — custom edge that visually responds to node states.
 *
 * Behaviours:
 * - IDLE: subtle dashed line, low opacity
 * - Source IN_PROGRESS → target: flowing dash animation (data transmitting)
 * - Both COMPLETE: solid green line (pipeline succeeded)
 * - Either ERROR: red tinted line
 * - Hover: thicker + glow
 */

const STATUS_COLORS: Record<string, string> = {
  IN_PROGRESS: '#f59e0b', // amber
  COMPLETE: '#22c55e',    // green
  ERROR: '#ef4444',       // red
  PAUSED: '#f59e0b',      // amber
  IDLE: '#94a3b8',        // slate-400
};

export function AnimatedEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  source,
  target,
  style = {},
  markerEnd,
  selected,
}: EdgeProps) {
  // Read node statuses from the React Flow store
  const sourceStatus = useStore(
    (s) => (s.nodeLookup?.get(source)?.data as any)?.status as NodeStatus | undefined
  );
  const targetStatus = useStore(
    (s) => (s.nodeLookup?.get(target)?.data as any)?.status as NodeStatus | undefined
  );

  const [edgePath] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetPosition,
    targetX,
    targetY,
  });

  const effectiveStatus = useMemo(() => {
    if (sourceStatus === 'ERROR' || targetStatus === 'ERROR') return 'ERROR';
    if (sourceStatus === 'IN_PROGRESS') return 'IN_PROGRESS';
    if (sourceStatus === 'COMPLETE' && targetStatus === 'COMPLETE') return 'COMPLETE';
    if (sourceStatus === 'COMPLETE') return 'IN_PROGRESS'; // data flowing to next
    return 'IDLE';
  }, [sourceStatus, targetStatus]);

  const color = STATUS_COLORS[effectiveStatus] || STATUS_COLORS.IDLE;
  const isActive = effectiveStatus === 'IN_PROGRESS';
  const isComplete = effectiveStatus === 'COMPLETE';
  const isError = effectiveStatus === 'ERROR';

  return (
    <>
      {/* Glow layer — only when active */}
      {isActive && (
        <BaseEdge
          id={`${id}-glow`}
          path={edgePath}
          style={{
            stroke: color,
            strokeWidth: 6,
            opacity: 0.15,
            filter: 'blur(3px)',
          }}
        />
      )}
      {/* Main edge */}
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          ...style,
          stroke: color,
          strokeWidth: selected ? 3 : isActive ? 2.5 : isComplete ? 2 : 1.5,
          strokeDasharray: isActive ? '8 4' : isComplete ? 'none' : '6 4',
          opacity: isActive || isComplete || isError ? 1 : 0.4,
          transition: 'all 0.3s ease',
          ...(isActive && {
            animation: 'edgeFlow 0.8s linear infinite',
          }),
        }}
      />
    </>
  );
}

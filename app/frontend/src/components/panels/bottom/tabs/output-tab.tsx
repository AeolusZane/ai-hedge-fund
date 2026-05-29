import { cn } from '@/lib/utils';

interface OutputTabProps {
  className?: string;
}

/**
 * Single-domain coding-branch placeholder.
 *
 * The legacy hedge-fund output renderer lived in BacktestOutput /
 * RegularOutput; both were finance-specific and have been removed. The
 * bug_fix domain surfaces its progress in the Run dialog launched from
 * the canvas, so this tab is currently informational only. Future bug
 * fix progress views (file-by-file patches, test output, etc.) will
 * land here.
 */
export function OutputTab({ className }: OutputTabProps) {
  return (
    <div className={cn('h-full overflow-y-auto font-mono text-sm', className)}>
      <div className="text-center py-8 text-muted-foreground">
        No output to display. Run a workflow from the canvas to see progress.
      </div>
    </div>
  );
}

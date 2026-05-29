import { Button } from '@/components/ui/button';
import { useDomain } from '@/core/contexts/domain-context';
import { cn } from '@/lib/utils';
import { PanelBottom, PanelLeft, PanelRight, Settings } from 'lucide-react';
import { useState } from 'react';
import { DomainSwitcher } from './domain-switcher';

interface TopBarProps {
  isLeftCollapsed: boolean;
  isRightCollapsed: boolean;
  isBottomCollapsed: boolean;
  onToggleLeft: () => void;
  onToggleRight: () => void;
  onToggleBottom: () => void;
  onSettingsClick: () => void;
}

export function TopBar({
  isLeftCollapsed,
  isRightCollapsed,
  isBottomCollapsed,
  onToggleLeft,
  onToggleRight,
  onToggleBottom,
  onSettingsClick,
}: TopBarProps) {
  const { current } = useDomain();
  const RunDialog = current?.RunDialog;
  // The dialog must stay mounted even though no top-bar button opens it
  // anymore — canvas nodes call into a module-level controller that
  // toggles `open` and starts a run.
  const [runDialogOpen, setRunDialogOpen] = useState(false);

  return (
    <div className="absolute top-0 right-0 z-40 flex items-center gap-0 py-1 px-2 bg-panel/80">
      {/* Workflow domain switcher */}
      <DomainSwitcher />

      {RunDialog && (
        <RunDialog open={runDialogOpen} onOpenChange={setRunDialogOpen} />
      )}

      {/* Divider */}
      <div className="w-px h-5 bg-ramp-grey-700 mx-1" />

      {/* Left Sidebar Toggle */}
      <Button
        variant="ghost"
        size="sm"
        onClick={onToggleLeft}
        className={cn(
          "h-8 w-8 p-0 text-muted-foreground hover:text-foreground hover:bg-ramp-grey-700 transition-colors",
          !isLeftCollapsed && "text-foreground"
        )}
        aria-label="Toggle left sidebar"
        title="Toggle Left Side Bar (⌘B)"
      >
        <PanelLeft size={16} />
      </Button>

      {/* Bottom Panel Toggle */}
      <Button
        variant="ghost"
        size="sm"
        onClick={onToggleBottom}
        className={cn(
          "h-8 w-8 p-0 text-muted-foreground hover:text-foreground hover:bg-ramp-grey-700 transition-colors",
          !isBottomCollapsed && "text-foreground"
        )}
        aria-label="Toggle bottom panel"
        title="Toggle Bottom Panel (⌘J)"
      >
        <PanelBottom size={16} />
      </Button>

      {/* Right Sidebar Toggle */}
      <Button
        variant="ghost"
        size="sm"
        onClick={onToggleRight}
        className={cn(
          "h-8 w-8 p-0 text-muted-foreground hover:text-foreground hover:bg-ramp-grey-700 transition-colors",
          !isRightCollapsed && "text-foreground"
        )}
        aria-label="Toggle right sidebar"
        title="Toggle Right Side Bar (⌘I)"
      >
        <PanelRight size={16} />
      </Button>

      {/* Divider */}
      <div className="w-px h-5 bg-ramp-grey-700 mx-1" />

      {/* Settings */}
      <Button
        variant="ghost"
        size="sm"
        onClick={onSettingsClick}
        className="h-8 w-8 p-0 text-muted-foreground hover:text-foreground hover:bg-ramp-grey-700 transition-colors"
        aria-label="Open settings"
        title="Open Settings (⌘,)"
      >
        <Settings size={16} />
      </Button>
    </div>
  );
} 
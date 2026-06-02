import { useDomain } from '@/core/contexts/domain-context';
import type { ComponentGroup } from '@/core/types/component-group';
import { useComponentGroups } from '@/hooks/use-component-groups';
import { useResizable } from '@/hooks/use-resizable';
import { cn } from '@/lib/utils';
import { ReactNode, useEffect, useState } from 'react';
import { ComponentActions } from './component-actions';
import { ComponentList } from './component-list';

interface RightSidebarProps {
  children?: ReactNode;
  isCollapsed: boolean;
  onCollapse: () => void;
  onExpand: () => void;
  onWidthChange?: (width: number) => void;
}

export function RightSidebar({
  isCollapsed,
  onWidthChange,
}: RightSidebarProps) {
  // Use our custom hooks
  const { width, isDragging, elementRef, startResize } = useResizable({
    defaultWidth: 280,
    minWidth: 200,
    maxWidth: window.innerWidth * .90,
    side: 'right',
  });
  
  // Notify parent component of width changes
  useEffect(() => {
    onWidthChange?.(width);
  }, [width, onWidthChange]);
  
  // The active domain decides which palette groups appear. Switching domain
  // re-runs the loader.
  const { current: currentDomain } = useDomain();
  const [componentGroups, setComponentGroups] = useState<ComponentGroup[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!currentDomain) {
      setComponentGroups([]);
      setIsLoading(false);
      return;
    }
    let cancelled = false;
    setIsLoading(true);
    currentDomain
      .getComponentGroups()
      .then((groups) => {
        if (!cancelled) setComponentGroups(groups);
      })
      .catch((error) => {
        console.error('Failed to load component groups:', error);
        if (!cancelled) setComponentGroups([]);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [currentDomain]);
  
  const { 
    searchQuery, 
    setSearchQuery, 
    activeItem, 
    openGroups, 
    filteredGroups,
    handleAccordionChange 
  } = useComponentGroups(componentGroups);

  return (
    <div 
      ref={elementRef}
      className={cn(
        "h-full bg-panel flex flex-col relative pt-5 border-l",
        isCollapsed ? "shadow-lg" : "",
      )}
      style={{ 
        width: `${width}px`
      }}
    >
      <ComponentActions />

      <ComponentList
        componentGroups={componentGroups}
        templates={currentDomain?.templates}
        searchQuery={searchQuery}
        isLoading={isLoading}
        openGroups={openGroups}
        filteredGroups={filteredGroups}
        activeItem={activeItem}
        onSearchChange={setSearchQuery}
        onAccordionChange={handleAccordionChange}
      />
      
      {/* Resize handle - on the left side for right sidebar */}
      {!isDragging && (
        <div 
          className="absolute top-0 left-0 h-full w-1 cursor-ew-resize transition-all duration-150 z-10"
          onMouseDown={startResize}
        />
      )}
    </div>
  );
} 
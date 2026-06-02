import { Accordion } from '@/components/ui/accordion';
import { ComponentGroup } from '@/core/types/component-group';
import type { WorkflowTemplate } from '@/core/types/workflow-template';
import { SearchBox } from '../search-box';
import { ComponentItemGroup } from './component-item-group';
import { TemplateGroup } from './template-group';

interface ComponentListProps {
  componentGroups: ComponentGroup[];
  templates?: WorkflowTemplate[];
  searchQuery: string;
  isLoading: boolean;
  openGroups: string[];
  filteredGroups: ComponentGroup[];
  activeItem: string | null;
  onSearchChange: (query: string) => void;
  onAccordionChange: (value: string[]) => void;
}

export function ComponentList({
  componentGroups,
  templates = [],
  searchQuery,
  isLoading,
  openGroups,
  filteredGroups,
  activeItem,
  onSearchChange,
  onAccordionChange,
}: ComponentListProps) {
  // Templates only show in the unfiltered view — the search box covers
  // component item names, not template names.
  const showTemplates = templates.length > 0 && searchQuery.trim() === '';
  return (
    <div className="flex-grow overflow-auto text-primary scrollbar-thin scrollbar-thumb-ramp-grey-700">
      <SearchBox 
        value={searchQuery} 
        onChange={onSearchChange}
        placeholder="Search components..."
      />
      
      {isLoading ? (
        <div className="flex items-center justify-center py-8">
          <div className="text-muted-foreground text-sm">Loading components...</div>
        </div>
      ) : (
        <Accordion
          type="multiple"
          className="w-full"
          value={openGroups}
          onValueChange={onAccordionChange}
        >
          {filteredGroups.map(group => (
            <ComponentItemGroup
              key={group.name}
              group={group}
              activeItem={activeItem}
            />
          ))}
          {showTemplates && <TemplateGroup templates={templates} />}
        </Accordion>
      )}

      {!isLoading && filteredGroups.length === 0 && (
        <div className="text-center py-8 text-muted-foreground text-sm">
          {componentGroups.length === 0 ? (
            <div className="space-y-2">
              <div>No components available</div>
              <div className="text-xs">Components will appear here when loaded</div>
            </div>
          ) : (
            'No components match your search'
          )}
        </div>
      )}
    </div>
  );
} 
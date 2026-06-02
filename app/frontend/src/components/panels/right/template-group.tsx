import ComponentItem from '@/components/panels/right/component-item';
import { AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import { useFlowContext } from '@/contexts/flow-context';
import type { WorkflowTemplate } from '@/core/types/workflow-template';
import { Sparkles } from 'lucide-react';

interface TemplateGroupProps {
  templates: WorkflowTemplate[];
}

/**
 * Accordion item that mirrors ComponentItemGroup's look but its tiles
 * drop a multi-node template onto the canvas instead of a single
 * component.
 */
export function TemplateGroup({ templates }: TemplateGroupProps) {
  const { addTemplateToFlow } = useFlowContext();

  const handleItemClick = async (template: WorkflowTemplate) => {
    try {
      await addTemplateToFlow(template);
    } catch (error) {
      console.error('Failed to add template to flow:', error);
    }
  };

  return (
    <AccordionItem value="Templates" className="border-none">
      <AccordionTrigger className="px-4 py-2 text-sm hover-bg hover:no-underline">
        <div className="flex items-center gap-2">
          <Sparkles size={16} className="text-amber-500" />
          <span className="capitalize">Templates</span>
        </div>
      </AccordionTrigger>
      <AccordionContent className="px-4">
        <div className="space-y-1">
          {templates.map((t) => (
            <ComponentItem
              key={t.id}
              icon={Sparkles}
              label={t.name}
              onClick={() => handleItemClick(t)}
            />
          ))}
        </div>
      </AccordionContent>
    </AccordionItem>
  );
}

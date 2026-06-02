import { Button } from '@/components/ui/button';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { useFlowContext } from '@/contexts/flow-context';
import { useDomain } from '@/core/contexts/domain-context';
import { cn } from '@/lib/utils';
import { ChevronDown, Sparkles } from 'lucide-react';
import { useState } from 'react';

/**
 * Dropdown above the palette search box. Lists the active DomainPack's
 * pre-wired workflow templates; clicking one calls addTemplateToFlow
 * which instantiates every node + edge on the canvas in one shot.
 */
export function TemplateMenu() {
  const { current } = useDomain();
  const { addTemplateToFlow } = useFlowContext();
  const [open, setOpen] = useState(false);

  const templates = current?.templates ?? [];
  if (templates.length === 0) return null;

  return (
    <div className="px-2 py-2 border-b">
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            className="w-full justify-between h-8 text-xs"
            title="Drop a pre-wired template onto the canvas"
          >
            <span className="flex items-center gap-2">
              <Sparkles className="h-3.5 w-3.5 text-amber-500" />
              Templates
            </span>
            <ChevronDown size={14} className="text-muted-foreground" />
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-64 p-1">
          <div className="px-2 py-1 text-[10px] uppercase tracking-wide text-muted-foreground">
            {current?.name} templates
          </div>
          {templates.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={async () => {
                await addTemplateToFlow(t);
                setOpen(false);
              }}
              className={cn(
                'flex w-full flex-col items-start gap-0.5 rounded-sm px-2 py-1.5 text-sm text-left hover:bg-accent hover:text-accent-foreground'
              )}
            >
              <div className="font-medium">{t.name}</div>
              {t.description && (
                <div className="text-[10px] text-muted-foreground">
                  {t.description}
                </div>
              )}
              <div className="text-[10px] text-muted-foreground">
                {t.nodes.length} nodes · {t.edges.length} edges
              </div>
            </button>
          ))}
        </PopoverContent>
      </Popover>
    </div>
  );
}

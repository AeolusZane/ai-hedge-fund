import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { useDomain } from '@/core/contexts/domain-context';
import { cn } from '@/lib/utils';
import { Check, ChevronDown } from 'lucide-react';
import { useState } from 'react';

export function DomainSwitcher() {
  const { available, current, setCurrentDomain } = useDomain();
  const [open, setOpen] = useState(false);

  if (!current) return null;

  const Icon = current.icon;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className="h-8 gap-2 px-2 text-foreground hover:bg-ramp-grey-700"
          title="Switch workflow domain"
        >
          {Icon && <Icon className="h-4 w-4" />}
          <span className="text-sm">{current.name}</span>
          <ChevronDown size={14} className="text-muted-foreground" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-64 p-1">
        <div className="px-2 py-1 text-xs uppercase tracking-wide text-muted-foreground">
          Workflow domain
        </div>
        {available.map((pack) => {
          const PackIcon = pack.icon;
          const isCurrent = pack.id === current.id;
          return (
            <button
              key={pack.id}
              type="button"
              onClick={() => {
                setCurrentDomain(pack.id);
                setOpen(false);
              }}
              className={cn(
                'flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-sm text-left hover:bg-accent hover:text-accent-foreground',
                isCurrent && 'bg-accent/50'
              )}
            >
              {PackIcon && <PackIcon className="h-4 w-4" />}
              <div className="flex-1 min-w-0">
                <div className="truncate">{pack.name}</div>
                {pack.description && (
                  <div className="truncate text-xs text-muted-foreground">
                    {pack.description}
                  </div>
                )}
              </div>
              {isCurrent && <Check size={14} className="text-muted-foreground" />}
            </button>
          );
        })}
      </PopoverContent>
    </Popover>
  );
}

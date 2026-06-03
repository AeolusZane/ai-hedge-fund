/**
 * Decision Tree Panel — visualizes an agent's structured reasoning trace.
 *
 * Each decision_step has:
 *   - step: identifier (classify_bug, search_codebase, form_hypothesis)
 *   - description: human-readable summary
 *   - details: step-specific data (bug_type, queries, findings, alternatives)
 *   - confidence: 0.0-1.0 score
 *
 * Renders a vertical timeline of steps with expandable details,
 * confidence indicators, and code search results.
 */
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import {
  Brain,
  Search,
  Lightbulb,
  ChevronDown,
  ChevronRight,
  FileCode,
  AlertTriangle,
  CheckCircle2,
  XCircle,
} from 'lucide-react';
import { useState } from 'react';
import type { DecisionStep } from './node-output-store';

interface DecisionTreePanelProps {
  steps: DecisionStep[];
  running: boolean;
}

// Step icons by step type
const STEP_ICONS: Record<string, React.ElementType> = {
  classify_bug: Brain,
  search_codebase: Search,
  form_hypothesis: Lightbulb,
};

const STEP_LABELS: Record<string, string> = {
  classify_bug: 'Bug Classification',
  search_codebase: 'Code Search',
  form_hypothesis: 'Hypothesis',
};

/**
 * Confidence badge — color-coded by confidence level.
 */
function ConfidenceBadge({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color =
    value >= 0.7 ? 'text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-950/30' :
    value >= 0.4 ? 'text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/30' :
    'text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/30';

  return (
    <span className={cn('inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium', color)}>
      {pct}% confidence
    </span>
  );
}

/**
 * Confidence bar — visual indicator.
 */
function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const barColor =
    value >= 0.7 ? 'bg-green-500' :
    value >= 0.4 ? 'bg-amber-500' :
    'bg-red-500';

  return (
    <div className="w-full h-1.5 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
      <div
        className={cn('h-full rounded-full transition-all duration-500', barColor)}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

/**
 * Single decision step card.
 */
function StepCard({
  step,
  index,
  isLast,
  isRunning,
}: {
  step: DecisionStep;
  index: number;
  isLast: boolean;
  isRunning: boolean;
}) {
  const [expanded, setExpanded] = useState(index === 0 || isLast);
  const Icon = STEP_ICONS[step.step] ?? Brain;
  const label = STEP_LABELS[step.step] ?? step.step;
  const isActive = isRunning && isLast;

  return (
    <div className="relative">
      {/* Timeline connector */}
      {!isLast && (
        <div className="absolute left-[15px] top-9 bottom-0 w-px bg-border" />
      )}

      <div className="flex gap-3">
        {/* Timeline dot */}
        <div className={cn(
          'flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center border',
          isActive
            ? 'border-blue-400 bg-blue-50 dark:bg-blue-950/30 animate-pulse'
            : 'border-border bg-background'
        )}>
          <Icon className={cn('h-4 w-4', isActive ? 'text-blue-500' : 'text-muted-foreground')} />
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0 pb-4">
          {/* Header */}
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-2 w-full text-left group"
          >
            <span className="text-xs font-medium text-foreground">{label}</span>
            <ConfidenceBadge value={step.confidence} />
            <span className="ml-auto text-muted-foreground">
              {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
            </span>
          </button>

          {/* Description */}
          <p className="text-[11px] text-muted-foreground mt-0.5">{step.description}</p>

          {/* Confidence bar */}
          <div className="mt-1.5">
            <ConfidenceBar value={step.confidence} />
          </div>

          {/* Expanded details */}
          {expanded && step.details && (
            <div className="mt-2 space-y-2">
              <StepDetails step={step} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Renders step-specific details based on step type.
 */
function StepDetails({ step }: { step: DecisionStep }) {
  const details = step.details;

  switch (step.step) {
    case 'classify_bug':
      return <ClassifyDetails details={details} />;
    case 'search_codebase':
      return <SearchDetails details={details} />;
    case 'form_hypothesis':
      return <HypothesisDetails details={details} />;
    default:
      return (
        <pre className="text-[10px] font-mono bg-muted/30 rounded p-2 overflow-auto max-h-40">
          {JSON.stringify(details, null, 2)}
        </pre>
      );
  }
}

function ClassifyDetails({ details }: { details: Record<string, any> }) {
  return (
    <div className="space-y-1.5 text-[11px]">
      <div className="flex items-center gap-2">
        <span className="text-muted-foreground">Type:</span>
        <Badge variant="outline" className="text-[10px] font-mono">
          {details.bug_type ?? 'unknown'}
        </Badge>
      </div>
      {details.reasoning && (
        <div>
          <span className="text-muted-foreground">Reasoning: </span>
          <span className="text-foreground">{details.reasoning}</span>
        </div>
      )}
      {details.initial_hypothesis && (
        <div>
          <span className="text-muted-foreground">Initial guess: </span>
          <span className="text-foreground">{details.initial_hypothesis}</span>
        </div>
      )}
      {Array.isArray(details.likely_areas) && details.likely_areas.length > 0 && (
        <div>
          <span className="text-muted-foreground">Likely areas: </span>
          <span className="text-foreground">{details.likely_areas.join(', ')}</span>
        </div>
      )}
    </div>
  );
}

function SearchDetails({ details }: { details: Record<string, any> }) {
  const queries = details.queries ?? [];
  const findings = details.key_findings ?? [];

  return (
    <div className="space-y-2 text-[11px]">
      {/* Query summary */}
      {queries.length > 0 && (
        <div className="space-y-1">
          <span className="text-muted-foreground text-[10px] uppercase tracking-wide">
            Queries ({details.total_matches ?? '?'} matches)
          </span>
          {queries.map((q: any, i: number) => (
            <div key={i} className="flex items-center gap-2 pl-2">
              <Search className="h-3 w-3 text-muted-foreground flex-shrink-0" />
              <code className="text-[10px] font-mono bg-muted/50 px-1 rounded">
                {q.query}
              </code>
              <span className="text-muted-foreground text-[10px]">
                {q.matches} hit{q.matches !== 1 ? 's' : ''}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Key findings */}
      {findings.length > 0 && (
        <div className="space-y-1">
          <span className="text-muted-foreground text-[10px] uppercase tracking-wide">
            Key Findings
          </span>
          {findings.map((f: string, i: number) => (
            <div key={i} className="flex items-start gap-1.5 pl-2">
              <FileCode className="h-3 w-3 text-blue-400 flex-shrink-0 mt-0.5" />
              <span className="text-foreground break-all">{f}</span>
            </div>
          ))}
        </div>
      )}

      {queries.length === 0 && findings.length === 0 && (
        <div className="flex items-center gap-2 text-muted-foreground">
          <AlertTriangle className="h-3 w-3" />
          <span>No code search performed (repo not available)</span>
        </div>
      )}
    </div>
  );
}

function HypothesisDetails({ details }: { details: Record<string, any> }) {
  const alternatives = details.alternatives ?? [];
  const evidence = details.evidence_chain ?? [];

  return (
    <div className="space-y-2 text-[11px]">
      {/* Main hypothesis */}
      {details.hypothesis && (
        <div className="flex items-start gap-2 bg-green-50 dark:bg-green-950/20 rounded p-2 border border-green-200 dark:border-green-800">
          <CheckCircle2 className="h-3.5 w-3.5 text-green-500 flex-shrink-0 mt-0.5" />
          <span className="text-foreground">{details.hypothesis}</span>
        </div>
      )}

      {/* Evidence chain */}
      {evidence.length > 0 && (
        <div className="space-y-1">
          <span className="text-muted-foreground text-[10px] uppercase tracking-wide">
            Evidence Chain
          </span>
          {evidence.map((e: string, i: number) => (
            <div key={i} className="flex items-start gap-1.5 pl-2">
              <span className="text-muted-foreground text-[10px]">{i + 1}.</span>
              <span className="text-foreground">{e}</span>
            </div>
          ))}
        </div>
      )}

      {/* Alternatives */}
      {alternatives.length > 0 && (
        <div className="space-y-1">
          <span className="text-muted-foreground text-[10px] uppercase tracking-wide">
            Alternative Hypotheses
          </span>
          {alternatives.map((alt: any, i: number) => (
            <div key={i} className="flex items-center gap-2 pl-2">
              <XCircle className="h-3 w-3 text-muted-foreground flex-shrink-0" />
              <span className="text-muted-foreground flex-1">{alt.hypothesis}</span>
              <span className="text-[10px] text-muted-foreground">
                {Math.round((alt.confidence ?? 0) * 100)}%
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Main Decision Tree Panel.
 */
export function DecisionTreePanel({ steps, running }: DecisionTreePanelProps) {
  if (steps.length === 0) {
    if (running) {
      return (
        <div className="flex items-center gap-2 py-4 text-xs text-muted-foreground">
          <Brain className="h-4 w-4 animate-pulse" />
          <span>Building decision tree...</span>
        </div>
      );
    }
    return null;
  }

  return (
    <div className="space-y-0">
      <div className="flex items-center gap-2 mb-3">
        <Brain className="h-4 w-4 text-blue-500" />
        <span className="text-xs font-medium">Decision Tree</span>
        <Badge variant="outline" className="text-[10px]">
          {steps.length} step{steps.length !== 1 ? 's' : ''}
        </Badge>
        {running && (
          <span className="flex items-center gap-1 text-[10px] text-blue-500">
            <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
            reasoning...
          </span>
        )}
      </div>

      {steps.map((step, i) => (
        <StepCard
          key={`${step.step}-${i}`}
          step={step}
          index={i}
          isLast={i === steps.length - 1}
          isRunning={running}
        />
      ))}
    </div>
  );
}

import { Layers } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { fetchStack, type StackStep } from './api';

interface StackPanelProps {
  owner: string;
  slug: string;
  number: number;
  onOpen: (number: number) => void;
}

/** The stack this request belongs to, the one that goes in first at the top. */
export function StackPanel({ owner, slug, number, onOpen }: StackPanelProps): ReactNode {
  const { t } = useTranslation();
  const [steps, setSteps] = useState<StackStep[]>([]);

  useEffect(() => {
    const controller = new AbortController();
    fetchStack(owner, slug, number, controller.signal)
      .then(setSteps)
      .catch(() => {
        // A request standing alone is not a stack, which is the ordinary case.
      });
    return () => {
      controller.abort();
    };
  }, [owner, slug, number]);

  if (steps.length === 0) return null;

  return (
    <div className="space-y-2 rounded-lg border border-app bg-surface-raised p-3">
      <p className="flex items-center gap-2 text-sm text-app">
        <Layers className="h-4 w-4 text-accent" aria-hidden="true" />
        {t('stack.heading', { count: steps.length })}
      </p>
      <ol className="space-y-1">
        {steps.map((step) => (
          <li key={step.number}>
            <button
              type="button"
              onClick={() => {
                onOpen(step.number);
              }}
              aria-current={step.number === number ? 'true' : undefined}
              className={`w-full rounded-md px-2 py-1 text-left text-xs ${
                step.number === number
                  ? 'bg-accent-subtle text-app'
                  : 'text-muted hover:bg-surface hover:text-app'
              }`}
            >
              <span className="font-mono">
                {step.position}. !{step.number}
              </span>{' '}
              <span className="truncate">{step.title}</span>
            </button>
          </li>
        ))}
      </ol>
      <p className="text-xs text-muted">{t('stack.explains')}</p>
    </div>
  );
}

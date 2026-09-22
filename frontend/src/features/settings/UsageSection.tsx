import { Gauge } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import type { TranslationKey } from '../../i18n/keys';
import { readableSize } from '../storage/size';
import { fetchUsage, type Usage } from './api';

const FULL = 100;
const NEARLY_FULL = 90;
const HALF_FULL = 70;

/** The kinds counted one by one, in the order the console shows them. */
const COUNTED = [
  'buckets',
  'applications',
  'functions',
  'databases',
  'queues',
  'workspaces',
] as const;

type Counted = (typeof COUNTED)[number];

const label = (kind: Counted | 'storage'): TranslationKey =>
  `settings.usage.${kind}` as TranslationKey;

const share = (held: number, limit: number): number =>
  limit <= 0 ? FULL : Math.min(Math.round((held / limit) * FULL), FULL);

const barColour = (percent: number): string => {
  if (percent >= NEARLY_FULL) return 'bg-error';
  if (percent >= HALF_FULL) return 'bg-warning';
  return 'bg-accent';
};

function Bar({ percent }: { percent: number }): ReactNode {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-raised">
      <div className={`h-full ${barColour(percent)}`} style={{ width: `${percent.toString()}%` }} />
    </div>
  );
}

/** How much of the instance this account takes, beside what it may take. */
export function UsageSection(): ReactNode {
  const { t } = useTranslation();
  const [usage, setUsage] = useState<Usage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchUsage(controller.signal)
      .then(setUsage)
      .catch(() => {
        if (!controller.signal.aborted) setError(t('settings.error.generic'));
      });
    return () => {
      controller.abort();
    };
  }, [t]);

  return (
    <section aria-labelledby="usage-heading" className="space-y-4">
      <div>
        <h2
          id="usage-heading"
          className="text-sm font-semibold uppercase tracking-wider text-muted"
        >
          {t('settings.usage.heading')}
        </h2>
        <p className="mt-1 text-sm text-muted">{t('settings.usage.description')}</p>
      </div>

      {error !== null && <ErrorBanner message={error} />}

      {usage !== null && (
        <div className="space-y-4 rounded-xl border border-app bg-surface p-4 shadow-app-sm">
          <div className="space-y-1.5">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="flex items-center gap-2 text-sm text-app">
                <Gauge className="h-4 w-4 text-accent" aria-hidden="true" />
                {t(label('storage'))}
              </span>
              <span className="font-mono text-xs text-muted">
                {readableSize(usage.storageBytes)} / {readableSize(usage.limits.storageBytes)}
              </span>
            </div>
            <Bar percent={share(usage.storageBytes, usage.limits.storageBytes)} />
            <p className="text-xs text-muted">
              {t('settings.usage.breakdown', {
                files: usage.files,
                packages: usage.packages,
                layers: usage.layers,
              })}
            </p>
          </div>

          <ul className="space-y-3">
            {COUNTED.map((kind) => (
              <li key={kind} className="space-y-1.5">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="text-sm text-app">{t(label(kind))}</span>
                  <span className="font-mono text-xs text-muted">
                    {usage[kind]} / {usage.limits[kind]}
                  </span>
                </div>
                <Bar percent={share(usage[kind], usage.limits[kind])} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

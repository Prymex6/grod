import { CheckCircle2, Loader2, XCircle } from 'lucide-react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { useInstanceHealth } from './useInstanceHealth';

function Row({ label, value }: { label: string; value: ReactNode }): ReactNode {
  return (
    <div className="flex items-center justify-between gap-4 px-4 py-3">
      <span className="text-sm text-muted">{label}</span>
      <span className="font-mono text-sm text-app">{value}</span>
    </div>
  );
}

/** Temporary home page: shows that the console and the API talk to each other. */
export function HomePage(): ReactNode {
  const { t } = useTranslation();
  const { state, reload } = useInstanceHealth();

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-app">{t('home.title')}</h1>
        <p className="mt-1 text-sm text-muted">{t('home.subtitle')}</p>
      </div>

      <section aria-labelledby="instance-heading" className="max-w-xl">
        <h2
          id="instance-heading"
          className="mb-3 text-sm font-semibold uppercase tracking-wider text-muted"
        >
          {t('home.instanceHeading')}
        </h2>

        <div className="divide-y divide-app overflow-hidden rounded-xl border border-app bg-surface shadow-app-sm">
          {state.kind === 'loading' && (
            <div className="flex items-center gap-2 px-4 py-3 text-sm text-muted">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              {t('home.loading')}
            </div>
          )}

          {state.kind === 'ready' && (
            <>
              <Row label={t('home.instanceName')} value={state.health.instance} />
              <Row label={t('home.version')} value={state.health.version} />
              <Row
                label={t('home.apiStatus')}
                value={
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-success-subtle px-2 py-0.5 text-xs font-medium text-success">
                    <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                    {t('home.apiOk')}
                  </span>
                }
              />
            </>
          )}

          {state.kind === 'unavailable' && (
            <div className="flex items-center justify-between gap-4 px-4 py-3">
              <span className="inline-flex items-center gap-1.5 text-sm text-error">
                <XCircle className="h-4 w-4" aria-hidden="true" />
                {t('home.apiUnavailable')}
              </span>
              <button
                type="button"
                onClick={reload}
                className="rounded-md border border-app px-2.5 py-1 text-xs font-medium text-app hover:bg-surface-raised"
              >
                {t('common.retry')}
              </button>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

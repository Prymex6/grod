import {
  Activity,
  CircleCheck,
  CircleHelp,
  CircleX,
  Loader2,
  Play,
  Plus,
  Trash2,
} from 'lucide-react';
import { useEffect, useState, type ReactNode, type SyntheticEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import type { TranslationKey } from '../../i18n/keys';
import { ApiError } from '../../lib/api';
import {
  createCheck,
  deleteCheck,
  fetchChecks,
  fetchResults,
  runCheck,
  type Check,
  type CheckResult,
  type CheckState,
} from './api';

const HTTP_CONFLICT = 409;
const NAME_MAX_LENGTH = 100;
const DEFAULT_INTERVAL = 60;
const BAR_COUNT = 40;

const STATE_ICON = {
  unknown: CircleHelp,
  up: CircleCheck,
  down: CircleX,
} as const satisfies Record<CheckState, typeof CircleCheck>;

const STATE_COLOUR = {
  unknown: 'text-muted',
  up: 'text-success',
  down: 'text-error',
} as const satisfies Record<CheckState, string>;

const STATE_KEYS = {
  unknown: 'monitoring.state.unknown',
  up: 'monitoring.state.up',
  down: 'monitoring.state.down',
} as const satisfies Record<CheckState, TranslationKey>;

/** Addresses the platform watches, with how each one has been doing. */
export function ChecksPage(): ReactNode {
  const { t, i18n } = useTranslation();
  const [checks, setChecks] = useState<Check[] | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  const [results, setResults] = useState<CheckResult[]>([]);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    fetchChecks(controller.signal)
      .then(setChecks)
      .catch(() => {
        if (!controller.signal.aborted) setError(t('monitoring.error.load'));
      });
    return () => {
      controller.abort();
    };
  }, [reloads, t]);

  useEffect(() => {
    if (chosen === null) return undefined;
    const controller = new AbortController();
    fetchResults(chosen, controller.signal)
      .then(setResults)
      .catch(() => {
        setResults([]);
      });
    return () => {
      controller.abort();
    };
  }, [chosen, reloads]);

  const reload = (): void => {
    setReloads((count) => count + 1);
  };

  const add = (event: SyntheticEvent<HTMLFormElement>): void => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    createCheck({ name: name.trim(), url: url.trim(), intervalSeconds: DEFAULT_INTERVAL })
      .then(() => {
        setName('');
        setUrl('');
        setCreating(false);
        reload();
      })
      .catch((cause: unknown) => {
        const taken = cause instanceof ApiError && cause.status === HTTP_CONFLICT;
        setError(t(taken ? 'monitoring.error.taken' : 'monitoring.error.create'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const act = (action: (checkName: string) => Promise<unknown>, checkName: string): void => {
    setBusy(true);
    setError(null);
    action(checkName)
      .then(reload)
      .catch(() => {
        setError(t('monitoring.error.create'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight text-app">
            <Activity className="h-6 w-6 text-accent" aria-hidden="true" />
            {t('monitoring.title')}
          </h1>
          <p className="mt-1 text-sm text-muted">{t('monitoring.subtitle')}</p>
        </div>
        <button
          type="button"
          onClick={() => {
            setCreating((open) => !open);
          }}
          className="flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          {t('monitoring.create')}
        </button>
      </div>

      {error !== null && <ErrorBanner message={error} />}

      {creating && (
        <form
          className="flex flex-wrap items-end gap-3 rounded-xl border border-app bg-surface p-4 shadow-app-sm"
          onSubmit={add}
        >
          <div className="min-w-40 flex-1">
            <label htmlFor="checkName" className="mb-1.5 block text-sm font-medium text-app">
              {t('monitoring.field.name')}
            </label>
            <input
              id="checkName"
              type="text"
              required
              maxLength={NAME_MAX_LENGTH}
              value={name}
              onChange={(event) => {
                setName(event.target.value);
              }}
              placeholder="Strona firmowa"
              className="w-full rounded-lg border border-app bg-app px-3 py-2 text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
            />
          </div>
          <div className="min-w-56 flex-1">
            <label htmlFor="checkUrl" className="mb-1.5 block text-sm font-medium text-app">
              {t('monitoring.field.url')}
            </label>
            <input
              id="checkUrl"
              type="url"
              required
              value={url}
              onChange={(event) => {
                setUrl(event.target.value);
              }}
              placeholder="https://moja-strona.pl/"
              className="w-full rounded-lg border border-app bg-app px-3 py-2 font-mono text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
            />
          </div>
          <button
            type="submit"
            disabled={busy}
            className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
          >
            {t('monitoring.create')}
          </button>
        </form>
      )}

      {checks === null && error === null && (
        <p className="flex items-center gap-2 text-sm text-muted">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          {t('monitoring.loading')}
        </p>
      )}

      {checks !== null && checks.length === 0 && (
        <p className="rounded-xl border border-app bg-surface px-4 py-6 text-center text-sm text-muted">
          {t('monitoring.empty')}
        </p>
      )}

      {checks !== null && checks.length > 0 && (
        <ul className="space-y-3">
          {checks.map((check) => {
            const Icon = STATE_ICON[check.state];
            return (
              <li
                key={check.id}
                className="space-y-3 rounded-xl border border-app bg-surface p-4 shadow-app-sm"
              >
                <div className="flex flex-wrap items-center gap-3">
                  <Icon
                    className={`h-5 w-5 shrink-0 ${STATE_COLOUR[check.state]}`}
                    aria-hidden="true"
                  />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-app">{check.name}</p>
                    <p className="mt-0.5 truncate font-mono text-xs text-muted">{check.url}</p>
                  </div>
                  <span className={`shrink-0 text-xs ${STATE_COLOUR[check.state]}`}>
                    {t(STATE_KEYS[check.state])}
                  </span>
                  <span className="shrink-0 text-xs text-muted">
                    {t('monitoring.uptime', { value: check.uptime })}
                    {check.averageMs > 0 && ` · ${String(check.averageMs)} ms`}
                  </span>
                  <button
                    type="button"
                    onClick={() => {
                      act(runCheck, check.name);
                    }}
                    disabled={busy}
                    aria-label={t('monitoring.run', { name: check.name })}
                    className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted hover:bg-surface-raised hover:text-accent disabled:opacity-60"
                  >
                    <Play className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setChosen(chosen === check.name ? null : check.name);
                    }}
                    aria-pressed={chosen === check.name}
                    className="shrink-0 rounded-md px-2 py-1 text-xs text-muted hover:bg-surface-raised hover:text-app"
                  >
                    {t('monitoring.history')}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      act(deleteCheck, check.name);
                    }}
                    disabled={busy}
                    aria-label={t('monitoring.remove', { name: check.name })}
                    className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted hover:bg-surface-raised hover:text-error disabled:opacity-60"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>

                {check.lastError !== '' && (
                  <p className="rounded-lg bg-error-subtle px-3 py-2 font-mono text-xs text-app">
                    {check.lastError}
                  </p>
                )}

                {chosen === check.name && (
                  <div className="space-y-2">
                    {/* Every look is one bar, newest on the right. */}
                    <div className="flex items-end gap-0.5" aria-hidden="true">
                      {[...results]
                        .slice(0, BAR_COUNT)
                        .reverse()
                        .map((result, index) => (
                          <span
                            key={`${result.createdAt}:${String(index)}`}
                            title={`${result.ok ? 'OK' : 'ERR'} · ${String(result.durationMs)} ms`}
                            className={`h-6 w-1.5 rounded-sm ${
                              result.ok ? 'bg-success' : 'bg-error'
                            }`}
                          />
                        ))}
                    </div>
                    {results.length === 0 ? (
                      <p className="text-xs text-muted">{t('monitoring.noHistory')}</p>
                    ) : (
                      <p className="text-xs text-muted">
                        {t('monitoring.lastLook', {
                          date: new Date(results[0]?.createdAt ?? '').toLocaleString(
                            i18n.resolvedLanguage ?? 'pl',
                          ),
                        })}
                      </p>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

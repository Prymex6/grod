import { Check, Loader2, Plus, Radar, Trash2 } from 'lucide-react';
import { useEffect, useState, type ReactNode, type SyntheticEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { CopyButton } from '../../components/ui/CopyButton';
import { ErrorBanner } from '../../components/ui/ErrorBanner';
import type { TranslationKey } from '../../i18n/keys';
import { ApiError } from '../../lib/api';
import {
  createSource,
  deleteSource,
  fetchIssues,
  fetchReports,
  fetchSources,
  resolveIssue,
  type Issue,
  type Level,
  type Report,
  type Source,
} from './api';

const HTTP_CONFLICT = 409;
const NAME_MAX_LENGTH = 100;

const LEVEL_COLOUR = {
  info: 'text-info',
  warning: 'text-warning',
  error: 'text-error',
  fatal: 'text-error',
} as const satisfies Record<Level, string>;

const LEVEL_KEYS = {
  info: 'errors.level.info',
  warning: 'errors.level.warning',
  error: 'errors.level.error',
  fatal: 'errors.level.fatal',
} as const satisfies Record<Level, TranslationKey>;

/** Errors the applications of the account reported. */
export function ErrorsPage(): ReactNode {
  const { t, i18n } = useTranslation();
  const [sources, setSources] = useState<Source[] | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [openedIssue, setOpenedIssue] = useState<string | null>(null);
  const [reports, setReports] = useState<Report[]>([]);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    fetchSources(controller.signal)
      .then((found) => {
        setSources(found);
        setChosen((current) => current ?? found[0]?.name ?? null);
      })
      .catch(() => {
        if (!controller.signal.aborted) setError(t('errors.error.load'));
      });
    return () => {
      controller.abort();
    };
  }, [reloads, t]);

  useEffect(() => {
    if (chosen === null) return undefined;
    const controller = new AbortController();
    fetchIssues(chosen, {}, controller.signal)
      .then(setIssues)
      .catch(() => {
        setIssues([]);
      });
    return () => {
      controller.abort();
    };
  }, [chosen, reloads]);

  useEffect(() => {
    if (chosen === null || openedIssue === null) return undefined;
    const controller = new AbortController();
    fetchReports(chosen, openedIssue, controller.signal)
      .then(setReports)
      .catch(() => {
        setReports([]);
      });
    return () => {
      controller.abort();
    };
  }, [chosen, openedIssue, reloads]);

  const reload = (): void => {
    setReloads((count) => count + 1);
  };

  const add = (event: SyntheticEvent<HTMLFormElement>): void => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    createSource(name.trim())
      .then((created) => {
        setName('');
        setCreating(false);
        setChosen(created.name);
        reload();
      })
      .catch((cause: unknown) => {
        const taken = cause instanceof ApiError && cause.status === HTTP_CONFLICT;
        setError(t(taken ? 'errors.error.taken' : 'errors.error.create'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const current = sources?.find((item) => item.name === chosen) ?? null;

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight text-app">
            <Radar className="h-6 w-6 text-accent" aria-hidden="true" />
            {t('errors.title')}
          </h1>
          <p className="mt-1 text-sm text-muted">{t('errors.subtitle')}</p>
        </div>
        <button
          type="button"
          onClick={() => {
            setCreating((open) => !open);
          }}
          className="flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          {t('errors.create')}
        </button>
      </div>

      {error !== null && <ErrorBanner message={error} />}

      {creating && (
        <form
          className="flex flex-wrap items-end gap-3 rounded-xl border border-app bg-surface p-4 shadow-app-sm"
          onSubmit={add}
        >
          <div className="min-w-48 flex-1">
            <label htmlFor="sourceName" className="mb-1.5 block text-sm font-medium text-app">
              {t('errors.field.name')}
            </label>
            <input
              id="sourceName"
              type="text"
              required
              maxLength={NAME_MAX_LENGTH}
              value={name}
              onChange={(event) => {
                setName(event.target.value);
              }}
              placeholder="sklep"
              className="w-full rounded-lg border border-app bg-app px-3 py-2 text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
            />
          </div>
          <button
            type="submit"
            disabled={busy}
            className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
          >
            {t('errors.create')}
          </button>
        </form>
      )}

      {sources === null && error === null && (
        <p className="flex items-center gap-2 text-sm text-muted">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          {t('errors.loading')}
        </p>
      )}

      {sources !== null && sources.length === 0 && (
        <p className="rounded-xl border border-app bg-surface px-4 py-6 text-center text-sm text-muted">
          {t('errors.empty')}
        </p>
      )}

      {sources !== null && sources.length > 0 && (
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
          <ul className="w-full shrink-0 space-y-1.5 lg:w-64">
            {sources.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => {
                    setChosen(item.name);
                    setOpenedIssue(null);
                  }}
                  aria-pressed={item.name === chosen}
                  className={`w-full rounded-lg border px-3 py-2 text-left ${
                    item.name === chosen
                      ? 'border-accent bg-accent-subtle'
                      : 'border-app bg-surface hover:bg-surface-raised'
                  }`}
                >
                  <p className="truncate text-sm text-app">{item.name}</p>
                  <p className="mt-0.5 truncate text-xs text-muted">
                    {t('errors.counts', { open: item.unresolved, reports: item.reports })}
                  </p>
                </button>
              </li>
            ))}
          </ul>

          {current !== null && (
            <div className="min-w-0 flex-1 space-y-3">
              <div className="space-y-2 rounded-xl border border-app bg-surface p-3 shadow-app-sm">
                <p className="text-xs text-muted">{t('errors.keyHint')}</p>
                <div className="flex items-center gap-2">
                  <code className="min-w-0 flex-1 truncate rounded-lg border border-app bg-app px-2 py-1 font-mono text-xs text-app">
                    {current.key}
                  </code>
                  <CopyButton value={current.key} label={t('errors.copyKey')} />
                  <button
                    type="button"
                    onClick={() => {
                      setBusy(true);
                      deleteSource(current.name)
                        .then(() => {
                          setChosen(null);
                          reload();
                        })
                        .catch(() => {
                          setError(t('errors.error.create'));
                        })
                        .finally(() => {
                          setBusy(false);
                        });
                    }}
                    disabled={busy}
                    aria-label={t('errors.remove', { name: current.name })}
                    className="flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-surface-raised hover:text-error disabled:opacity-60"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>

              {issues.length === 0 ? (
                <p className="rounded-xl border border-app bg-surface px-4 py-6 text-center text-sm text-muted">
                  {t('errors.noIssues')}
                </p>
              ) : (
                <ul className="divide-y divide-app overflow-hidden rounded-xl border border-app bg-surface shadow-app-sm">
                  {issues.map((issue) => (
                    <li key={issue.id} className="space-y-2 px-4 py-3">
                      <div className="flex flex-wrap items-center gap-3">
                        <div className="min-w-0 flex-1">
                          <p className="flex flex-wrap items-center gap-2">
                            <span
                              className={`font-mono text-sm font-medium ${LEVEL_COLOUR[issue.level]}`}
                            >
                              {issue.kind}
                            </span>
                            <span className="text-xs text-muted">{t(LEVEL_KEYS[issue.level])}</span>
                            {issue.resolved && (
                              <span className="rounded-full bg-success-subtle px-2 py-0.5 text-xs text-success">
                                {t('errors.resolved')}
                              </span>
                            )}
                          </p>
                          <p className="mt-0.5 truncate text-sm text-app">{issue.message}</p>
                          {issue.culprit !== '' && (
                            <p className="mt-0.5 truncate font-mono text-xs text-muted">
                              {issue.culprit}
                            </p>
                          )}
                        </div>
                        <span className="shrink-0 text-xs text-muted">
                          {t('errors.seen', {
                            count: issue.count,
                            date: new Date(issue.lastSeenAt).toLocaleString(
                              i18n.resolvedLanguage ?? 'pl',
                            ),
                          })}
                        </span>
                        <button
                          type="button"
                          onClick={() => {
                            setBusy(true);
                            resolveIssue(current.name, issue.id, !issue.resolved)
                              .then(reload)
                              .catch(() => {
                                setError(t('errors.error.create'));
                              })
                              .finally(() => {
                                setBusy(false);
                              });
                          }}
                          disabled={busy}
                          className="flex shrink-0 items-center gap-1.5 rounded-lg border border-app bg-surface px-2.5 py-1 text-xs text-app hover:bg-surface-raised disabled:opacity-60"
                        >
                          <Check className="h-3.5 w-3.5" aria-hidden="true" />
                          {t(issue.resolved ? 'errors.reopen' : 'errors.resolve')}
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setOpenedIssue(openedIssue === issue.id ? null : issue.id);
                          }}
                          aria-pressed={openedIssue === issue.id}
                          className="shrink-0 rounded-md px-2 py-1 text-xs text-muted hover:bg-surface-raised hover:text-app"
                        >
                          {t('errors.details')}
                        </button>
                      </div>

                      {openedIssue === issue.id && reports.length > 0 && (
                        <div className="space-y-2">
                          <p className="text-xs text-muted">
                            {reports[0]?.environment !== ''
                              ? t('errors.environment', { name: reports[0]?.environment ?? '' })
                              : ''}
                            {reports[0]?.release !== '' && ` · ${reports[0]?.release ?? ''}`}
                          </p>
                          <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-app p-3 font-mono text-xs text-app">
                            {reports[0]?.stack ?? ''}
                          </pre>
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

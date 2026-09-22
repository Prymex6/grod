import { Loader2, Play, Plus, Save, Trash2, Wind } from 'lucide-react';
import { useEffect, useState, type ReactNode, type SyntheticEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import { ApiError } from '../../lib/api';
import {
  callFunction,
  changeFunction,
  createFunction,
  deleteFunction,
  fetchFunctions,
  type CallResult,
  type GrodFunction,
  type Runtime,
} from './api';

const HTTP_CONFLICT = 409;
const NAME_MAX_LENGTH = 63;
const RUNTIMES: Runtime[] = ['python', 'node'];

/** Functions the account keeps, with an editor and a way to try one out. */
export function FunctionsPage(): ReactNode {
  const { t, i18n } = useTranslation();
  const [functions, setFunctions] = useState<GrodFunction[] | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  const [source, setSource] = useState('');
  const [event, setEvent] = useState('{}');
  const [result, setResult] = useState<CallResult | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState('');
  const [runtime, setRuntime] = useState<Runtime>('python');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    fetchFunctions(controller.signal)
      .then((found) => {
        setFunctions(found);
        setChosen((current) => current ?? found[0]?.name ?? null);
      })
      .catch(() => {
        if (!controller.signal.aborted) setError(t('functions.error.load'));
      });
    return () => {
      controller.abort();
    };
  }, [reloads, t]);

  const current = functions?.find((item) => item.name === chosen) ?? null;

  const choose = (item: GrodFunction): void => {
    setChosen(item.name);
    setSource(item.source);
    setResult(null);
  };

  const add = (submitted: SyntheticEvent<HTMLFormElement>): void => {
    submitted.preventDefault();
    setBusy(true);
    setError(null);
    createFunction({ name: name.trim().toLowerCase(), runtime, source: '' })
      .then((created) => {
        setName('');
        setCreating(false);
        setChosen(created.name);
        setSource(created.source);
        setReloads((count) => count + 1);
      })
      .catch((cause: unknown) => {
        const taken = cause instanceof ApiError && cause.status === HTTP_CONFLICT;
        setError(t(taken ? 'functions.error.taken' : 'functions.error.create'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const save = (): void => {
    if (current === null) return;
    setBusy(true);
    setError(null);
    changeFunction(current.name, { source })
      .then(() => {
        setReloads((count) => count + 1);
      })
      .catch(() => {
        setError(t('functions.error.save'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const run = (): void => {
    if (current === null) return;
    setBusy(true);
    setError(null);
    let payload: unknown = {};
    try {
      payload = JSON.parse(event);
    } catch {
      setError(t('functions.error.event'));
      setBusy(false);
      return;
    }
    callFunction(current.name, payload)
      .then((answer) => {
        setResult(answer);
        setReloads((count) => count + 1);
      })
      .catch(() => {
        setError(t('functions.error.call'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const drop = (): void => {
    if (current === null) return;
    setBusy(true);
    deleteFunction(current.name)
      .then(() => {
        setChosen(null);
        setSource('');
        setResult(null);
        setReloads((count) => count + 1);
      })
      .catch(() => {
        setError(t('functions.error.save'));
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
            <Wind className="h-6 w-6 text-accent" aria-hidden="true" />
            {t('functions.title')}
          </h1>
          <p className="mt-1 text-sm text-muted">{t('functions.subtitle')}</p>
        </div>
        <button
          type="button"
          onClick={() => {
            setCreating((open) => !open);
          }}
          className="flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          {t('functions.create')}
        </button>
      </div>

      {error !== null && <ErrorBanner message={error} />}

      {creating && (
        <form
          className="flex flex-wrap items-end gap-3 rounded-xl border border-app bg-surface p-4 shadow-app-sm"
          onSubmit={add}
        >
          <div className="min-w-48 flex-1">
            <label htmlFor="functionName" className="mb-1.5 block text-sm font-medium text-app">
              {t('functions.field.name')}
            </label>
            <input
              id="functionName"
              type="text"
              required
              maxLength={NAME_MAX_LENGTH}
              value={name}
              onChange={(changed) => {
                setName(changed.target.value);
              }}
              placeholder="powitanie"
              className="w-full rounded-lg border border-app bg-app px-3 py-2 font-mono text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
            />
          </div>
          <div>
            <label htmlFor="functionRuntime" className="mb-1.5 block text-sm font-medium text-app">
              {t('functions.field.runtime')}
            </label>
            <select
              id="functionRuntime"
              value={runtime}
              onChange={(changed) => {
                setRuntime(changed.target.value as Runtime);
              }}
              className="rounded-lg border border-app bg-surface px-2 py-2 text-sm text-app focus:border-accent focus:outline-none"
            >
              {RUNTIMES.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </div>
          <button
            type="submit"
            disabled={busy}
            className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
          >
            {t('functions.create')}
          </button>
        </form>
      )}

      {functions === null && error === null && (
        <p className="flex items-center gap-2 text-sm text-muted">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          {t('functions.loading')}
        </p>
      )}

      {functions !== null && functions.length === 0 && (
        <p className="rounded-xl border border-app bg-surface px-4 py-6 text-center text-sm text-muted">
          {t('functions.empty')}
        </p>
      )}

      {functions !== null && functions.length > 0 && (
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
          <ul className="w-full shrink-0 space-y-1.5 lg:w-64">
            {functions.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => {
                    choose(item);
                  }}
                  aria-pressed={item.name === chosen}
                  className={`w-full rounded-lg border px-3 py-2 text-left ${
                    item.name === chosen
                      ? 'border-accent bg-accent-subtle'
                      : 'border-app bg-surface hover:bg-surface-raised'
                  }`}
                >
                  <p className="truncate font-mono text-sm text-app">{item.name}</p>
                  <p className="mt-0.5 truncate text-xs text-muted">
                    {item.runtime} · {t('functions.callCount', { count: item.calls })}
                    {item.lastDurationMs !== null && ` · ${String(item.lastDurationMs)} ms`}
                  </p>
                </button>
              </li>
            ))}
          </ul>

          {current !== null && (
            <div className="min-w-0 flex-1 space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="min-w-0 flex-1 truncate font-mono text-lg text-app">
                  {current.name}
                </h2>
                <button
                  type="button"
                  onClick={save}
                  disabled={busy}
                  className="flex items-center gap-2 rounded-lg border border-app bg-surface px-3 py-1.5 text-sm text-app hover:bg-surface-raised disabled:opacity-60"
                >
                  <Save className="h-4 w-4" aria-hidden="true" />
                  {t('functions.save')}
                </button>
                <button
                  type="button"
                  onClick={run}
                  disabled={busy}
                  className="flex items-center gap-2 rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
                >
                  <Play className="h-4 w-4" aria-hidden="true" />
                  {t('functions.call')}
                </button>
                <button
                  type="button"
                  onClick={drop}
                  disabled={busy}
                  aria-label={t('functions.remove', { name: current.name })}
                  className="flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-surface-raised hover:text-error disabled:opacity-60"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>

              <div>
                <label
                  htmlFor="functionSource"
                  className="mb-1.5 block text-sm font-medium text-app"
                >
                  {t('functions.field.source')}
                </label>
                <textarea
                  id="functionSource"
                  rows={14}
                  value={source || current.source}
                  onChange={(changed) => {
                    setSource(changed.target.value);
                  }}
                  spellCheck={false}
                  className="w-full rounded-lg border border-app bg-app px-3 py-2 font-mono text-xs text-app focus:border-accent focus:outline-none"
                />
              </div>

              <div>
                <label
                  htmlFor="functionEvent"
                  className="mb-1.5 block text-sm font-medium text-app"
                >
                  {t('functions.field.event')}
                </label>
                <textarea
                  id="functionEvent"
                  rows={3}
                  value={event}
                  onChange={(changed) => {
                    setEvent(changed.target.value);
                  }}
                  spellCheck={false}
                  className="w-full rounded-lg border border-app bg-app px-3 py-2 font-mono text-xs text-app focus:border-accent focus:outline-none"
                />
              </div>

              {result !== null && (
                <div className="space-y-2 rounded-xl border border-app bg-surface p-3">
                  <p className="text-xs text-muted">
                    {result.ok ? t('functions.result.ok') : t('functions.result.failed')} ·{' '}
                    {result.durationMs} ms
                  </p>
                  <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-app p-3 font-mono text-xs text-app">
                    {result.ok ? JSON.stringify(result.answer, null, 2) : result.error}
                  </pre>
                </div>
              )}

              {current.lastCalledAt !== null && result === null && (
                <p className="text-xs text-muted">
                  {t('functions.lastCalled', {
                    date: new Date(current.lastCalledAt).toLocaleString(
                      i18n.resolvedLanguage ?? 'pl',
                    ),
                  })}
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

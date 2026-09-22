import { FileCode2, Globe, Loader2, Lock, Plus, RefreshCw, Trash2 } from 'lucide-react';
import { useEffect, useState, type ReactNode, type SyntheticEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import { ApiError } from '../../lib/api';
import {
  createDoc,
  deleteDoc,
  fetchDoc,
  fetchDocs,
  refreshDoc,
  setPublic,
  type ApiDoc,
  type ApiDocDetail,
  type Operation,
} from './api';

const HTTP_CONFLICT = 409;
const NAME_MAX_LENGTH = 63;

// Every method gets its own colour, the way every API browser shows it.
const METHOD_COLOUR: Record<string, string> = {
  GET: 'bg-info-subtle text-info',
  POST: 'bg-success-subtle text-success',
  PUT: 'bg-warning-subtle text-warning',
  PATCH: 'bg-warning-subtle text-warning',
  DELETE: 'bg-error-subtle text-error',
};

/** Group the operations of an API by the tag they carry. */
const byTag = (operations: Operation[]): [string, Operation[]][] => {
  const groups = new Map<string, Operation[]>();
  for (const operation of operations) {
    const tag = operation.tags[0] ?? '';
    groups.set(tag, [...(groups.get(tag) ?? []), operation]);
  }
  return [...groups.entries()].sort(([first], [second]) => first.localeCompare(second));
};

/** API descriptions the account keeps, with a browser for each one. */
export function ApisPage(): ReactNode {
  const { t } = useTranslation();
  const [docs, setDocs] = useState<ApiDoc[] | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  const [detail, setDetail] = useState<ApiDocDetail | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [document, setDocument] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    fetchDocs(controller.signal)
      .then((found) => {
        setDocs(found);
        setChosen((current) => current ?? found[0]?.name ?? null);
      })
      .catch(() => {
        if (!controller.signal.aborted) setError(t('apidocs.error.load'));
      });
    return () => {
      controller.abort();
    };
  }, [reloads, t]);

  useEffect(() => {
    if (chosen === null) return undefined;
    const controller = new AbortController();
    fetchDoc(chosen, controller.signal)
      .then(setDetail)
      .catch(() => {
        setDetail(null);
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
    createDoc({
      name: name.trim().toLowerCase(),
      document: document.trim(),
      url: url.trim(),
      public: false,
    })
      .then((created) => {
        setName('');
        setUrl('');
        setDocument('');
        setCreating(false);
        setChosen(created.name);
        reload();
      })
      .catch((cause: unknown) => {
        const taken = cause instanceof ApiError && cause.status === HTTP_CONFLICT;
        setError(t(taken ? 'apidocs.error.taken' : 'apidocs.error.create'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const act = (action: (docName: string) => Promise<unknown>, docName: string): void => {
    setBusy(true);
    setError(null);
    action(docName)
      .then(reload)
      .catch(() => {
        setError(t('apidocs.error.create'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const current = docs?.find((item) => item.name === chosen) ?? null;

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight text-app">
            <FileCode2 className="h-6 w-6 text-accent" aria-hidden="true" />
            {t('apidocs.title')}
          </h1>
          <p className="mt-1 text-sm text-muted">{t('apidocs.subtitle')}</p>
        </div>
        <button
          type="button"
          onClick={() => {
            setCreating((open) => !open);
          }}
          className="flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          {t('apidocs.create')}
        </button>
      </div>

      {error !== null && <ErrorBanner message={error} />}

      {creating && (
        <form
          className="space-y-3 rounded-xl border border-app bg-surface p-4 shadow-app-sm"
          onSubmit={add}
        >
          <div className="flex flex-wrap gap-3">
            <div className="min-w-40 flex-1">
              <label htmlFor="docName" className="mb-1.5 block text-sm font-medium text-app">
                {t('apidocs.field.name')}
              </label>
              <input
                id="docName"
                type="text"
                required
                maxLength={NAME_MAX_LENGTH}
                value={name}
                onChange={(event) => {
                  setName(event.target.value);
                }}
                placeholder="sklep-api"
                className="w-full rounded-lg border border-app bg-app px-3 py-2 font-mono text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
              />
            </div>
            <div className="min-w-56 flex-1">
              <label htmlFor="docUrl" className="mb-1.5 block text-sm font-medium text-app">
                {t('apidocs.field.url')}
              </label>
              <input
                id="docUrl"
                type="url"
                value={url}
                onChange={(event) => {
                  setUrl(event.target.value);
                }}
                placeholder="https://moja-apka/openapi.json"
                className="w-full rounded-lg border border-app bg-app px-3 py-2 font-mono text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
              />
            </div>
          </div>
          <div>
            <label htmlFor="docDocument" className="mb-1.5 block text-sm font-medium text-app">
              {t('apidocs.field.document')}
            </label>
            <textarea
              id="docDocument"
              rows={5}
              value={document}
              onChange={(event) => {
                setDocument(event.target.value);
              }}
              spellCheck={false}
              placeholder={t('apidocs.field.documentHint')}
              className="w-full rounded-lg border border-app bg-app px-3 py-2 font-mono text-xs text-app placeholder:text-muted focus:border-accent focus:outline-none"
            />
          </div>
          <button
            type="submit"
            disabled={busy}
            className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
          >
            {t('apidocs.create')}
          </button>
        </form>
      )}

      {docs === null && error === null && (
        <p className="flex items-center gap-2 text-sm text-muted">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          {t('apidocs.loading')}
        </p>
      )}

      {docs !== null && docs.length === 0 && (
        <p className="rounded-xl border border-app bg-surface px-4 py-6 text-center text-sm text-muted">
          {t('apidocs.empty')}
        </p>
      )}

      {docs !== null && docs.length > 0 && (
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
          <ul className="w-full shrink-0 space-y-1.5 lg:w-64">
            {docs.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => {
                    setChosen(item.name);
                  }}
                  aria-pressed={item.name === chosen}
                  className={`w-full rounded-lg border px-3 py-2 text-left ${
                    item.name === chosen
                      ? 'border-accent bg-accent-subtle'
                      : 'border-app bg-surface hover:bg-surface-raised'
                  }`}
                >
                  <p className="truncate text-sm text-app">{item.title || item.name}</p>
                  <p className="mt-0.5 truncate text-xs text-muted">
                    {item.version !== '' && `${item.version} · `}
                    {t('apidocs.operationCount', { count: item.operations })}
                  </p>
                </button>
              </li>
            ))}
          </ul>

          {current !== null && detail !== null && (
            <div className="min-w-0 flex-1 space-y-3">
              <div className="flex flex-wrap items-center gap-2 rounded-xl border border-app bg-surface p-4 shadow-app-sm">
                <div className="min-w-0 flex-1">
                  <h2 className="truncate text-lg font-semibold text-app">
                    {detail.title || detail.name}
                  </h2>
                  <p className="mt-0.5 truncate font-mono text-xs text-muted">
                    {detail.version}
                    {detail.url !== '' && ` · ${detail.url}`}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    act((docName) => setPublic(docName, !current.public), current.name);
                  }}
                  disabled={busy}
                  className="flex items-center gap-1.5 rounded-full bg-surface-raised px-2.5 py-1 text-xs text-muted hover:text-app disabled:opacity-60"
                >
                  {current.public ? (
                    <Globe className="h-3 w-3" aria-hidden="true" />
                  ) : (
                    <Lock className="h-3 w-3" aria-hidden="true" />
                  )}
                  {t(current.public ? 'apidocs.public' : 'apidocs.private')}
                </button>
                {current.source === 'url' && (
                  <button
                    type="button"
                    onClick={() => {
                      act(refreshDoc, current.name);
                    }}
                    disabled={busy}
                    aria-label={t('apidocs.refresh', { name: current.name })}
                    className="flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-surface-raised hover:text-accent disabled:opacity-60"
                  >
                    <RefreshCw className="h-4 w-4" />
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => {
                    setChosen(null);
                    act(deleteDoc, current.name);
                  }}
                  disabled={busy}
                  aria-label={t('apidocs.remove', { name: current.name })}
                  className="flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-surface-raised hover:text-error disabled:opacity-60"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>

              {current.lastError !== '' && <ErrorBanner message={current.lastError} />}

              {byTag(detail.paths).map(([tag, operations]) => (
                <section key={tag} className="space-y-1.5">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-muted">
                    {tag === '' ? t('apidocs.noTag') : tag}
                  </h3>
                  <ul className="divide-y divide-app overflow-hidden rounded-xl border border-app bg-surface shadow-app-sm">
                    {operations.map((operation) => (
                      <li
                        key={`${operation.method}:${operation.path}`}
                        className="flex flex-wrap items-center gap-3 px-4 py-2.5"
                      >
                        <span
                          className={`shrink-0 rounded-md px-2 py-0.5 font-mono text-xs font-semibold ${
                            METHOD_COLOUR[operation.method] ?? 'bg-surface-raised text-muted'
                          }`}
                        >
                          {operation.method}
                        </span>
                        <code className="min-w-0 flex-1 truncate font-mono text-sm text-app">
                          {operation.path}
                        </code>
                        {operation.summary !== '' && (
                          <span className="min-w-0 truncate text-xs text-muted">
                            {operation.summary}
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

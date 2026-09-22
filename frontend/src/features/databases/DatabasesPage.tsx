import { BookOpen, Eye, KeyRound, Loader2, Plus, Trash2 } from 'lucide-react';
import { useEffect, useState, type ReactNode, type SyntheticEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { CopyButton } from '../../components/ui/CopyButton';
import { ErrorBanner } from '../../components/ui/ErrorBanner';
import { ApiError } from '../../lib/api';
import { readableSize } from '../storage/size';
import {
  createDatabase,
  deleteDatabase,
  fetchConnection,
  fetchDatabases,
  rotatePassword,
  type DatabaseConnection,
  type ManagedDatabase,
} from './api';

const HTTP_CONFLICT = 409;
const NAME_MAX_LENGTH = 40;

/** Databases the account keeps, with the address each one is reached at. */
export function DatabasesPage(): ReactNode {
  const { t } = useTranslation();
  const [databases, setDatabases] = useState<ManagedDatabase[] | null>(null);
  const [connection, setConnection] = useState<DatabaseConnection | null>(null);
  const [shown, setShown] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    fetchDatabases(controller.signal)
      .then(setDatabases)
      .catch(() => {
        if (!controller.signal.aborted) setError(t('databases.error.load'));
      });
    return () => {
      controller.abort();
    };
  }, [reloads, t]);

  const reload = (): void => {
    setReloads((count) => count + 1);
  };

  const add = (event: SyntheticEvent<HTMLFormElement>): void => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    createDatabase(name.trim().toLowerCase())
      .then(() => {
        setName('');
        setCreating(false);
        reload();
      })
      .catch((cause: unknown) => {
        const taken = cause instanceof ApiError && cause.status === HTTP_CONFLICT;
        setError(t(taken ? 'databases.error.taken' : 'databases.error.create'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const show = (databaseName: string): void => {
    if (shown === databaseName) {
      setShown(null);
      setConnection(null);
      return;
    }
    setBusy(true);
    fetchConnection(databaseName)
      .then((found) => {
        setShown(databaseName);
        setConnection(found);
      })
      .catch(() => {
        setError(t('databases.error.load'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const rotate = (databaseName: string): void => {
    setBusy(true);
    rotatePassword(databaseName)
      .then((found) => {
        setShown(databaseName);
        setConnection(found);
      })
      .catch(() => {
        setError(t('databases.error.rotate'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const drop = (databaseName: string): void => {
    setBusy(true);
    deleteDatabase(databaseName)
      .then(() => {
        setShown(null);
        setConnection(null);
        reload();
      })
      .catch(() => {
        setError(t('databases.error.create'));
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
            <BookOpen className="h-6 w-6 text-accent" aria-hidden="true" />
            {t('databases.title')}
          </h1>
          <p className="mt-1 text-sm text-muted">{t('databases.subtitle')}</p>
        </div>
        <button
          type="button"
          onClick={() => {
            setCreating((open) => !open);
          }}
          className="flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          {t('databases.create')}
        </button>
      </div>

      {error !== null && <ErrorBanner message={error} />}

      {creating && (
        <form
          className="flex flex-wrap items-end gap-3 rounded-xl border border-app bg-surface p-4 shadow-app-sm"
          onSubmit={add}
        >
          <div className="min-w-48 flex-1">
            <label htmlFor="databaseName" className="mb-1.5 block text-sm font-medium text-app">
              {t('databases.field.name')}
            </label>
            <input
              id="databaseName"
              type="text"
              required
              maxLength={NAME_MAX_LENGTH}
              value={name}
              onChange={(event) => {
                setName(event.target.value);
              }}
              placeholder="sklep"
              className="w-full rounded-lg border border-app bg-app px-3 py-2 font-mono text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
            />
          </div>
          <button
            type="submit"
            disabled={busy}
            className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
          >
            {t('databases.create')}
          </button>
        </form>
      )}

      {databases === null && error === null && (
        <p className="flex items-center gap-2 text-sm text-muted">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          {t('databases.loading')}
        </p>
      )}

      {databases !== null && databases.length === 0 && (
        <p className="rounded-xl border border-app bg-surface px-4 py-6 text-center text-sm text-muted">
          {t('databases.empty')}
        </p>
      )}

      {databases !== null && databases.length > 0 && (
        <ul className="divide-y divide-app overflow-hidden rounded-xl border border-app bg-surface shadow-app-sm">
          {databases.map((database) => (
            <li key={database.id} className="space-y-3 px-4 py-3">
              <div className="flex flex-wrap items-center gap-3">
                <BookOpen className="h-4 w-4 shrink-0 text-muted" aria-hidden="true" />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-mono text-sm font-medium text-app">{database.name}</p>
                  <p className="mt-0.5 truncate text-xs text-muted">
                    {database.engine} · {database.host}:{database.port} ·{' '}
                    {readableSize(database.sizeBytes)}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    show(database.name);
                  }}
                  disabled={busy}
                  aria-pressed={shown === database.name}
                  className="flex items-center gap-1.5 rounded-lg border border-app bg-surface px-2.5 py-1.5 text-xs text-app hover:bg-surface-raised disabled:opacity-60"
                >
                  <Eye className="h-3.5 w-3.5" aria-hidden="true" />
                  {t('databases.showConnection')}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    rotate(database.name);
                  }}
                  disabled={busy}
                  aria-label={t('databases.rotate', { name: database.name })}
                  className="flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-surface-raised hover:text-accent disabled:opacity-60"
                >
                  <KeyRound className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  onClick={() => {
                    drop(database.name);
                  }}
                  disabled={busy}
                  aria-label={t('databases.remove', { name: database.name })}
                  className="flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-surface-raised hover:text-error disabled:opacity-60"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>

              {shown === database.name && connection !== null && (
                <div className="space-y-2 rounded-lg border border-accent bg-accent-subtle p-3">
                  <p className="text-xs text-app">{t('databases.connectionHint')}</p>
                  <div className="flex items-center gap-2">
                    <code className="min-w-0 flex-1 truncate rounded-lg border border-app bg-app px-2 py-1 font-mono text-xs text-app">
                      {connection.url}
                    </code>
                    <CopyButton value={connection.url} label={t('databases.copyUrl')} />
                  </div>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

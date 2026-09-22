import { Hammer, Loader2, Play, Plus, Save, Square, Trash2 } from 'lucide-react';
import { useCallback, useEffect, useState, type ReactNode, type SyntheticEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import type { TranslationKey } from '../../i18n/keys';
import { ApiError } from '../../lib/api';
import { readableSize } from '../storage/size';
import { Terminal } from './Terminal';
import {
  createWorkspace,
  deleteWorkspace,
  fetchChanges,
  fetchWorkspaces,
  saveWorkspace,
  startWorkspace,
  stopWorkspace,
  type Change,
  type Workspace,
  type WorkspaceState,
} from './api';

const HTTP_CONFLICT = 409;
const NAME_MAX_LENGTH = 63;
const DEFAULT_IMAGE = 'python:3.14-slim';

const STATE_CLASS: Record<WorkspaceState, string> = {
  running: 'bg-success-subtle text-success',
  stopped: 'bg-surface-raised text-muted',
  failed: 'bg-error-subtle text-error',
};

const stateLabel = (state: WorkspaceState): TranslationKey =>
  `workspaces.state.${state}` as TranslationKey;

/** Workspaces: a container with the code of a branch, and a terminal in it. */
export function WorkspacesPage(): ReactNode {
  const { t } = useTranslation();
  const [workspaces, setWorkspaces] = useState<Workspace[] | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  const [changes, setChanges] = useState<Change[]>([]);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState('');
  const [project, setProject] = useState('');
  const [branch, setBranch] = useState('main');
  const [image, setImage] = useState(DEFAULT_IMAGE);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);

  const reload = useCallback((): void => {
    setReloads((count) => count + 1);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetchWorkspaces(controller.signal)
      .then((found) => {
        setWorkspaces(found);
        setChosen((current) => current ?? found[0]?.name ?? null);
      })
      .catch(() => {
        if (!controller.signal.aborted) setError(t('workspaces.error.load'));
      });
    return () => {
      controller.abort();
    };
  }, [reloads, t]);

  const current = workspaces?.find((item) => item.name === chosen) ?? null;
  const running = current?.state === 'running';

  useEffect(() => {
    if (current?.state !== 'running') {
      return undefined;
    }
    const controller = new AbortController();
    fetchChanges(current.name, controller.signal)
      .then(setChanges)
      .catch(() => {
        // A workspace that stopped in the meantime simply has nothing to show.
      });
    return () => {
      controller.abort();
    };
  }, [current, reloads]);

  const act = (action: () => Promise<unknown>, failure: TranslationKey): void => {
    setBusy(true);
    setError(null);
    action()
      .then(() => {
        reload();
      })
      .catch((cause: unknown) => {
        const full = cause instanceof ApiError && cause.status === HTTP_CONFLICT;
        setError(t(full ? 'workspaces.error.limit' : failure));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const add = (event: SyntheticEvent<HTMLFormElement>): void => {
    event.preventDefault();
    const [owner = '', slug = ''] = project.split('/');
    if (owner === '' || slug === '') {
      setError(t('workspaces.error.project'));
      return;
    }
    act(
      () =>
        createWorkspace({
          name: name.trim().toLowerCase(),
          owner,
          slug,
          branch: branch.trim(),
          image: image.trim() || DEFAULT_IMAGE,
        }).then((made) => {
          setName('');
          setCreating(false);
          setChosen(made.name);
        }),
      'workspaces.error.create',
    );
  };

  const save = (): void => {
    if (current === null) return;
    act(
      () =>
        saveWorkspace(current.name, message.trim() || t('workspaces.defaultMessage')).then(() => {
          setMessage('');
        }),
      'workspaces.error.save',
    );
  };

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight text-app">
            <Hammer className="h-6 w-6 text-accent" aria-hidden="true" />
            {t('workspaces.title')}
          </h1>
          <p className="mt-1 text-sm text-muted">{t('workspaces.subtitle')}</p>
        </div>
        <button
          type="button"
          onClick={() => {
            setCreating((open) => !open);
          }}
          className="flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          {t('workspaces.create')}
        </button>
      </div>

      {error !== null && <ErrorBanner message={error} />}

      {creating && (
        <form
          className="flex flex-wrap items-end gap-3 rounded-xl border border-app bg-surface p-4 shadow-app-sm"
          onSubmit={add}
        >
          <div className="min-w-40 flex-1">
            <label htmlFor="workspaceName" className="mb-1.5 block text-sm font-medium text-app">
              {t('workspaces.field.name')}
            </label>
            <input
              id="workspaceName"
              type="text"
              required
              maxLength={NAME_MAX_LENGTH}
              value={name}
              onChange={(event) => {
                setName(event.target.value);
              }}
              placeholder="moj-workspaces"
              className="w-full rounded-lg border border-app bg-app px-3 py-2 font-mono text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
            />
          </div>
          <div className="min-w-48 flex-1">
            <label htmlFor="workspaceProject" className="mb-1.5 block text-sm font-medium text-app">
              {t('workspaces.field.project')}
            </label>
            <input
              id="workspaceProject"
              type="text"
              required
              value={project}
              onChange={(event) => {
                setProject(event.target.value);
              }}
              placeholder="bartek/moj-projekt"
              className="w-full rounded-lg border border-app bg-app px-3 py-2 font-mono text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
            />
          </div>
          <div className="min-w-32">
            <label htmlFor="workspaceBranch" className="mb-1.5 block text-sm font-medium text-app">
              {t('workspaces.field.branch')}
            </label>
            <input
              id="workspaceBranch"
              type="text"
              required
              value={branch}
              onChange={(event) => {
                setBranch(event.target.value);
              }}
              className="w-full rounded-lg border border-app bg-app px-3 py-2 font-mono text-sm text-app focus:border-accent focus:outline-none"
            />
          </div>
          <div className="min-w-40">
            <label htmlFor="workspaceImage" className="mb-1.5 block text-sm font-medium text-app">
              {t('workspaces.field.image')}
            </label>
            <input
              id="workspaceImage"
              type="text"
              value={image}
              onChange={(event) => {
                setImage(event.target.value);
              }}
              className="w-full rounded-lg border border-app bg-app px-3 py-2 font-mono text-sm text-app focus:border-accent focus:outline-none"
            />
          </div>
          <button
            type="submit"
            disabled={busy}
            className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
          >
            {t('workspaces.confirm')}
          </button>
        </form>
      )}

      {workspaces === null && error === null && (
        <p className="flex items-center gap-2 text-sm text-muted">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          {t('workspaces.loading')}
        </p>
      )}

      {workspaces !== null && workspaces.length === 0 && (
        <p className="rounded-xl border border-app bg-surface px-4 py-6 text-center text-sm text-muted">
          {t('workspaces.empty')}
        </p>
      )}

      {workspaces !== null && workspaces.length > 0 && (
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
          <ul className="w-full shrink-0 space-y-1.5 lg:w-64">
            {workspaces.map((item) => (
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
                  <p className="truncate font-mono text-sm text-app">{item.name}</p>
                  <p className="mt-0.5 truncate text-xs text-muted">
                    {item.project} · {item.branch}
                  </p>
                </button>
              </li>
            ))}
          </ul>

          {current !== null && (
            <div className="min-w-0 flex-1 space-y-3">
              <div className="flex flex-wrap items-center gap-2 rounded-xl border border-app bg-surface p-4 shadow-app-sm">
                <div className="min-w-0 flex-1">
                  <h2 className="truncate font-mono text-lg text-app">{current.name}</h2>
                  <p className="mt-0.5 truncate font-mono text-xs text-muted">{current.image}</p>
                </div>
                <span className={`rounded-full px-2 py-0.5 text-xs ${STATE_CLASS[current.state]}`}>
                  {t(stateLabel(current.state))}
                </span>
                {running ? (
                  <button
                    type="button"
                    onClick={() => {
                      act(() => stopWorkspace(current.name), 'workspaces.error.create');
                    }}
                    disabled={busy}
                    className="flex items-center gap-1.5 rounded-lg border border-app px-3 py-2 text-sm text-muted hover:bg-surface-raised hover:text-app disabled:opacity-60"
                  >
                    <Square className="h-4 w-4" aria-hidden="true" />
                    {t('workspaces.stop')}
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => {
                      act(() => startWorkspace(current.name), 'workspaces.error.start');
                    }}
                    disabled={busy}
                    className="flex items-center gap-1.5 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
                  >
                    <Play className="h-4 w-4" aria-hidden="true" />
                    {t('workspaces.start')}
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => {
                    setChosen(null);
                    act(() => deleteWorkspace(current.name), 'workspaces.error.create');
                  }}
                  disabled={busy}
                  aria-label={t('workspaces.remove', { name: current.name })}
                  className="flex h-9 w-9 items-center justify-center rounded-md text-muted hover:bg-surface-raised hover:text-error disabled:opacity-60"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>

              {current.lastError !== '' && <ErrorBanner message={current.lastError} />}

              {running && <Terminal workspace={current.name} onClosed={reload} />}

              {running && (
                <div className="space-y-3 rounded-xl border border-app bg-surface p-4 shadow-app-sm">
                  <h3 className="text-sm font-semibold text-app">
                    {changes.length === 0
                      ? t('workspaces.noChanges')
                      : t('workspaces.changeCount', { count: changes.length })}
                  </h3>
                  {changes.length > 0 && (
                    <ul className="divide-y divide-app overflow-hidden rounded-lg border border-app">
                      {changes.map((change) => (
                        <li
                          key={change.path}
                          className="flex items-center gap-3 px-3 py-2 font-mono text-xs"
                        >
                          <span
                            className={change.removed ? 'text-error' : 'text-success'}
                            aria-hidden="true"
                          >
                            {change.removed ? '−' : '+'}
                          </span>
                          <span className="min-w-0 flex-1 truncate text-app">{change.path}</span>
                          {!change.removed && (
                            <span className="text-muted">{readableSize(change.size)}</span>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                  <div className="flex flex-wrap items-end gap-3">
                    <div className="min-w-56 flex-1">
                      <label
                        htmlFor="saveMessage"
                        className="mb-1.5 block text-sm font-medium text-app"
                      >
                        {t('workspaces.field.message')}
                      </label>
                      <input
                        id="saveMessage"
                        type="text"
                        value={message}
                        onChange={(event) => {
                          setMessage(event.target.value);
                        }}
                        placeholder={t('workspaces.defaultMessage')}
                        className="w-full rounded-lg border border-app bg-app px-3 py-2 text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
                      />
                    </div>
                    <button
                      type="button"
                      onClick={save}
                      disabled={busy || changes.length === 0}
                      className="flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
                    >
                      <Save className="h-4 w-4" aria-hidden="true" />
                      {t('workspaces.save')}
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

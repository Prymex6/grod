import {
  CircleCheck,
  CircleSlash,
  CircleX,
  ExternalLink,
  Loader2,
  Play,
  Plus,
  Server,
  Square,
  Trash2,
} from 'lucide-react';
import { useEffect, useState, type ReactNode, type SyntheticEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import type { TranslationKey } from '../../i18n/keys';
import { ApiError } from '../../lib/api';
import {
  createApplication,
  deleteApplication,
  fetchApplicationLog,
  fetchApplications,
  fetchEngine,
  startApplication,
  stopApplication,
  type Application,
  type AppState,
} from './api';

const HTTP_CONFLICT = 409;
const NAME_MAX_LENGTH = 63;
const DEFAULT_MEMORY = 256;
const DEFAULT_CPUS = 0.5;

const STATE_ICON = {
  stopped: CircleSlash,
  running: CircleCheck,
  failed: CircleX,
} as const satisfies Record<AppState, typeof CircleCheck>;

const STATE_COLOUR = {
  stopped: 'text-muted',
  running: 'text-success',
  failed: 'text-error',
} as const satisfies Record<AppState, string>;

const STATE_KEYS = {
  stopped: 'apps.state.stopped',
  running: 'apps.state.running',
  failed: 'apps.state.failed',
} as const satisfies Record<AppState, TranslationKey>;

/** Applications the account runs as containers. */
export function AppsPage(): ReactNode {
  const { t } = useTranslation();
  const [applications, setApplications] = useState<Application[] | null>(null);
  const [engine, setEngine] = useState<boolean | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState('');
  const [image, setImage] = useState('');
  const [command, setCommand] = useState('');
  const [port, setPort] = useState('');
  const [chosen, setChosen] = useState<string | null>(null);
  const [log, setLog] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([fetchApplications(controller.signal), fetchEngine(controller.signal)])
      .then(([found, status]) => {
        setApplications(found);
        setEngine(status.available);
      })
      .catch(() => {
        if (!controller.signal.aborted) setError(t('apps.error.load'));
      });
    return () => {
      controller.abort();
    };
  }, [reloads, t]);

  useEffect(() => {
    if (chosen === null) return undefined;
    const controller = new AbortController();
    fetchApplicationLog(chosen, controller.signal)
      .then((answer) => {
        setLog(answer.log);
      })
      .catch(() => {
        setLog('');
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
    createApplication({
      name: name.trim().toLowerCase(),
      image: image.trim(),
      command: command.trim(),
      environment: {},
      port: port === '' ? null : Number(port),
      memoryMb: DEFAULT_MEMORY,
      cpus: DEFAULT_CPUS,
    })
      .then(() => {
        setName('');
        setImage('');
        setCommand('');
        setPort('');
        setCreating(false);
        reload();
      })
      .catch((cause: unknown) => {
        const taken = cause instanceof ApiError && cause.status === HTTP_CONFLICT;
        setError(t(taken ? 'apps.error.taken' : 'apps.error.create'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  // Every action answers with the application, except removing it.
  const act = (action: (appName: string) => Promise<unknown>, appName: string): void => {
    setBusy(true);
    setError(null);
    action(appName)
      .then(reload)
      .catch(() => {
        setError(t('apps.error.action'));
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
            <Server className="h-6 w-6 text-accent" aria-hidden="true" />
            {t('apps.title')}
          </h1>
          <p className="mt-1 text-sm text-muted">{t('apps.subtitle')}</p>
        </div>
        <button
          type="button"
          onClick={() => {
            setCreating((open) => !open);
          }}
          className="flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          {t('apps.create')}
        </button>
      </div>

      {engine === false && (
        <div className="rounded-xl border border-app bg-warning-subtle px-4 py-3 text-sm text-app">
          {t('apps.noEngine')}
        </div>
      )}

      {error !== null && <ErrorBanner message={error} />}

      {creating && (
        <form
          className="space-y-3 rounded-xl border border-app bg-surface p-4 shadow-app-sm"
          onSubmit={add}
        >
          <div className="flex flex-wrap gap-3">
            <div className="min-w-40 flex-1">
              <label htmlFor="appName" className="mb-1.5 block text-sm font-medium text-app">
                {t('apps.field.name')}
              </label>
              <input
                id="appName"
                type="text"
                required
                maxLength={NAME_MAX_LENGTH}
                value={name}
                onChange={(event) => {
                  setName(event.target.value);
                }}
                placeholder="moja-apka"
                className="w-full rounded-lg border border-app bg-app px-3 py-2 font-mono text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
              />
            </div>
            <div className="min-w-48 flex-1">
              <label htmlFor="appImage" className="mb-1.5 block text-sm font-medium text-app">
                {t('apps.field.image')}
              </label>
              <input
                id="appImage"
                type="text"
                required
                value={image}
                onChange={(event) => {
                  setImage(event.target.value);
                }}
                placeholder="nginx:alpine"
                className="w-full rounded-lg border border-app bg-app px-3 py-2 font-mono text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
              />
            </div>
            <div className="w-28">
              <label htmlFor="appPort" className="mb-1.5 block text-sm font-medium text-app">
                {t('apps.field.port')}
              </label>
              <input
                id="appPort"
                type="number"
                min={1}
                max={65535}
                value={port}
                onChange={(event) => {
                  setPort(event.target.value);
                }}
                placeholder="80"
                className="w-full rounded-lg border border-app bg-app px-3 py-2 font-mono text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
              />
            </div>
          </div>
          <div>
            <label htmlFor="appCommand" className="mb-1.5 block text-sm font-medium text-app">
              {t('apps.field.command')}
            </label>
            <input
              id="appCommand"
              type="text"
              value={command}
              onChange={(event) => {
                setCommand(event.target.value);
              }}
              placeholder={t('apps.field.commandHint')}
              className="w-full rounded-lg border border-app bg-app px-3 py-2 font-mono text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
            />
          </div>
          <button
            type="submit"
            disabled={busy}
            className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
          >
            {t('apps.create')}
          </button>
        </form>
      )}

      {applications === null && error === null && (
        <p className="flex items-center gap-2 text-sm text-muted">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          {t('apps.loading')}
        </p>
      )}

      {applications !== null && applications.length === 0 && (
        <p className="rounded-xl border border-app bg-surface px-4 py-6 text-center text-sm text-muted">
          {t('apps.empty')}
        </p>
      )}

      {applications !== null && applications.length > 0 && (
        <ul className="divide-y divide-app overflow-hidden rounded-xl border border-app bg-surface shadow-app-sm">
          {applications.map((application) => {
            const Icon = STATE_ICON[application.state];
            return (
              <li key={application.id} className="space-y-2 px-4 py-3">
                <div className="flex flex-wrap items-center gap-3">
                  <Icon
                    className={`h-4 w-4 shrink-0 ${STATE_COLOUR[application.state]}`}
                    aria-hidden="true"
                  />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-mono text-sm font-medium text-app">
                      {application.name}
                    </p>
                    <p className="mt-0.5 truncate font-mono text-xs text-muted">
                      {application.image}
                      {application.command !== '' && ` · ${application.command}`}
                    </p>
                  </div>
                  <span className="shrink-0 text-xs text-muted">
                    {t(STATE_KEYS[application.state])}
                  </span>
                  {application.url !== null && (
                    <a
                      href={application.url}
                      target="_blank"
                      rel="noreferrer"
                      className="flex shrink-0 items-center gap-1 font-mono text-xs text-accent hover:underline"
                    >
                      {application.url}
                      <ExternalLink className="h-3 w-3" aria-hidden="true" />
                    </a>
                  )}
                  <div className="flex shrink-0 gap-1">
                    <button
                      type="button"
                      onClick={() => {
                        act(startApplication, application.name);
                      }}
                      disabled={busy}
                      aria-label={t('apps.start', { name: application.name })}
                      className="flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-surface-raised hover:text-success disabled:opacity-60"
                    >
                      <Play className="h-4 w-4" />
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        act(stopApplication, application.name);
                      }}
                      disabled={busy}
                      aria-label={t('apps.stop', { name: application.name })}
                      className="flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-surface-raised hover:text-app disabled:opacity-60"
                    >
                      <Square className="h-4 w-4" />
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setChosen(chosen === application.name ? null : application.name);
                      }}
                      aria-pressed={chosen === application.name}
                      className="rounded-md px-2 text-xs text-muted hover:bg-surface-raised hover:text-app"
                    >
                      {t('apps.showLog')}
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        act(deleteApplication, application.name);
                      }}
                      disabled={busy}
                      aria-label={t('apps.remove', { name: application.name })}
                      className="flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-surface-raised hover:text-error disabled:opacity-60"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>

                {application.lastError !== '' && (
                  <p className="rounded-lg bg-error-subtle px-3 py-2 font-mono text-xs text-app">
                    {application.lastError}
                  </p>
                )}

                {chosen === application.name && (
                  <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-app p-3 font-mono text-xs text-app">
                    {log || t('apps.noLog')}
                  </pre>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

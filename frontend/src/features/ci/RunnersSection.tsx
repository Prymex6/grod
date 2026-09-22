import { Cpu, Plus, Trash2 } from 'lucide-react';
import { useEffect, useState, type ReactNode, type SyntheticEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { CopyButton } from '../../components/ui/CopyButton';
import { ErrorBanner } from '../../components/ui/ErrorBanner';
import type { Project } from '../projects/api';
import { fetchRunners, registerRunner, removeRunner, type Runner } from './api';

const NAME_MAX_LENGTH = 100;

/** Machines that take jobs of this project, and the token each one signs in with. */
export function RunnersSection({ project }: { project: Project }): ReactNode {
  const { t, i18n } = useTranslation();
  const [runners, setRunners] = useState<Runner[]>([]);
  const [name, setName] = useState('');
  const [tags, setTags] = useState('');
  const [token, setToken] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    fetchRunners(project.ownerLogin, project.slug, controller.signal)
      .then(setRunners)
      .catch(() => {
        if (!controller.signal.aborted) setError(t('ci.runners.error.load'));
      });
    return () => {
      controller.abort();
    };
  }, [project.ownerLogin, project.slug, reloads, t]);

  const reload = (): void => {
    setReloads((count) => count + 1);
  };

  const add = (event: SyntheticEvent<HTMLFormElement>): void => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    registerRunner(project.ownerLogin, project.slug, { name: name.trim(), tags: tags.trim() })
      .then((created) => {
        setName('');
        setTags('');
        setToken(created.token);
        reload();
      })
      .catch(() => {
        setError(t('ci.runners.error.add'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const drop = (runnerId: string): void => {
    setBusy(true);
    removeRunner(project.ownerLogin, project.slug, runnerId)
      .then(reload)
      .catch(() => {
        setError(t('ci.runners.error.add'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  return (
    <section aria-labelledby="runners-heading" className="space-y-4">
      <div>
        <h2
          id="runners-heading"
          className="text-sm font-semibold uppercase tracking-wider text-muted"
        >
          {t('ci.runners.heading')}
        </h2>
        <p className="mt-1 text-sm text-muted">{t('ci.runners.description')}</p>
      </div>

      {error !== null && <ErrorBanner message={error} />}

      {token !== null && (
        <div className="space-y-2 rounded-xl border border-accent bg-accent-subtle p-4">
          <p className="text-sm text-app">{t('ci.runners.tokenOnce')}</p>
          <div className="flex items-center gap-2">
            <code className="min-w-0 flex-1 truncate rounded-lg border border-app bg-app px-2 py-1 font-mono text-xs text-app">
              {token}
            </code>
            <CopyButton value={token} label={t('ci.runners.copyToken')} />
          </div>
          <p className="font-mono text-xs text-muted">
            grod-runner --url {window.location.origin}/api/v1 --token …
          </p>
        </div>
      )}

      {runners.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-app bg-surface shadow-app-sm">
          <ul className="divide-y divide-app">
            {runners.map((runner) => (
              <li key={runner.id} className="flex items-center gap-3 px-4 py-3">
                <Cpu className="h-4 w-4 shrink-0 text-muted" aria-hidden="true" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm text-app">{runner.name}</p>
                  <p className="truncate text-xs text-muted">
                    {runner.tags === '' ? t('ci.runners.noTags') : runner.tags}
                    {' · '}
                    {runner.lastSeenAt === null
                      ? t('ci.runners.neverSeen')
                      : t('ci.runners.lastSeen', {
                          date: new Date(runner.lastSeenAt).toLocaleString(
                            i18n.resolvedLanguage ?? 'pl',
                          ),
                        })}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    drop(runner.id);
                  }}
                  disabled={busy}
                  aria-label={t('ci.runners.remove', { name: runner.name })}
                  className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted hover:bg-surface-raised hover:text-error disabled:opacity-60"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <form className="flex flex-wrap items-end gap-3" onSubmit={add}>
        <div className="min-w-48 flex-1">
          <label htmlFor="runnerName" className="mb-1.5 block text-sm font-medium text-app">
            {t('ci.runners.field.name')}
          </label>
          <input
            id="runnerName"
            type="text"
            required
            maxLength={NAME_MAX_LENGTH}
            value={name}
            onChange={(event) => {
              setName(event.target.value);
            }}
            placeholder="serwer-domowy"
            className="w-full rounded-lg border border-app bg-app px-3 py-2 text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
          />
        </div>
        <div className="min-w-40 flex-1">
          <label htmlFor="runnerTags" className="mb-1.5 block text-sm font-medium text-app">
            {t('ci.runners.field.tags')}
          </label>
          <input
            id="runnerTags"
            type="text"
            maxLength={200}
            value={tags}
            onChange={(event) => {
              setTags(event.target.value);
            }}
            placeholder="shell, linux"
            className="w-full rounded-lg border border-app bg-app px-3 py-2 text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
          />
        </div>
        <button
          type="submit"
          disabled={busy}
          className="flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          {t('ci.runners.add')}
        </button>
      </form>
    </section>
  );
}

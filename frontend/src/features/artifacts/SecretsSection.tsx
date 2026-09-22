import { KeyRound, Lock, Plus, Trash2 } from 'lucide-react';
import { useEffect, useState, type ReactNode, type SyntheticEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import type { Project } from '../projects/api';
import { fetchSecrets, removeSecret, setSecret, type Secret } from './api';

const NAME_MAX_LENGTH = 100;
const VALUE_MAX_LENGTH = 10_000;

/** Values a project keeps out of its repository and hands to its jobs. */
export function SecretsSection({ project }: { project: Project }): ReactNode {
  const { t } = useTranslation();
  const [secrets, setSecrets] = useState<Secret[]>([]);
  const [name, setName] = useState('');
  const [value, setValue] = useState('');
  const [masked, setMasked] = useState(true);
  const [protectedOnly, setProtectedOnly] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);

  const owner = project.ownerLogin;
  const slug = project.slug;

  useEffect(() => {
    const controller = new AbortController();
    fetchSecrets(owner, slug, controller.signal)
      .then(setSecrets)
      .catch(() => {
        if (!controller.signal.aborted) setError(t('artifacts.secrets.error.load'));
      });
    return () => {
      controller.abort();
    };
  }, [owner, slug, reloads, t]);

  const reload = (): void => {
    setReloads((count) => count + 1);
  };

  const keep = (event: SyntheticEvent<HTMLFormElement>): void => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setSecret(owner, slug, {
      name: name.trim(),
      value,
      masked,
      protected: protectedOnly,
    })
      .then(() => {
        setName('');
        setValue('');
        reload();
      })
      .catch(() => {
        setError(t('artifacts.secrets.error.save'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const drop = (secretName: string): void => {
    setBusy(true);
    removeSecret(owner, slug, secretName)
      .then(reload)
      .catch(() => {
        setError(t('artifacts.secrets.error.save'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  return (
    <section aria-labelledby="secrets-heading" className="space-y-4">
      <div>
        <h2
          id="secrets-heading"
          className="text-sm font-semibold uppercase tracking-wider text-muted"
        >
          {t('artifacts.secrets.heading')}
        </h2>
        <p className="mt-1 text-sm text-muted">{t('artifacts.secrets.description')}</p>
      </div>

      {error !== null && <ErrorBanner message={error} />}

      {secrets.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-app bg-surface shadow-app-sm">
          <ul className="divide-y divide-app">
            {secrets.map((secret) => (
              <li key={secret.name} className="flex items-center gap-3 px-4 py-3">
                <KeyRound className="h-4 w-4 shrink-0 text-muted" aria-hidden="true" />
                <span className="min-w-0 flex-1 truncate font-mono text-sm text-app">
                  {secret.name}
                </span>
                {secret.masked && (
                  <span className="shrink-0 rounded-full bg-surface-raised px-2 py-0.5 text-xs text-muted">
                    {t('artifacts.secrets.masked')}
                  </span>
                )}
                {secret.protected && (
                  <span className="flex shrink-0 items-center gap-1 rounded-full bg-accent-subtle px-2 py-0.5 text-xs text-accent">
                    <Lock className="h-3 w-3" aria-hidden="true" />
                    {t('artifacts.secrets.protected')}
                  </span>
                )}
                <button
                  type="button"
                  onClick={() => {
                    drop(secret.name);
                  }}
                  disabled={busy}
                  aria-label={t('artifacts.secrets.remove', { name: secret.name })}
                  className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted hover:bg-surface-raised hover:text-error disabled:opacity-60"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <form className="space-y-3 rounded-xl border border-app bg-surface p-4" onSubmit={keep}>
        <div className="flex flex-wrap gap-3">
          <div className="min-w-40 flex-1">
            <label htmlFor="secretName" className="mb-1.5 block text-sm font-medium text-app">
              {t('artifacts.secrets.field.name')}
            </label>
            <input
              id="secretName"
              type="text"
              required
              maxLength={NAME_MAX_LENGTH}
              value={name}
              onChange={(event) => {
                setName(event.target.value.toUpperCase());
              }}
              placeholder="TOKEN_WDROZENIA"
              className="w-full rounded-lg border border-app bg-app px-3 py-2 font-mono text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
            />
          </div>
          <div className="min-w-48 flex-1">
            <label htmlFor="secretValue" className="mb-1.5 block text-sm font-medium text-app">
              {t('artifacts.secrets.field.value')}
            </label>
            <input
              id="secretValue"
              type="password"
              required
              maxLength={VALUE_MAX_LENGTH}
              value={value}
              onChange={(event) => {
                setValue(event.target.value);
              }}
              autoComplete="off"
              className="w-full rounded-lg border border-app bg-app px-3 py-2 font-mono text-sm text-app focus:border-accent focus:outline-none"
            />
          </div>
        </div>

        <div className="flex flex-wrap gap-4">
          <label className="flex items-center gap-2 text-sm text-app">
            <input
              type="checkbox"
              checked={masked}
              onChange={(event) => {
                setMasked(event.target.checked);
              }}
              className="h-4 w-4 accent-[var(--accent)]"
            />
            {t('artifacts.secrets.field.masked')}
          </label>
          <label className="flex items-center gap-2 text-sm text-app">
            <input
              type="checkbox"
              checked={protectedOnly}
              onChange={(event) => {
                setProtectedOnly(event.target.checked);
              }}
              className="h-4 w-4 accent-[var(--accent)]"
            />
            {t('artifacts.secrets.field.protected')}
          </label>
        </div>

        <button
          type="submit"
          disabled={busy}
          className="flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          {t('artifacts.secrets.add')}
        </button>
      </form>
    </section>
  );
}

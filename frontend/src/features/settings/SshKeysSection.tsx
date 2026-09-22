import { KeySquare, Trash2 } from 'lucide-react';
import { useState, type ReactNode, type SyntheticEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import { ApiError } from '../../lib/api';
import { addSshKey, removeSshKey, type SshKey } from './api';

const HTTP_BAD_REQUEST = 400;
const HTTP_CONFLICT = 409;

interface SshKeysSectionProps {
  keys: SshKey[];
  onChanged: () => void;
}

/** Public keys that let Git reach the repositories over SSH. */
export function SshKeysSection({ keys, onChanged }: SshKeysSectionProps): ReactNode {
  const { t, i18n } = useTranslation();
  const [name, setName] = useState('');
  const [publicKey, setPublicKey] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const formatDate = (value: string): string =>
    new Date(value).toLocaleString(i18n.resolvedLanguage ?? 'pl');

  const add = (event: SyntheticEvent<HTMLFormElement>): void => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    addSshKey({ name, publicKey })
      .then(() => {
        setName('');
        setPublicKey('');
        onChanged();
      })
      .catch((cause: unknown) => {
        if (cause instanceof ApiError && cause.status === HTTP_CONFLICT) {
          setError(t('settings.sshKeys.duplicate'));
        } else if (cause instanceof ApiError && cause.status === HTTP_BAD_REQUEST) {
          setError(t('settings.sshKeys.invalid'));
        } else {
          setError(t('settings.error.generic'));
        }
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const remove = (id: string): void => {
    setBusy(true);
    setError(null);
    removeSshKey(id)
      .then(onChanged)
      .catch(() => {
        setError(t('settings.error.generic'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  return (
    <section aria-labelledby="ssh-keys-heading" className="space-y-4">
      <div>
        <h2
          id="ssh-keys-heading"
          className="text-sm font-semibold uppercase tracking-wider text-muted"
        >
          {t('settings.sshKeys.heading')}
        </h2>
        <p className="mt-1 text-sm text-muted">{t('settings.sshKeys.description')}</p>
      </div>

      {error !== null && <ErrorBanner message={error} />}

      <div className="overflow-hidden rounded-xl border border-app bg-surface shadow-app-sm">
        {keys.length === 0 ? (
          <p className="px-4 py-3 text-sm text-muted">{t('settings.sshKeys.empty')}</p>
        ) : (
          <ul className="divide-y divide-app">
            {keys.map((key) => (
              <li key={key.id} className="flex items-center justify-between gap-4 px-4 py-3">
                <div className="min-w-0">
                  <p className="flex items-center gap-2 text-sm text-app">
                    <KeySquare className="h-4 w-4 text-accent" aria-hidden="true" />
                    {key.name}
                  </p>
                  <p className="mt-0.5 truncate font-mono text-xs text-muted">{key.fingerprint}</p>
                  <p className="mt-0.5 text-xs text-muted">
                    {key.algorithm} ·{' '}
                    {t('settings.sshKeys.added', { date: formatDate(key.createdAt) })}
                    {key.lastUsedAt !== null &&
                      ` · ${t('settings.sshKeys.lastUsed', { date: formatDate(key.lastUsedAt) })}`}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    remove(key.id);
                  }}
                  disabled={busy}
                  aria-label={t('settings.sshKeys.remove', { name: key.name })}
                  className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted hover:bg-surface-raised hover:text-error disabled:opacity-60"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <form className="space-y-3" onSubmit={add}>
        <div>
          <label htmlFor="sshKeyName" className="mb-1.5 block text-sm font-medium text-app">
            {t('settings.sshKeys.name')}
          </label>
          <input
            id="sshKeyName"
            type="text"
            required
            maxLength={100}
            value={name}
            onChange={(event) => {
              setName(event.target.value);
            }}
            placeholder={t('settings.sshKeys.namePlaceholder')}
            className="w-full max-w-sm rounded-lg border border-app bg-app px-3 py-2 text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
          />
        </div>

        <div>
          <label htmlFor="sshKeyValue" className="mb-1.5 block text-sm font-medium text-app">
            {t('settings.sshKeys.key')}
          </label>
          <textarea
            id="sshKeyValue"
            required
            rows={3}
            value={publicKey}
            onChange={(event) => {
              setPublicKey(event.target.value);
            }}
            placeholder="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5... bartek@laptop"
            className="w-full rounded-lg border border-app bg-app px-3 py-2 font-mono text-xs text-app placeholder:text-muted focus:border-accent focus:outline-none"
          />
          <p className="mt-1.5 text-xs text-muted">{t('settings.sshKeys.keyHint')}</p>
        </div>

        <button
          type="submit"
          disabled={busy}
          className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
        >
          {t('settings.sshKeys.add')}
        </button>
      </form>
    </section>
  );
}

import { KeyRound, Trash2 } from 'lucide-react';
import { useState, type ReactNode, type SyntheticEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { CopyButton } from '../../components/ui/CopyButton';
import { ErrorBanner } from '../../components/ui/ErrorBanner';
import { createToken, removeToken, type AccessToken } from './api';

const SCOPES = ['repo:read', 'repo:write'] as const;

interface TokensSectionProps {
  tokens: AccessToken[];
  onChanged: () => void;
}

/** Access tokens: what Git asks for instead of a password. */
export function TokensSection({ tokens, onChanged }: TokensSectionProps): ReactNode {
  const { t, i18n } = useTranslation();
  const [name, setName] = useState('');
  const [scopes, setScopes] = useState<string[]>([...SCOPES]);
  const [created, setCreated] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const formatDate = (value: string): string =>
    new Date(value).toLocaleString(i18n.resolvedLanguage ?? 'pl');

  const add = (event: SyntheticEvent<HTMLFormElement>): void => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    createToken({ name, scopes })
      .then((token) => {
        setCreated(token.value);
        setName('');
        onChanged();
      })
      .catch(() => {
        setError(t('settings.tokens.addFailed'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const remove = (id: string): void => {
    setBusy(true);
    setError(null);
    removeToken(id)
      .then(onChanged)
      .catch(() => {
        setError(t('settings.error.generic'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  return (
    <section aria-labelledby="tokens-heading" className="space-y-4">
      <div>
        <h2
          id="tokens-heading"
          className="text-sm font-semibold uppercase tracking-wider text-muted"
        >
          {t('settings.tokens.heading')}
        </h2>
        <p className="mt-1 text-sm text-muted">{t('settings.tokens.description')}</p>
      </div>

      {error !== null && <ErrorBanner message={error} />}

      {created !== null && (
        <div className="space-y-2 rounded-lg bg-accent-subtle p-3">
          <p className="text-sm text-accent">{t('settings.tokens.copyNow')}</p>
          <div className="flex items-center gap-2">
            <code className="min-w-0 flex-1 truncate font-mono text-xs text-app">{created}</code>
            <CopyButton value={created} label={t('settings.tokens.copy')} />
          </div>
        </div>
      )}

      <div className="overflow-hidden rounded-xl border border-app bg-surface shadow-app-sm">
        {tokens.length === 0 ? (
          <p className="px-4 py-3 text-sm text-muted">{t('settings.tokens.empty')}</p>
        ) : (
          <ul className="divide-y divide-app">
            {tokens.map((token) => (
              <li key={token.id} className="flex items-center justify-between gap-4 px-4 py-3">
                <div className="min-w-0">
                  <p className="flex items-center gap-2 text-sm text-app">
                    <KeyRound className="h-4 w-4 text-accent" aria-hidden="true" />
                    {token.name}
                  </p>
                  <p className="mt-0.5 text-xs text-muted">
                    {token.scopes.join(', ')} ·{' '}
                    {t('settings.tokens.created', {
                      date: formatDate(token.createdAt),
                    })}
                    {token.lastUsedAt !== null &&
                      ` · ${t('settings.tokens.lastUsed', { date: formatDate(token.lastUsedAt) })}`}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    remove(token.id);
                  }}
                  disabled={busy}
                  aria-label={t('settings.tokens.remove', { name: token.name })}
                  className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted hover:bg-surface-raised hover:text-error disabled:opacity-60"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <form className="flex flex-wrap items-end gap-3" onSubmit={add}>
        <div className="min-w-48 flex-1">
          <label htmlFor="tokenName" className="mb-1.5 block text-sm font-medium text-app">
            {t('settings.tokens.name')}
          </label>
          <input
            id="tokenName"
            type="text"
            required
            maxLength={100}
            value={name}
            onChange={(event) => {
              setName(event.target.value);
            }}
            placeholder={t('settings.tokens.namePlaceholder')}
            className="w-full rounded-lg border border-app bg-app px-3 py-2 text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
          />
        </div>

        <fieldset className="flex items-end gap-3">
          <legend className="sr-only">{t('settings.tokens.scopes')}</legend>
          {SCOPES.map((scope) => (
            <label key={scope} className="flex items-center gap-2 pb-2 text-sm text-app">
              <input
                type="checkbox"
                checked={scopes.includes(scope)}
                onChange={(event) => {
                  setScopes((current) =>
                    event.target.checked
                      ? [...current, scope]
                      : current.filter((item) => item !== scope),
                  );
                }}
                className="accent-[var(--accent)]"
              />
              <code className="font-mono text-xs">{scope}</code>
            </label>
          ))}
        </fieldset>

        <button
          type="submit"
          disabled={busy || scopes.length === 0}
          className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
        >
          {t('settings.tokens.add')}
        </button>
      </form>
    </section>
  );
}

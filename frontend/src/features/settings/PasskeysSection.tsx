import { Fingerprint, Trash2 } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import { addPasskey, removePasskey, type Passkey } from './api';

const PRIMARY_BUTTON =
  'flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60';

interface PasskeysSectionProps {
  passkeys: Passkey[];
  onChanged: () => void;
}

/** Passkeys let people sign in with a fingerprint, face or security key. */
export function PasskeysSection({ passkeys, onChanged }: PasskeysSectionProps): ReactNode {
  const { t, i18n } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const formatDate = (value: string): string =>
    new Date(value).toLocaleString(i18n.resolvedLanguage ?? 'pl');

  const run = (action: () => Promise<void>, message: string): void => {
    setBusy(true);
    setError(null);
    action()
      .then(onChanged)
      .catch(() => {
        setError(message);
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const add = (): void => {
    run(async () => {
      await addPasskey(t('settings.passkeys.defaultLabel'));
    }, t('settings.passkeys.addFailed'));
  };

  const remove = (id: string): void => {
    run(async () => {
      await removePasskey(id);
    }, t('settings.error.generic'));
  };

  return (
    <section aria-labelledby="passkeys-heading" className="space-y-4">
      <div>
        <h2
          id="passkeys-heading"
          className="text-sm font-semibold uppercase tracking-wider text-muted"
        >
          {t('settings.passkeys.heading')}
        </h2>
        <p className="mt-1 text-sm text-muted">{t('settings.passkeys.description')}</p>
      </div>

      {error !== null && <ErrorBanner message={error} />}

      <div className="overflow-hidden rounded-xl border border-app bg-surface shadow-app-sm">
        {passkeys.length === 0 ? (
          <p className="px-4 py-3 text-sm text-muted">{t('settings.passkeys.empty')}</p>
        ) : (
          <ul className="divide-y divide-app">
            {passkeys.map((passkey) => (
              <li key={passkey.id} className="flex items-center justify-between gap-4 px-4 py-3">
                <div className="min-w-0">
                  <p className="flex items-center gap-2 text-sm text-app">
                    <Fingerprint className="h-4 w-4 text-accent" aria-hidden="true" />
                    {passkey.label}
                  </p>
                  <p className="mt-0.5 text-xs text-muted">
                    {t('settings.passkeys.added', { date: formatDate(passkey.createdAt) })}
                    {passkey.lastUsedAt !== null &&
                      ` · ${t('settings.passkeys.lastUsed', { date: formatDate(passkey.lastUsedAt) })}`}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    remove(passkey.id);
                  }}
                  disabled={busy}
                  aria-label={t('settings.passkeys.remove', { label: passkey.label })}
                  className="flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-surface-raised hover:text-error disabled:opacity-60"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <button type="button" onClick={add} disabled={busy} className={PRIMARY_BUTTON}>
        <Fingerprint className="h-4 w-4" aria-hidden="true" />
        {t('settings.passkeys.add')}
      </button>
    </section>
  );
}

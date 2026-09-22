import { AppWindow, Trash2 } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import { revokeAuthorization, type Authorization } from './api';

const SCOPE_KEYS = {
  openid: 'consent.scope.openid',
  profile: 'consent.scope.profile',
  email: 'consent.scope.email',
  offline_access: 'consent.scope.offline_access',
} as const;

const isKnownScope = (scope: string): scope is keyof typeof SCOPE_KEYS => scope in SCOPE_KEYS;

interface ApplicationsSectionProps {
  authorizations: Authorization[];
  onChanged: () => void;
}

/** Applications allowed to sign this account in, and a way to take that back. */
export function ApplicationsSection({
  authorizations,
  onChanged,
}: ApplicationsSectionProps): ReactNode {
  const { t, i18n } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const revoke = (clientId: string): void => {
    setBusy(true);
    setError(null);
    revokeAuthorization(clientId)
      .then(onChanged)
      .catch(() => {
        setError(t('settings.error.generic'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  return (
    <section aria-labelledby="applications-heading" className="space-y-4">
      <div>
        <h2
          id="applications-heading"
          className="text-sm font-semibold uppercase tracking-wider text-muted"
        >
          {t('settings.applications.heading')}
        </h2>
        <p className="mt-1 text-sm text-muted">{t('settings.applications.description')}</p>
      </div>

      {error !== null && <ErrorBanner message={error} />}

      <div className="overflow-hidden rounded-xl border border-app bg-surface shadow-app-sm">
        {authorizations.length === 0 ? (
          <p className="px-4 py-3 text-sm text-muted">{t('settings.applications.empty')}</p>
        ) : (
          <ul className="divide-y divide-app">
            {authorizations.map((authorization) => (
              <li
                key={authorization.clientId}
                className="flex items-start justify-between gap-4 px-4 py-3"
              >
                <div className="min-w-0">
                  <p className="flex items-center gap-2 text-sm text-app">
                    <AppWindow className="h-4 w-4 text-accent" aria-hidden="true" />
                    {authorization.name}
                  </p>
                  <p className="mt-0.5 text-xs text-muted">
                    {t('settings.applications.grantedAt', {
                      date: new Date(authorization.grantedAt).toLocaleString(
                        i18n.resolvedLanguage ?? 'pl',
                      ),
                    })}
                  </p>
                  <ul className="mt-1 text-xs text-muted">
                    {authorization.scopes.map((scope) => (
                      <li key={scope}>· {isKnownScope(scope) ? t(SCOPE_KEYS[scope]) : scope}</li>
                    ))}
                  </ul>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    revoke(authorization.clientId);
                  }}
                  disabled={busy}
                  aria-label={t('settings.applications.revoke', { name: authorization.name })}
                  className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted hover:bg-surface-raised hover:text-error disabled:opacity-60"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

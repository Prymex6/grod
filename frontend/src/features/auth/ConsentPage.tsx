import { Check, Loader2, ShieldCheck, X } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import { ApiError, NetworkError, getJson, postJson } from '../../lib/api';
import { AuthLayout } from './AuthLayout';

interface ConsentRequest {
  clientName: string;
  scopes: string[];
}

interface ConsentDecision {
  redirectTo: string;
}

const HTTP_UNAUTHORIZED = 401;
const HTTP_NOT_FOUND = 404;

type ErrorKind = 'expired' | 'network' | 'unknown';

const ERROR_KEYS = {
  expired: 'consent.error.expired',
  network: 'consent.error.network',
  unknown: 'consent.error.unknown',
} as const satisfies Record<ErrorKind, string>;

const SCOPE_KEYS = {
  openid: 'consent.scope.openid',
  profile: 'consent.scope.profile',
  email: 'consent.scope.email',
  offline_access: 'consent.scope.offline_access',
} as const;

const isKnownScope = (scope: string): scope is keyof typeof SCOPE_KEYS => scope in SCOPE_KEYS;

const classify = (error: unknown): ErrorKind => {
  if (error instanceof NetworkError) return 'network';
  if (error instanceof ApiError && error.status === HTTP_NOT_FOUND) return 'expired';
  return 'unknown';
};

/**
 * Consent screen of the OpenID Connect flow. Brama sends the browser here
 * with the handle of a pending request from an application.
 */
export function ConsentPage(): ReactNode {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const handle = params.get('request');
  const [request, setRequest] = useState<ConsentRequest | null>(null);
  const [deciding, setDeciding] = useState(false);
  const [error, setError] = useState<ErrorKind | null>(handle === null ? 'expired' : null);

  useEffect(() => {
    if (handle === null) return;
    const controller = new AbortController();

    getJson<ConsentRequest>(`/oauth/requests/${handle}`, controller.signal)
      .then(setRequest)
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        // Without a session there is nothing to consent with, so sign in first.
        if (cause instanceof ApiError && cause.status === HTTP_UNAUTHORIZED) {
          window.location.assign(`/login?next=${encodeURIComponent(window.location.href)}`);
          return;
        }
        setError(classify(cause));
      });

    return () => {
      controller.abort();
    };
  }, [handle]);

  const decide = (decision: 'approve' | 'deny'): void => {
    if (handle === null) return;
    setDeciding(true);
    setError(null);
    postJson<ConsentDecision>(`/oauth/requests/${handle}/${decision}`)
      .then((result) => {
        window.location.assign(result.redirectTo);
      })
      .catch((cause: unknown) => {
        setError(classify(cause));
        setDeciding(false);
      });
  };

  return (
    <AuthLayout
      heading={t('consent.title')}
      subtitle={request ? t('consent.intro', { client: request.clientName }) : ''}
      footer={t('login.footer')}
    >
      {error && <ErrorBanner message={t(ERROR_KEYS[error])} />}

      {!request && !error && (
        <p className="flex items-center gap-2 text-sm text-muted">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          {t('consent.loading')}
        </p>
      )}

      {request && (
        <div className="space-y-5">
          <div>
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wider text-muted">
              {t('consent.scopesHeading')}
            </h2>
            <ul className="space-y-2">
              {request.scopes.map((scope) => (
                <li key={scope} className="flex items-start gap-2 text-sm text-app">
                  <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-accent" aria-hidden="true" />
                  {isKnownScope(scope) ? t(SCOPE_KEYS[scope]) : scope}
                </li>
              ))}
            </ul>
          </div>

          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => {
                decide('deny');
              }}
              disabled={deciding}
              className="flex flex-1 items-center justify-center gap-2 rounded-lg border border-app bg-app py-2.5 text-sm font-medium text-app hover:bg-surface-raised disabled:opacity-60"
            >
              <X className="h-4 w-4" aria-hidden="true" />
              {t('consent.deny')}
            </button>
            <button
              type="button"
              onClick={() => {
                decide('approve');
              }}
              disabled={deciding}
              className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-accent py-2.5 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
            >
              <Check className="h-4 w-4" aria-hidden="true" />
              {deciding ? t('consent.working') : t('consent.approve')}
            </button>
          </div>
        </div>
      )}
    </AuthLayout>
  );
}

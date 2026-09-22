import { Lock, Mail, User } from 'lucide-react';
import { useState, type ReactNode, type SyntheticEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import { ApiError, NetworkError, postJson } from '../../lib/api';
import { AuthLayout } from './AuthLayout';
import type { SignedIn } from './api';

const MIN_PASSWORD_LENGTH = 12;
const HTTP_CONFLICT = 409;
const HTTP_UNPROCESSABLE = 422;

const FIELD =
  'w-full rounded-lg border border-app bg-app py-2 pl-9 pr-3 text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none';

type ErrorKind = 'emailTaken' | 'invalid' | 'network' | 'unknown';

const ERROR_KEYS = {
  emailTaken: 'register.error.emailTaken',
  invalid: 'register.error.invalid',
  network: 'register.error.network',
  unknown: 'register.error.unknown',
} as const satisfies Record<ErrorKind, string>;

const classify = (error: unknown): ErrorKind => {
  if (error instanceof NetworkError) return 'network';
  if (error instanceof ApiError) {
    if (error.status === HTTP_CONFLICT) return 'emailTaken';
    if (error.status === HTTP_UNPROCESSABLE) return 'invalid';
  }
  return 'unknown';
};

/** Open registration: anyone may create an account on this instance. */
export function RegisterPage(): ReactNode {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<ErrorKind | null>(null);

  const onSubmit = (event: SyntheticEvent<HTMLFormElement>): void => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    postJson<SignedIn>('/auth/register', { email, displayName, password })
      .then(() => navigate('/'))
      .catch((cause: unknown) => {
        setError(classify(cause));
        setSubmitting(false);
      });
  };

  return (
    <AuthLayout
      heading={t('register.title')}
      subtitle={t('register.subtitle')}
      footer={t('login.footer')}
    >
      {error && <ErrorBanner message={t(ERROR_KEYS[error])} />}

      <form className="space-y-4" onSubmit={onSubmit}>
        <div>
          <label htmlFor="displayName" className="mb-1.5 block text-sm font-medium text-app">
            {t('register.displayName')}
          </label>
          <div className="relative">
            <User
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted"
              aria-hidden="true"
            />
            <input
              id="displayName"
              type="text"
              required
              autoComplete="name"
              value={displayName}
              onChange={(event) => {
                setDisplayName(event.target.value);
              }}
              placeholder={t('register.displayNamePlaceholder')}
              className={FIELD}
            />
          </div>
        </div>

        <div>
          <label htmlFor="email" className="mb-1.5 block text-sm font-medium text-app">
            {t('login.email')}
          </label>
          <div className="relative">
            <Mail
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted"
              aria-hidden="true"
            />
            <input
              id="email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(event) => {
                setEmail(event.target.value);
              }}
              placeholder={t('login.emailPlaceholder')}
              className={FIELD}
            />
          </div>
        </div>

        <div>
          <label htmlFor="password" className="mb-1.5 block text-sm font-medium text-app">
            {t('login.password')}
          </label>
          <div className="relative">
            <Lock
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted"
              aria-hidden="true"
            />
            <input
              id="password"
              type="password"
              required
              minLength={MIN_PASSWORD_LENGTH}
              autoComplete="new-password"
              value={password}
              onChange={(event) => {
                setPassword(event.target.value);
              }}
              placeholder={t('login.passwordPlaceholder')}
              className={FIELD}
            />
          </div>
          <p className="mt-1.5 text-xs text-muted">{t('register.passwordHint')}</p>
        </div>

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-lg bg-accent py-2.5 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
        >
          {submitting ? t('register.submitting') : t('register.submit')}
        </button>

        <p className="pt-2 text-center text-sm text-muted">
          {t('register.haveAccount')}{' '}
          <Link to="/login" className="font-medium text-accent hover:underline">
            {t('register.signIn')}
          </Link>
        </p>
      </form>
    </AuthLayout>
  );
}

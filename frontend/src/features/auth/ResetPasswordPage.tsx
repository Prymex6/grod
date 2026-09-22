import { Lock } from 'lucide-react';
import { useState, type ReactNode, type SyntheticEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useSearchParams } from 'react-router';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import { ApiError, NetworkError, postJson } from '../../lib/api';
import { AuthLayout } from './AuthLayout';

const MIN_PASSWORD_LENGTH = 12;
const HTTP_BAD_REQUEST = 400;

const FIELD =
  'w-full rounded-lg border border-app bg-app py-2 pl-9 pr-3 text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none';

type ErrorKind = 'expiredLink' | 'mismatch' | 'network' | 'unknown';

const ERROR_KEYS = {
  expiredLink: 'reset.error.expiredLink',
  mismatch: 'reset.error.mismatch',
  network: 'reset.error.network',
  unknown: 'reset.error.unknown',
} as const satisfies Record<ErrorKind, string>;

const classify = (error: unknown): ErrorKind => {
  if (error instanceof NetworkError) return 'network';
  if (error instanceof ApiError && error.status === HTTP_BAD_REQUEST) return 'expiredLink';
  return 'unknown';
};

/** Sets a new password from the link in the email. */
export function ResetPasswordPage(): ReactNode {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const token = params.get('token');
  const [password, setPassword] = useState('');
  const [repeated, setRepeated] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<ErrorKind | null>(token === null ? 'expiredLink' : null);

  const onSubmit = (event: SyntheticEvent<HTMLFormElement>): void => {
    event.preventDefault();
    if (token === null) return;
    if (password !== repeated) {
      setError('mismatch');
      return;
    }

    setSubmitting(true);
    setError(null);
    postJson<undefined>('/auth/password/reset', { token, password })
      .then(() => navigate('/login'))
      .catch((cause: unknown) => {
        setError(classify(cause));
        setSubmitting(false);
      });
  };

  return (
    <AuthLayout
      heading={t('reset.title')}
      subtitle={t('reset.subtitle')}
      footer={t('login.footer')}
    >
      {error !== null && <ErrorBanner message={t(ERROR_KEYS[error])} />}

      <form className="space-y-4" onSubmit={onSubmit}>
        {(['password', 'repeat'] as const).map((field) => (
          <div key={field}>
            <label htmlFor={field} className="mb-1.5 block text-sm font-medium text-app">
              {field === 'password' ? t('reset.newPassword') : t('reset.repeatPassword')}
            </label>
            <div className="relative">
              <Lock
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted"
                aria-hidden="true"
              />
              <input
                id={field}
                type="password"
                required
                minLength={MIN_PASSWORD_LENGTH}
                autoComplete="new-password"
                value={field === 'password' ? password : repeated}
                onChange={(event) => {
                  if (field === 'password') setPassword(event.target.value);
                  else setRepeated(event.target.value);
                }}
                placeholder={t('login.passwordPlaceholder')}
                className={FIELD}
              />
            </div>
          </div>
        ))}

        <p className="text-xs text-muted">{t('register.passwordHint')}</p>

        <button
          type="submit"
          disabled={submitting || token === null}
          className="w-full rounded-lg bg-accent py-2.5 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
        >
          {submitting ? t('reset.saving') : t('reset.submit')}
        </button>

        <Link
          to="/password/forgot"
          className="block text-center text-sm font-medium text-accent hover:underline"
        >
          {t('reset.askForNewLink')}
        </Link>
      </form>
    </AuthLayout>
  );
}

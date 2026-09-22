import { Mail, MailCheck } from 'lucide-react';
import { useState, type ReactNode, type SyntheticEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import { postJson } from '../../lib/api';
import { AuthLayout } from './AuthLayout';

const FIELD =
  'w-full rounded-lg border border-app bg-app py-2 pl-9 pr-3 text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none';

/** Asks Brama for a reset link. The answer never says whether the account exists. */
export function ForgotPasswordPage(): ReactNode {
  const { t } = useTranslation();
  const [email, setEmail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = (event: SyntheticEvent<HTMLFormElement>): void => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    postJson<undefined>('/auth/password/reset-request', { email })
      .then(() => {
        setSent(true);
      })
      .catch(() => {
        setError(t('forgot.error'));
      })
      .finally(() => {
        setSubmitting(false);
      });
  };

  return (
    <AuthLayout
      heading={t('forgot.title')}
      subtitle={sent ? t('forgot.sentSubtitle') : t('forgot.subtitle')}
      footer={t('login.footer')}
    >
      {error !== null && <ErrorBanner message={error} />}

      {sent ? (
        <div className="space-y-4">
          <p className="flex items-start gap-2 rounded-lg bg-success-subtle p-3 text-sm text-success">
            <MailCheck className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            {t('forgot.sent')}
          </p>
          <Link
            to="/login"
            className="block text-center text-sm font-medium text-accent hover:underline"
          >
            {t('forgot.backToSignIn')}
          </Link>
        </div>
      ) : (
        <form className="space-y-4" onSubmit={onSubmit}>
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

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-lg bg-accent py-2.5 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
          >
            {submitting ? t('forgot.sending') : t('forgot.submit')}
          </button>

          <Link
            to="/login"
            className="block text-center text-sm font-medium text-accent hover:underline"
          >
            {t('forgot.backToSignIn')}
          </Link>
        </form>
      )}
    </AuthLayout>
  );
}

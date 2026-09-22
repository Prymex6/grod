import { Eye, EyeOff, Fingerprint, KeyRound, Lock, Mail } from 'lucide-react';
import { useState, type ReactNode, type SyntheticEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useSearchParams } from 'react-router';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import { signInWithPasskey } from '../settings/api';
import { AuthLayout } from './AuthLayout';
import { OtpInput } from './OtpInput';
import { useSignIn, type SignInErrorKind } from './useSignIn';

const CODE_LENGTH = 6;
const emptyCode = (): string[] => Array.from({ length: CODE_LENGTH }, () => '');

const PRIMARY_BUTTON =
  'w-full rounded-lg bg-accent py-2.5 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60';
const FIELD =
  'w-full rounded-lg border border-app bg-app py-2 pl-9 text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none';

const ERROR_KEYS = {
  invalidCredentials: 'login.error.invalidCredentials',
  invalidCode: 'login.error.invalidCode',
  tooManyAttempts: 'login.error.tooManyAttempts',
  network: 'login.error.network',
  unknown: 'login.error.unknown',
} as const satisfies Record<SignInErrorKind, string>;

/** Sign-in screen of Brama: password, then a code when two-factor is on. */
export function LoginPage(): ReactNode {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  // An application may send people here to sign in before consenting.
  const next = params.get('next');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [code, setCode] = useState<string[]>(emptyCode);
  const [passkeyBusy, setPasskeyBusy] = useState(false);
  const [passkeyError, setPasskeyError] = useState<string | null>(null);

  const signedIn = (): void => {
    if (next === null) {
      void navigate('/');
      return;
    }
    window.location.assign(next);
  };

  const { submitting, error, pendingToken, submitCredentials, submitCode, reset } = useSignIn(
    () => {
      signedIn();
    },
  );
  const awaitingCode = pendingToken !== null;

  const onSubmitCredentials = (event: SyntheticEvent<HTMLFormElement>): void => {
    event.preventDefault();
    void submitCredentials(email, password);
  };

  const onSubmitCode = (event: SyntheticEvent<HTMLFormElement>): void => {
    event.preventDefault();
    void submitCode(code.join(''));
  };

  const usePasskey = (): void => {
    setPasskeyBusy(true);
    setPasskeyError(null);
    signInWithPasskey()
      .then(signedIn)
      .catch(() => {
        setPasskeyError(t('login.passkeyFailed'));
      })
      .finally(() => {
        setPasskeyBusy(false);
      });
  };

  const backToCredentials = (): void => {
    setCode(emptyCode());
    reset();
  };

  return (
    <AuthLayout
      heading={t('login.heading')}
      subtitle={awaitingCode ? t('login.subtitle.code') : t('login.subtitle.credentials')}
      footer={t('login.footer')}
    >
      {error && <ErrorBanner message={t(ERROR_KEYS[error])} />}
      {passkeyError !== null && <ErrorBanner message={passkeyError} />}

      {awaitingCode ? (
        <form className="space-y-4" onSubmit={onSubmitCode}>
          <div className="flex items-center gap-2 rounded-lg bg-accent-subtle p-3 text-sm text-accent">
            <KeyRound className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span>{t('login.codeHint')}</span>
          </div>

          <OtpInput
            value={code}
            onChange={setCode}
            label={t('login.codeLabel')}
            digitLabel={(position) =>
              t('login.codeDigitLabel', { index: position, total: CODE_LENGTH })
            }
          />

          <button type="submit" className={PRIMARY_BUTTON} disabled={submitting}>
            {submitting ? t('login.verifying') : t('login.codeVerify')}
          </button>

          <div className="flex items-center justify-between text-sm">
            <button
              type="button"
              onClick={backToCredentials}
              className="font-medium text-muted hover:text-app"
            >
              {t('login.back')}
            </button>
            <button type="button" className="font-medium text-accent hover:underline">
              {t('login.resend')}
            </button>
          </div>
        </form>
      ) : (
        <form className="space-y-4" onSubmit={onSubmitCredentials}>
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
                className={`${FIELD} pr-3`}
              />
            </div>
          </div>

          <div>
            <div className="mb-1.5 flex items-center justify-between">
              <label htmlFor="password" className="block text-sm font-medium text-app">
                {t('login.password')}
              </label>
              <Link
                to="/password/forgot"
                className="text-xs font-medium text-accent hover:underline"
              >
                {t('login.forgotPassword')}
              </Link>
            </div>
            <div className="relative">
              <Lock
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted"
                aria-hidden="true"
              />
              <input
                id="password"
                type={passwordVisible ? 'text' : 'password'}
                required
                autoComplete="current-password"
                value={password}
                onChange={(event) => {
                  setPassword(event.target.value);
                }}
                placeholder={t('login.passwordPlaceholder')}
                className={`${FIELD} pr-10`}
              />
              <button
                type="button"
                onClick={() => {
                  setPasswordVisible((visible) => !visible);
                }}
                aria-label={passwordVisible ? t('login.hidePassword') : t('login.showPassword')}
                className="absolute right-2 top-1/2 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-md text-muted hover:bg-surface-raised hover:text-app"
              >
                {passwordVisible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>

          <button type="submit" className={PRIMARY_BUTTON} disabled={submitting}>
            {submitting ? t('login.submitting') : t('login.submit')}
          </button>

          <div className="relative py-1 text-center">
            <span aria-hidden="true" className="absolute left-0 top-1/2 h-px w-full bg-app" />
            <span className="relative z-10 bg-surface px-2 text-xs text-muted">
              {t('login.or')}
            </span>
          </div>

          <button
            type="button"
            onClick={usePasskey}
            disabled={passkeyBusy}
            className="flex w-full items-center justify-center gap-2 rounded-lg border border-app bg-app py-2.5 text-sm font-medium text-app hover:bg-surface-raised disabled:opacity-60"
          >
            <Fingerprint className="h-4 w-4 text-accent" aria-hidden="true" />
            {t('login.passkey')}
          </button>

          <p className="pt-2 text-center text-sm text-muted">
            {t('login.noAccount')}{' '}
            <Link to="/register" className="font-medium text-accent hover:underline">
              {t('login.signUp')}
            </Link>
          </p>
        </form>
      )}
    </AuthLayout>
  );
}

import { Loader2 } from 'lucide-react';
import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import { ApiError } from '../../lib/api';
import type { Account } from '../auth/api';
import { ApplicationsSection } from './ApplicationsSection';
import { PasskeysSection } from './PasskeysSection';
import { SessionsSection } from './SessionsSection';
import { SshKeysSection } from './SshKeysSection';
import { TokensSection } from './TokensSection';
import { TwoFactorSection } from './TwoFactorSection';
import { UsageSection } from './UsageSection';
import {
  fetchAccount,
  fetchAuthorizations,
  fetchPasskeys,
  fetchSessions,
  fetchSshKeys,
  fetchTokens,
  type AccessToken,
  type Authorization,
  type Passkey,
  type SessionEntry,
  type SshKey,
} from './api';

const HTTP_UNAUTHORIZED = 401;

interface SettingsData {
  account: Account;
  passkeys: Passkey[];
  sessions: SessionEntry[];
  authorizations: Authorization[];
  tokens: AccessToken[];
  sshKeys: SshKey[];
}

/** Account security: two-factor codes, passkeys and live sessions. */
export function SettingsPage(): ReactNode {
  const { t } = useTranslation();
  const [data, setData] = useState<SettingsData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);

  const reload = useCallback(() => {
    setReloads((count) => count + 1);
  }, []);

  useEffect(() => {
    const controller = new AbortController();

    Promise.all([
      fetchAccount(controller.signal),
      fetchPasskeys(controller.signal),
      fetchSessions(controller.signal),
      fetchAuthorizations(controller.signal),
      fetchTokens(controller.signal),
      fetchSshKeys(controller.signal),
    ])
      .then(([account, passkeys, sessions, authorizations, tokens, sshKeys]) => {
        setData({ account, passkeys, sessions, authorizations, tokens, sshKeys });
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        if (cause instanceof ApiError && cause.status === HTTP_UNAUTHORIZED) {
          window.location.assign('/login');
          return;
        }
        setError(t('settings.error.load'));
      });

    return () => {
      controller.abort();
    };
  }, [reloads, t]);

  return (
    <div className="space-y-8 p-4 sm:p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-app">{t('settings.title')}</h1>
        <p className="mt-1 text-sm text-muted">{t('settings.subtitle')}</p>
      </div>

      {error !== null && <ErrorBanner message={error} />}

      {data === null && error === null && (
        <p className="flex items-center gap-2 text-sm text-muted">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          {t('settings.loading')}
        </p>
      )}

      {data !== null && (
        <div className="max-w-2xl space-y-10">
          <TwoFactorSection enabled={data.account.totpEnabled} onChanged={reload} />
          <PasskeysSection passkeys={data.passkeys} onChanged={reload} />
          <SessionsSection sessions={data.sessions} onChanged={reload} />
          <TokensSection tokens={data.tokens} onChanged={reload} />
          <SshKeysSection keys={data.sshKeys} onChanged={reload} />
          <ApplicationsSection authorizations={data.authorizations} onChanged={reload} />
          <UsageSection />
        </div>
      )}
    </div>
  );
}

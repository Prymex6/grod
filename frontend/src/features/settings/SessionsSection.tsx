import { LogOut, Monitor } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import { logoutOtherSessions, type SessionEntry } from './api';

interface SessionsSectionProps {
  sessions: SessionEntry[];
  onChanged: () => void;
}

/** Devices with a live session, and a way to sign the others out. */
export function SessionsSection({ sessions, onChanged }: SessionsSectionProps): ReactNode {
  const { t, i18n } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const others = sessions.filter((session) => !session.current).length;

  const signOutOthers = (): void => {
    setBusy(true);
    setError(null);
    logoutOtherSessions()
      .then(onChanged)
      .catch(() => {
        setError(t('settings.error.generic'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  return (
    <section aria-labelledby="sessions-heading" className="space-y-4">
      <div>
        <h2
          id="sessions-heading"
          className="text-sm font-semibold uppercase tracking-wider text-muted"
        >
          {t('settings.sessions.heading')}
        </h2>
        <p className="mt-1 text-sm text-muted">{t('settings.sessions.description')}</p>
      </div>

      {error !== null && <ErrorBanner message={error} />}

      <div className="overflow-hidden rounded-xl border border-app bg-surface shadow-app-sm">
        <ul className="divide-y divide-app">
          {sessions.map((session) => (
            <li
              key={`${session.createdAt}-${session.userAgent}`}
              className="flex items-center justify-between gap-4 px-4 py-3"
            >
              <div className="min-w-0">
                <p className="flex items-center gap-2 text-sm text-app">
                  <Monitor className="h-4 w-4 text-muted" aria-hidden="true" />
                  <span className="truncate">
                    {session.userAgent || t('settings.sessions.unknownDevice')}
                  </span>
                </p>
                <p className="mt-0.5 text-xs text-muted">
                  {t('settings.sessions.signedInAt', {
                    date: new Date(session.createdAt).toLocaleString(i18n.resolvedLanguage ?? 'pl'),
                  })}
                </p>
              </div>
              {session.current && (
                <span className="shrink-0 rounded-full bg-success-subtle px-2 py-0.5 text-xs font-medium text-success">
                  {t('settings.sessions.current')}
                </span>
              )}
            </li>
          ))}
        </ul>
      </div>

      <button
        type="button"
        onClick={signOutOthers}
        disabled={busy || others === 0}
        className="flex items-center gap-2 rounded-lg border border-app bg-app px-3 py-2 text-sm font-medium text-app hover:bg-surface-raised disabled:opacity-60"
      >
        <LogOut className="h-4 w-4" aria-hidden="true" />
        {t('settings.sessions.signOutOthers', { count: others })}
      </button>
    </section>
  );
}

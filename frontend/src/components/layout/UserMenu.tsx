import { LogOut, Settings } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import type { Account } from '../../features/auth/api';
import { signOut } from '../../features/auth/api';

const initialsOf = (displayName: string): string =>
  displayName
    .split(/\s+/u)
    .slice(0, 2)
    .map((part) => part.charAt(0))
    .join('')
    .toUpperCase();

/** Avatar with the account menu: settings and signing out. */
export function UserMenu({ account }: { account: Account }): ReactNode {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const close = (): void => {
      setOpen(false);
    };
    window.addEventListener('click', close);
    return () => {
      window.removeEventListener('click', close);
    };
  }, [open]);

  const leave = (): void => {
    signOut()
      .catch(() => {
        // Even a failed call must not keep anyone locked inside the console.
      })
      .finally(() => {
        window.location.assign('/login');
      });
  };

  return (
    <div className="relative">
      <button
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          setOpen((current) => !current);
        }}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={t('topbar.userMenu')}
        className="flex h-9 w-9 items-center justify-center rounded-full bg-accent-subtle text-sm font-semibold text-accent"
      >
        {initialsOf(account.displayName)}
      </button>

      {open && (
        <div
          role="menu"
          onClick={(event) => {
            event.stopPropagation();
          }}
          className="absolute right-0 top-full z-40 mt-1 w-60 overflow-hidden rounded-lg border border-app bg-surface py-1 shadow-app-md"
        >
          <div className="border-b border-app px-3 py-2">
            <p className="truncate text-sm font-medium text-app">{account.displayName}</p>
            <p className="truncate text-xs text-muted">{account.email}</p>
          </div>
          <Link
            to="/settings"
            role="menuitem"
            onClick={() => {
              setOpen(false);
            }}
            className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm text-app hover:bg-surface-raised"
          >
            <Settings className="h-4 w-4 text-muted" aria-hidden="true" />
            {t('settings.open')}
          </Link>
          <button
            type="button"
            role="menuitem"
            onClick={leave}
            className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm text-app hover:bg-surface-raised"
          >
            <LogOut className="h-4 w-4 text-muted" aria-hidden="true" />
            {t('topbar.signOut')}
          </button>
        </div>
      )}
    </div>
  );
}

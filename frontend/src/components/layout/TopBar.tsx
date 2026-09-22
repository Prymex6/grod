import { Bell, Menu, Plus, Search, X } from 'lucide-react';
import { useEffect, useRef, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import type { Account } from '../../features/auth/api';
import { LogoLockup } from '../brand/LogoLockup';
import { LogoMark } from '../brand/LogoMark';
import { IconButton } from '../ui/IconButton';
import { LanguageButton } from '../ui/LanguageButton';
import { ThemeButton } from '../ui/ThemeButton';
import { UserMenu } from './UserMenu';

interface TopBarProps {
  account: Account | null;
  menuOpen: boolean;
  onToggleMenu: () => void;
}

export function TopBar({ account, menuOpen, onToggleMenu }: TopBarProps): ReactNode {
  const { t } = useTranslation();
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const focusSearchOnSlash = (event: KeyboardEvent): void => {
      const target = event.target as HTMLElement | null;
      const typingInField = target?.tagName === 'INPUT' || target?.tagName === 'TEXTAREA';
      if (event.key === '/' && !typingInField) {
        event.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener('keydown', focusSearchOnSlash);
    return () => {
      window.removeEventListener('keydown', focusSearchOnSlash);
    };
  }, []);

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b border-app bg-surface px-3 sm:px-4">
      <IconButton
        label={menuOpen ? t('topbar.closeMenu') : t('topbar.openMenu')}
        onClick={onToggleMenu}
        expanded={menuOpen}
        className="lg:hidden"
      >
        {menuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
      </IconButton>

      <Link to="/" aria-label={t('app.name')} className="hidden sm:inline-flex">
        <LogoLockup name={t('app.name')} />
      </Link>
      <Link to="/" aria-label={t('app.name')} className="inline-flex text-accent sm:hidden">
        <LogoMark />
      </Link>

      <div className="mx-auto w-full max-w-md">
        <div className="flex items-center gap-2 rounded-lg border border-app bg-app px-3 py-1.5 focus-within:border-accent">
          <Search className="h-4 w-4 shrink-0 text-muted" aria-hidden="true" />
          <input
            ref={searchRef}
            type="search"
            placeholder={t('topbar.searchPlaceholder')}
            aria-label={t('topbar.searchLabel')}
            className="w-full bg-transparent text-sm text-app placeholder:text-muted focus:outline-none"
          />
          <kbd className="hidden shrink-0 rounded border border-app bg-surface px-1.5 py-0.5 font-mono text-[10px] text-muted sm:block">
            /
          </kbd>
        </div>
      </div>

      <div className="flex items-center gap-1">
        <button
          type="button"
          className="flex h-9 items-center gap-1.5 rounded-md bg-accent px-2.5 text-sm font-medium text-accent-contrast hover:bg-accent-hover sm:px-3"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          <span className="hidden sm:inline">{t('topbar.new')}</span>
        </button>

        <IconButton label={t('topbar.notifications')}>
          <Bell className="h-5 w-5" />
        </IconButton>

        <ThemeButton />
        <LanguageButton />
        {account !== null && <UserMenu account={account} />}
      </div>
    </header>
  );
}

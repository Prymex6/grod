import { X } from 'lucide-react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { LogoLockup } from '../brand/LogoLockup';
import { IconButton } from '../ui/IconButton';
import { SidebarNav } from './SidebarNav';

interface SidebarProps {
  open: boolean;
  onClose: () => void;
}

/** Permanent on wide screens, a slide-over panel on phones. */
export function Sidebar({ open, onClose }: SidebarProps): ReactNode {
  const { t } = useTranslation();

  return (
    <>
      <aside className="hidden w-60 shrink-0 border-r border-app bg-surface lg:block">
        <SidebarNav onNavigate={onClose} />
      </aside>

      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button
            type="button"
            aria-label={t('topbar.closeMenu')}
            onClick={onClose}
            className="absolute inset-0 h-full w-full cursor-default bg-black/50"
          />
          <aside className="absolute left-0 top-0 h-full w-64 border-r border-app bg-surface shadow-app-md">
            <div className="flex h-14 items-center justify-between border-b border-app px-3">
              <LogoLockup name={t('app.name')} size="sm" />
              <IconButton label={t('topbar.closeMenu')} onClick={onClose}>
                <X className="h-5 w-5" />
              </IconButton>
            </div>
            <SidebarNav onNavigate={onClose} />
          </aside>
        </div>
      )}
    </>
  );
}

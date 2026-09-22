import { Languages } from 'lucide-react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { useLanguage } from '../../i18n/useLanguage';

/** Switches the console between Polish and English. */
export function LanguageButton(): ReactNode {
  const { t } = useTranslation();
  const { language, toggleLanguage } = useLanguage();

  return (
    <button
      type="button"
      onClick={toggleLanguage}
      aria-label={t('topbar.language')}
      className="flex h-9 items-center gap-1.5 rounded-md px-2 text-xs font-semibold uppercase tracking-wider text-muted hover:bg-surface-raised hover:text-app"
    >
      <Languages className="h-4 w-4" aria-hidden="true" />
      <span>{language}</span>
    </button>
  );
}

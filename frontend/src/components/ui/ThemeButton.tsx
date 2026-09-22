import { Moon, Sun } from 'lucide-react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { useTheme } from '../../theme/useTheme';
import { IconButton } from './IconButton';

/** Switches between the light and dark theme. */
export function ThemeButton(): ReactNode {
  const { t } = useTranslation();
  const { theme, toggleTheme } = useTheme();
  const isLight = theme === 'light';

  return (
    <IconButton
      label={isLight ? t('topbar.theme.toDark') : t('topbar.theme.toLight')}
      onClick={toggleTheme}
    >
      {isLight ? <Moon className="h-5 w-5" /> : <Sun className="h-5 w-5" />}
    </IconButton>
  );
}

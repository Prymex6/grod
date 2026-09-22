import { useContext } from 'react';

import { ThemeContext, type ThemeContextValue } from './ThemeContext';

/** Current theme and a toggle; requires ThemeProvider above in the tree. */
export const useTheme = (): ThemeContextValue => {
  const context = useContext(ThemeContext);
  if (!context) throw new Error('useTheme must be used inside ThemeProvider');
  return context;
};

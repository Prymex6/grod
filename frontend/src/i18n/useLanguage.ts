import { useTranslation } from 'react-i18next';

import { DEFAULT_LANGUAGE, LANGUAGES, storeLanguage, type Language } from './index';

interface LanguageControl {
  language: Language;
  toggleLanguage: () => void;
}

/** Current language plus a toggle between Polish and English. */
export const useLanguage = (): LanguageControl => {
  const { i18n } = useTranslation();
  const current = LANGUAGES.find((code) => i18n.resolvedLanguage === code) ?? DEFAULT_LANGUAGE;

  const toggleLanguage = (): void => {
    const next = current === 'pl' ? 'en' : 'pl';
    void i18n.changeLanguage(next);
    storeLanguage(next);
    document.documentElement.lang = next;
  };

  return { language: current, toggleLanguage };
};

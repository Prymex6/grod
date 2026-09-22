import i18next from 'i18next';
import { initReactI18next } from 'react-i18next';

import { en } from './locales/en';
import { pl } from './locales/pl';

export const LANGUAGES = ['pl', 'en'] as const;
export type Language = (typeof LANGUAGES)[number];

export const DEFAULT_LANGUAGE: Language = 'pl';
const STORAGE_KEY = 'grod.language';

const isLanguage = (value: string | null): value is Language =>
  value !== null && LANGUAGES.includes(value as Language);

const readStoredLanguage = (): Language => {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return isLanguage(stored) ? stored : DEFAULT_LANGUAGE;
  } catch {
    // Storage can be blocked (private mode, blocked cookies) — fall back silently.
    return DEFAULT_LANGUAGE;
  }
};

export const storeLanguage = (language: Language): void => {
  try {
    localStorage.setItem(STORAGE_KEY, language);
  } catch {
    // Remembering the choice is a convenience, not a requirement.
  }
};

await i18next.use(initReactI18next).init({
  resources: { pl: { translation: pl }, en: { translation: en } },
  lng: readStoredLanguage(),
  fallbackLng: DEFAULT_LANGUAGE,
  supportedLngs: LANGUAGES,
  // Keys are flat strings with dots, so no nesting or namespace separators.
  keySeparator: false,
  nsSeparator: false,
  interpolation: { escapeValue: false },
});

export default i18next;

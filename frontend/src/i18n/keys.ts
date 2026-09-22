import type { pl } from './locales/pl';

/** Every key the translation files define; t() accepts nothing else. */
export type TranslationKey = keyof typeof pl;

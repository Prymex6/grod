import type { pl } from './locales/pl';

// Makes t() reject unknown keys. Values are typed as plain strings so that
// i18next does not try to derive the placeholders from each literal template.
declare module 'i18next' {
  interface CustomTypeOptions {
    resources: { translation: Record<keyof typeof pl, string> };
    keySeparator: false;
    nsSeparator: false;
  }
}

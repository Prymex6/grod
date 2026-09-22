import '@testing-library/jest-dom/vitest';
import '../i18n';

// jsdom does not implement matchMedia, which the theme uses to read the
// system preference. Report "light" so components render deterministically.
window.matchMedia = (query: string): MediaQueryList =>
  ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    addListener: () => undefined,
    removeListener: () => undefined,
    dispatchEvent: () => false,
  }) as MediaQueryList;

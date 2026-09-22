import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { LogoMark } from '../../components/brand/LogoMark';
import { LanguageButton } from '../../components/ui/LanguageButton';
import { ThemeButton } from '../../components/ui/ThemeButton';

interface AuthLayoutProps {
  heading: string;
  subtitle: string;
  footer?: string;
  children: ReactNode;
}

/** Standalone frame of the Brama screens: sign-in, registration, consent. */
export function AuthLayout({ heading, subtitle, footer, children }: AuthLayoutProps): ReactNode {
  const { t } = useTranslation();

  return (
    <div className="flex min-h-screen flex-col bg-app text-app">
      <header className="flex items-center justify-end gap-1 px-4 py-4 sm:px-6">
        <ThemeButton />
        <LanguageButton />
      </header>

      <main className="flex flex-1 items-center justify-center px-4 py-8">
        <div className="w-full max-w-md">
          <div className="mb-6 flex flex-col items-center text-center">
            <span className="text-accent">
              <LogoMark className="h-12 w-12" />
            </span>
            <h1 className="mt-3 text-2xl font-semibold tracking-tight text-app">{heading}</h1>
            <p className="mt-1 text-sm text-muted">{subtitle}</p>
          </div>

          <div className="rounded-xl border border-app bg-surface p-6 shadow-app-md">
            {children}
          </div>

          {footer !== undefined && <p className="mt-4 text-center text-xs text-muted">{footer}</p>}
        </div>
      </main>

      <footer className="border-t border-app px-4 py-4 text-center text-xs text-muted sm:px-6">
        © {new Date().getFullYear()} {t('app.name')} — {t('app.tagline')}
      </footer>
    </div>
  );
}

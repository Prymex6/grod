import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { CLOUD_NAV, CODE_NAV, MODULE_NAMES } from '../../modules';

const ITEM_CLASS =
  'flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm text-app hover:bg-surface-raised';

/**
 * Navigation of the console. The entries are not links yet: their pages are
 * built module by module, so for now they only show the structure.
 */
export function SidebarNav({ onNavigate }: { onNavigate: () => void }): ReactNode {
  const { t } = useTranslation();

  return (
    <nav
      aria-label={t('app.name')}
      className="flex h-full flex-col gap-6 overflow-y-auto px-3 py-4"
    >
      <div>
        <p className="mb-2 px-2 text-xs font-semibold uppercase tracking-wider text-muted">
          {t('nav.section.code')}
        </p>
        <ul className="space-y-0.5">
          {CODE_NAV.map(({ labelKey, icon: Icon, to }) => (
            <li key={labelKey}>
              {to === undefined ? (
                <button
                  type="button"
                  onClick={onNavigate}
                  className={`w-full text-left ${ITEM_CLASS}`}
                >
                  <Icon className="h-4 w-4 shrink-0 text-muted" aria-hidden="true" />
                  {t(labelKey)}
                </button>
              ) : (
                <Link to={to} onClick={onNavigate} className={ITEM_CLASS}>
                  <Icon className="h-4 w-4 shrink-0 text-muted" aria-hidden="true" />
                  {t(labelKey)}
                </Link>
              )}
            </li>
          ))}
        </ul>
      </div>

      <div>
        <p className="mb-2 px-2 text-xs font-semibold uppercase tracking-wider text-muted">
          {t('nav.section.cloud')}
        </p>
        <ul className="space-y-0.5">
          {CLOUD_NAV.map(({ id, descriptionKey, icon: Icon, to }) => {
            const described = `${MODULE_NAMES[id]} — ${t(descriptionKey)}`;
            return (
              <li key={id}>
                {to === undefined ? (
                  <button
                    type="button"
                    onClick={onNavigate}
                    title={described}
                    aria-label={described}
                    className={`w-full text-left ${ITEM_CLASS}`}
                  >
                    <Icon className="h-4 w-4 shrink-0 text-muted" aria-hidden="true" />
                    {MODULE_NAMES[id]}
                  </button>
                ) : (
                  <Link to={to} onClick={onNavigate} title={described} className={ITEM_CLASS}>
                    <Icon className="h-4 w-4 shrink-0 text-muted" aria-hidden="true" />
                    {MODULE_NAMES[id]}
                  </Link>
                )}
              </li>
            );
          })}
        </ul>
      </div>
    </nav>
  );
}

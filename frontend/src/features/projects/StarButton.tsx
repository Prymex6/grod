import { Star } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { starProject, unstarProject, type Project } from './api';

/** Gives a project a star, or takes it back. */
export function StarButton({ project }: { project: Project }): ReactNode {
  const { t } = useTranslation();
  const [starred, setStarred] = useState(project.starred);
  const [stars, setStars] = useState(project.stars);
  const [busy, setBusy] = useState(false);

  const toggle = (): void => {
    const next = !starred;
    setBusy(true);
    // The count moves at once; a failure puts it back where it was.
    setStarred(next);
    setStars((count) => count + (next ? 1 : -1));
    const run = next ? starProject : unstarProject;
    run(project.ownerLogin, project.slug)
      .catch(() => {
        setStarred(!next);
        setStars((count) => count + (next ? -1 : 1));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  return (
    <button
      type="button"
      onClick={toggle}
      disabled={busy}
      aria-pressed={starred}
      className={`flex items-center gap-1.5 rounded-lg border border-app px-2.5 py-1.5 text-sm font-medium disabled:opacity-60 ${
        starred
          ? 'bg-accent-subtle text-accent'
          : 'bg-surface text-muted hover:bg-surface-raised hover:text-app'
      }`}
    >
      <Star className={`h-4 w-4 ${starred ? 'fill-current' : ''}`} aria-hidden="true" />
      {t(starred ? 'project.starred' : 'project.star')}
      <span className="font-mono text-xs">{stars}</span>
    </button>
  );
}

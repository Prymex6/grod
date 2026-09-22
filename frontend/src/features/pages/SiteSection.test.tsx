import { screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { jsonResponse, mockApi, show } from '../../test/api';
import type { Project } from '../projects/api';
import { SiteSection } from './SiteSection';
import type { Site } from './api';

const PROJECT: Project = {
  id: '99999999-9999-4999-8999-999999999999',
  ownerLogin: 'bartek',
  slug: 'first-project',
  name: 'First project',
  description: '',
  visibility: 'public',
  defaultBranch: 'main',
  empty: false,
  cloneUrl: 'http://localhost:5173/bartek/first-project.git',
  createdAt: '2026-09-20T08:00:00Z',
  access: { read: true, write: true, manage: true, own: true },
  stars: 0,
  starred: false,
};

const SITE = '/api/v1/projects/bartek/first-project/site';

const PUBLISHED: Site = {
  branch: 'main',
  directory: 'public',
  enabled: true,
  publishedCommit: 'a'.repeat(40),
  publishedAt: '2026-09-20T09:00:00Z',
  url: 'http://localhost:5173/-/pages/bartek/first-project/',
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('SiteSection', () => {
  it('shows the address a published site answers at', async () => {
    mockApi({ [SITE]: jsonResponse(PUBLISHED) });
    show(<SiteSection project={PROJECT} branches={[{ name: 'main', commit: 'a'.repeat(40) }]} />);

    expect(
      await screen.findByText('http://localhost:5173/-/pages/bartek/first-project/'),
    ).toBeInTheDocument();
  });

  it('says so when nothing has been published yet', async () => {
    mockApi({ [SITE]: jsonResponse({ ...PUBLISHED, publishedCommit: null, publishedAt: null }) });
    show(<SiteSection project={PROJECT} branches={[{ name: 'main', commit: 'a'.repeat(40) }]} />);

    expect(await screen.findByText('Jeszcze nic nie opublikowano.')).toBeInTheDocument();
  });

  it('offers to switch a site on when the project has none', async () => {
    // A project without a site answers 404, which is an answer, not a failure.
    mockApi({ [SITE]: jsonResponse({ detail: 'No such site' }, 404) });
    show(<SiteSection project={PROJECT} branches={[{ name: 'main', commit: 'a'.repeat(40) }]} />);

    expect(await screen.findByRole('button', { name: 'Włącz witrynę' })).toBeInTheDocument();
    expect(screen.queryByText('Nie udało się sprawdzić witryny.')).not.toBeInTheDocument();
  });
});

import { screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { jsonResponse, mockApi, show } from '../../test/api';
import type { Project } from '../projects/api';
import { SecretsSection } from './SecretsSection';
import type { Secret } from './api';

const PROJECT: Project = {
  id: '99999999-9999-4999-8999-999999999999',
  ownerLogin: 'bartek',
  slug: 'first-project',
  name: 'First project',
  description: '',
  visibility: 'private',
  defaultBranch: 'main',
  empty: false,
  cloneUrl: 'http://localhost:5173/bartek/first-project.git',
  createdAt: '2026-09-20T08:00:00Z',
  access: { read: true, write: true, manage: true, own: true },
  stars: 0,
  starred: false,
};

const SECRETS = '/api/v1/projects/bartek/first-project/secrets';

const DEPLOY_TOKEN: Secret = {
  name: 'DEPLOY_TOKEN',
  masked: true,
  protected: true,
  createdAt: '2026-09-20T08:00:00Z',
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('SecretsSection', () => {
  it('names the secrets but never shows what is in them', async () => {
    mockApi({ [SECRETS]: jsonResponse([DEPLOY_TOKEN]) });
    show(<SecretsSection project={PROJECT} />);

    expect(await screen.findByText('DEPLOY_TOKEN')).toBeInTheDocument();
    // The value is not in the answer at all, so it cannot leak into the page.
    expect(screen.queryByText(/grodrun_/)).not.toBeInTheDocument();
  });

  it('marks a secret that only protected branches may use', async () => {
    mockApi({ [SECRETS]: jsonResponse([DEPLOY_TOKEN]) });
    show(<SecretsSection project={PROJECT} />);

    expect(await screen.findByText('tylko chronione')).toBeInTheDocument();
    expect(screen.getByText('maskowany')).toBeInTheDocument();
  });

  it('shows a plain message when they cannot be read', async () => {
    mockApi({});
    show(<SecretsSection project={PROJECT} />);

    expect(await screen.findByText('Nie udało się wczytać sekretów.')).toBeInTheDocument();
  });
});

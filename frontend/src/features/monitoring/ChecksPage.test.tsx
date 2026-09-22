import { screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { jsonResponse, mockApi, show } from '../../test/api';
import { ChecksPage } from './ChecksPage';
import type { Check } from './api';

const CHECKS = '/api/v1/checks';

const HOME: Check = {
  id: 'aaaaaaaa-1111-4111-8111-111111111111',
  name: 'home page',
  url: 'https://example.com/',
  intervalSeconds: 60,
  expectedStatus: 200,
  enabled: true,
  state: 'up',
  lastCheckedAt: '2026-09-20T09:00:00Z',
  lastDurationMs: 120,
  lastError: '',
  uptime: 99.5,
  averageMs: 130,
  createdAt: '2026-09-20T08:00:00Z',
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('ChecksPage', () => {
  it('lists what is being watched and where', async () => {
    mockApi({ [CHECKS]: jsonResponse([HOME]) });
    show(<ChecksPage />);

    expect(await screen.findByText('home page')).toBeInTheDocument();
    expect(screen.getByText(/example.com/)).toBeInTheDocument();
  });

  it('says so when nothing is watched yet', async () => {
    mockApi({ [CHECKS]: jsonResponse([]) });
    show(<ChecksPage />);

    expect(await screen.findByText('Nie pilnujesz jeszcze żadnego adresu.')).toBeInTheDocument();
  });

  it('shows a plain message when the list cannot be read', async () => {
    mockApi({});
    show(<ChecksPage />);

    expect(await screen.findByText('Nie udało się wczytać nadzorów.')).toBeInTheDocument();
  });
});

import { screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { jsonResponse, mockApi, show } from '../../test/api';
import { MarketPage } from './MarketPage';
import type { Offering } from './api';

const MARKET = '/api/v1/market';

const NGINX: Offering = {
  slug: 'ready-nginx',
  title: 'Ready-made nginx',
  description: 'A web server with nothing to set up.',
  kind: 'application',
  author: 'anna.k',
  branch: '',
  image: 'nginx:1.27-alpine',
  published: true,
  taken: 4,
  createdAt: '2026-09-20T08:00:00Z',
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('MarketPage', () => {
  it('shows what is on offer', async () => {
    mockApi({ [MARKET]: jsonResponse([NGINX]) });
    show(<MarketPage />);

    expect(await screen.findByText('Ready-made nginx')).toBeInTheDocument();
  });

  it('says so when nothing is on offer', async () => {
    mockApi({ [MARKET]: jsonResponse([]) });
    show(<MarketPage />);

    expect(await screen.findByText('Na jarmarku jeszcze nic nie stoi.')).toBeInTheDocument();
  });

  it('shows a plain message when the list cannot be read', async () => {
    mockApi({});
    show(<MarketPage />);

    expect(await screen.findByText('Nie udało się wczytać jarmarku.')).toBeInTheDocument();
  });
});

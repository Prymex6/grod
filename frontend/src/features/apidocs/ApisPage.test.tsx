import { screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { jsonResponse, mockApi, show } from '../../test/api';
import { ApisPage } from './ApisPage';
import type { ApiDoc } from './api';

const APIS = '/api/v1/apis';

const SHOP: ApiDoc = {
  id: 'aaaaaaaa-1111-4111-8111-111111111111',
  name: 'shop-api',
  source: 'uploaded',
  url: '',
  title: 'Shop API',
  version: '1.0.0',
  public: false,
  operations: 3,
  fetchedAt: null,
  lastError: '',
  createdAt: '2026-09-20T08:00:00Z',
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('ApisPage', () => {
  it('lists the kept descriptions by their title', async () => {
    mockApi({ [APIS]: jsonResponse([SHOP]) });
    show(<ApisPage />);

    expect(await screen.findByText('Shop API')).toBeInTheDocument();
  });

  it('says so when nothing has been described yet', async () => {
    mockApi({ [APIS]: jsonResponse([]) });
    show(<ApisPage />);

    expect(await screen.findByText('Nie masz jeszcze żadnego opisu API.')).toBeInTheDocument();
  });

  it('shows a plain message when the list cannot be read', async () => {
    mockApi({});
    show(<ApisPage />);

    expect(await screen.findByText('Nie udało się wczytać opisów.')).toBeInTheDocument();
  });
});

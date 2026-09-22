import { screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { jsonResponse, mockApi, show } from '../../test/api';
import { RoutesPage } from './RoutesPage';
import type { Route } from './api';

const ROUTES = '/api/v1/routes';

const SHOP: Route = {
  id: 'aaaaaaaa-1111-4111-8111-111111111111',
  name: 'shop',
  targetKind: 'application',
  target: 'my-site',
  public: true,
  url: 'http://localhost:5173/-/traffic/shop/',
  createdAt: '2026-09-20T08:00:00Z',
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('RoutesPage', () => {
  it('lists the routes with the address each one answers at', async () => {
    mockApi({ [ROUTES]: jsonResponse([SHOP]) });
    show(<RoutesPage />);

    // The row shows the address, not the bare name; the name labels the controls.
    expect(await screen.findByText('http://localhost:5173/-/traffic/shop/')).toBeInTheDocument();
    expect(screen.getByText(/my-site/)).toBeInTheDocument();
  });

  it('says so when no address has been set up', async () => {
    mockApi({ [ROUTES]: jsonResponse([]) });
    show(<RoutesPage />);

    expect(await screen.findByText('Nie masz jeszcze żadnego adresu.')).toBeInTheDocument();
  });

  it('shows a plain message when the list cannot be read', async () => {
    mockApi({});
    show(<RoutesPage />);

    expect(await screen.findByText('Nie udało się wczytać adresów.')).toBeInTheDocument();
  });
});

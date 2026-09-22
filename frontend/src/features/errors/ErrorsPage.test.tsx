import { screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { jsonResponse, mockApi, show } from '../../test/api';
import { ErrorsPage } from './ErrorsPage';
import type { Source } from './api';

const SOURCES = '/api/v1/errors/sources';

const CHECKOUT: Source = {
  id: 'aaaaaaaa-1111-4111-8111-111111111111',
  name: 'checkout',
  key: 'grodczuj_abc123',
  issues: 2,
  unresolved: 1,
  reports: 7,
  createdAt: '2026-09-20T08:00:00Z',
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('ErrorsPage', () => {
  it('lists the sources that report errors', async () => {
    mockApi({ [SOURCES]: jsonResponse([CHECKOUT]) });
    show(<ErrorsPage />);

    expect(await screen.findByText('checkout')).toBeInTheDocument();
  });

  it('says so when nothing reports anything', async () => {
    mockApi({ [SOURCES]: jsonResponse([]) });
    show(<ErrorsPage />);

    expect(await screen.findByText('Nic jeszcze nie zgłasza błędów.')).toBeInTheDocument();
  });
});

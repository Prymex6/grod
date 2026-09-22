import { screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { jsonResponse, mockApi, show } from '../../test/api';
import { HomePage } from './HomePage';

const HEALTH = '/api/v1/health';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('HomePage', () => {
  it('reports what the instance calls itself and which version answers', async () => {
    mockApi({ [HEALTH]: jsonResponse({ status: 'ok', instance: 'Gród', version: '0.1.0' }) });
    show(<HomePage />);

    expect(await screen.findByText('Działa')).toBeInTheDocument();
    expect(screen.getByText('Gród')).toBeInTheDocument();
    expect(screen.getByText('0.1.0')).toBeInTheDocument();
  });

  it('says plainly when the API cannot be reached', async () => {
    mockApi({});
    show(<HomePage />);

    expect(await screen.findByText('Brak połączenia z API')).toBeInTheDocument();
  });
});

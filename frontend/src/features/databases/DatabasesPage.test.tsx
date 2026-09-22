import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { jsonResponse, mockApi, nthButton, show } from '../../test/api';
import { DatabasesPage } from './DatabasesPage';
import type { ManagedDatabase } from './api';

const DATABASES = '/api/v1/databases';

const SHOP: ManagedDatabase = {
  id: 'aaaaaaaa-1111-4111-8111-111111111111',
  name: 'shop',
  engine: 'postgres',
  databaseName: 'grod_db_abc123',
  roleName: 'grod_user_abc123',
  host: 'localhost',
  port: 5433,
  sizeBytes: 8192,
  createdAt: '2026-09-20T08:00:00Z',
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('DatabasesPage', () => {
  it('lists the databases with the name the server really gave them', async () => {
    mockApi({ [DATABASES]: jsonResponse([SHOP]) });
    show(<DatabasesPage />);

    expect(await screen.findByText('shop')).toBeInTheDocument();
    expect(screen.getByText(/postgres · localhost:5433/)).toBeInTheDocument();
  });

  it('keeps the connection details behind a button', async () => {
    mockApi({ [DATABASES]: jsonResponse([SHOP]) });
    show(<DatabasesPage />);

    expect(await screen.findByRole('button', { name: 'Pokaż dane dostępu' })).toBeInTheDocument();
  });

  it('says so when there is no database yet', async () => {
    mockApi({ [DATABASES]: jsonResponse([]) });
    show(<DatabasesPage />);

    expect(await screen.findByText('Nie masz jeszcze żadnej bazy.')).toBeInTheDocument();
  });

  it('sends a new database to the API', async () => {
    const sent = mockApi({ [DATABASES]: jsonResponse([]) });
    const user = userEvent.setup();
    show(<DatabasesPage />);

    await screen.findByText('Nie masz jeszcze żadnej bazy.');
    await user.click(screen.getByRole('button', { name: 'Nowa baza' }));
    await user.type(screen.getByLabelText('Nazwa bazy'), 'shop');
    await user.click(nthButton('Nowa baza', 1));

    expect(sent).toContain(`POST ${DATABASES}`);
  });

  it('shows a plain message when the list cannot be read', async () => {
    mockApi({});
    show(<DatabasesPage />);

    expect(await screen.findByText('Nie udało się wczytać baz.')).toBeInTheDocument();
  });
});

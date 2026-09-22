import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ThemeProvider } from '../../theme/ThemeProvider';
import { AccessPage } from './AccessPage';

const BUCKET = {
  id: '11111111-1111-4111-8111-111111111111',
  name: 'my-storage',
};

const GRANT = {
  id: '22222222-2222-4222-8222-222222222222',
  resourceKind: 'bucket',
  resourceId: BUCKET.id,
  subjectKind: 'group',
  subjectId: '33333333-3333-4333-8333-333333333333',
  subject: 'zespol-wdrozeniowy',
  role: 'viewer',
  createdAt: '2026-09-19T08:00:00Z',
};

const ACCOUNT = {
  id: '44444444-4444-4444-8444-444444444444',
  name: 'worker-zamowienia',
  active: true,
  lastUsedAt: null,
  createdAt: '2026-09-19T08:00:00Z',
};

const jsonResponse = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

const mockApi = (answers: Record<string, Response>, sent: string[] = []): void => {
  vi.stubGlobal(
    'fetch',
    vi.fn((path: string, options?: { method?: string }) => {
      sent.push(`${options?.method ?? 'GET'} ${path}`);
      return Promise.resolve(answers[path] ?? jsonResponse({ detail: 'not mocked' }, 404));
    }),
  );
};

const show = (): void => {
  render(
    <MemoryRouter>
      <ThemeProvider>
        <AccessPage />
      </ThemeProvider>
    </MemoryRouter>,
  );
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('AccessPage', () => {
  it('shows who was let into the chosen resource', async () => {
    mockApi({
      '/api/v1/iam/service-accounts': jsonResponse([ACCOUNT]),
      '/api/v1/storage/buckets': jsonResponse([BUCKET]),
      [`/api/v1/iam/grants?resourceKind=bucket&resourceId=${BUCKET.id}`]: jsonResponse([GRANT]),
    });
    show();

    // The words also stand in the pickers below, so the row itself is read.
    const row = (await screen.findByText('zespol-wdrozeniowy')).closest('li');
    expect(row?.textContent).toContain('grupa');
    expect(row?.textContent).toContain('podgląd');
    expect(screen.getByText('worker-zamowienia')).toBeInTheDocument();
    expect(screen.getByText('nieużywana')).toBeInTheDocument();
  });

  it('says so when nobody else has been let in', async () => {
    mockApi({
      '/api/v1/iam/service-accounts': jsonResponse([]),
      '/api/v1/storage/buckets': jsonResponse([BUCKET]),
      [`/api/v1/iam/grants?resourceKind=bucket&resourceId=${BUCKET.id}`]: jsonResponse([]),
    });
    show();

    expect(await screen.findByText('Nikt poza Tobą nie ma tu dostępu.')).toBeInTheDocument();
  });

  it('shows a fresh token once, with the warning that it will not come back', async () => {
    mockApi({
      '/api/v1/iam/service-accounts': jsonResponse([]),
      '/api/v1/storage/buckets': jsonResponse([]),
    });
    const user = userEvent.setup();
    show();

    await screen.findByText('Nie masz jeszcze żadnej tożsamości maszynowej.');
    mockApi({
      '/api/v1/iam/service-accounts': jsonResponse({
        ...ACCOUNT,
        token: 'grodsrv_abc_sekret',
      }),
      '/api/v1/storage/buckets': jsonResponse([]),
    });
    await user.type(screen.getByLabelText('Nazwa'), 'worker-zamowienia');
    await user.click(screen.getByRole('button', { name: 'Utwórz' }));

    expect(await screen.findByText('grodsrv_abc_sekret')).toBeInTheDocument();
    expect(screen.getByText('Token pokazujemy tylko raz. Zapisz go teraz.')).toBeInTheDocument();
  });

  it('asks the module of the chosen kind for what it holds', async () => {
    const sent: string[] = [];
    mockApi(
      {
        '/api/v1/iam/service-accounts': jsonResponse([]),
        '/api/v1/storage/buckets': jsonResponse([]),
        '/api/v1/queues': jsonResponse([{ id: BUCKET.id, name: 'zadania' }]),
        [`/api/v1/iam/grants?resourceKind=queue&resourceId=${BUCKET.id}`]: jsonResponse([]),
      },
      sent,
    );
    const user = userEvent.setup();
    show();

    await screen.findByText('Nie masz jeszcze niczego tego rodzaju.');
    await user.selectOptions(screen.getByLabelText('Rodzaj'), 'queue');

    expect(await screen.findByRole('option', { name: 'zadania' })).toBeInTheDocument();
    expect(sent).toContain('GET /api/v1/queues');
  });
});

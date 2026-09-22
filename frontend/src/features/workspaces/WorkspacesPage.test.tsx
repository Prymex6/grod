import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ThemeProvider } from '../../theme/ThemeProvider';
import { WorkspacesPage } from './WorkspacesPage';

const WORKSPACES = '/api/v1/workspaces';

const STOPPED = {
  id: 'aaaaaaaa-1111-4111-8111-111111111111',
  name: 'my-workspace',
  project: 'bartek/first-project',
  branch: 'main',
  image: 'python:3.14-slim',
  commit: '0'.repeat(40),
  state: 'stopped' as const,
  lastError: '',
  createdAt: '2026-09-20T08:00:00Z',
};

const FAILED = {
  ...STOPPED,
  id: 'bbbbbbbb-2222-4222-8222-222222222222',
  name: 'zepsuty',
  state: 'failed' as const,
  lastError: 'Unable to find image',
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
        <WorkspacesPage />
      </ThemeProvider>
    </MemoryRouter>,
  );
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('WorkspacesPage', () => {
  it('shows a workspace with the project and branch it works on', async () => {
    mockApi({ [WORKSPACES]: jsonResponse([STOPPED]) });
    show();

    expect(await screen.findAllByText('my-workspace')).not.toHaveLength(0);
    expect(screen.getByText('bartek/first-project · main')).toBeInTheDocument();
    expect(screen.getByText('zatrzymany')).toBeInTheDocument();
    // Nothing runs, so there is nothing to type into and nothing to save.
    expect(screen.queryByRole('button', { name: 'Zapisz jako commit' })).not.toBeInTheDocument();
  });

  it('says why a workspace did not start', async () => {
    mockApi({ [WORKSPACES]: jsonResponse([FAILED]) });
    show();

    expect(await screen.findByText('Unable to find image')).toBeInTheDocument();
    expect(screen.getByText('błąd')).toBeInTheDocument();
  });

  it('says so when there is nothing yet', async () => {
    mockApi({ [WORKSPACES]: jsonResponse([]) });
    show();

    expect(await screen.findByText('Nie masz jeszcze żadnego warsztatu.')).toBeInTheDocument();
  });

  it('asks the API to start the container', async () => {
    const sent: string[] = [];
    mockApi(
      {
        [WORKSPACES]: jsonResponse([STOPPED]),
        [`${WORKSPACES}/my-workspace/start`]: jsonResponse(STOPPED),
      },
      sent,
    );
    const user = userEvent.setup();
    show();

    await screen.findByText('zatrzymany');
    await user.click(screen.getByRole('button', { name: 'Uruchom' }));

    expect(sent).toContain(`POST ${WORKSPACES}/my-workspace/start`);
  });

  it('refuses a project that is not written owner/project', async () => {
    mockApi({ [WORKSPACES]: jsonResponse([]) });
    const user = userEvent.setup();
    show();

    await screen.findByText('Nie masz jeszcze żadnego warsztatu.');
    await user.click(screen.getByRole('button', { name: 'Nowy workspaces' }));
    await user.type(screen.getByLabelText('Nazwa'), 'proba');
    await user.type(screen.getByLabelText('Projekt (login/projekt)'), 'bezukosnika');
    await user.click(screen.getByRole('button', { name: 'Utwórz' }));

    expect(await screen.findByText('Podaj projekt w postaci login/projekt.')).toBeInTheDocument();
  });
});

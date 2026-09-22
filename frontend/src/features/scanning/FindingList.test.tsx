import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { Project } from '../projects/api';
import { ThemeProvider } from '../../theme/ThemeProvider';
import { FindingList } from './FindingList';

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

const FINDINGS = '/api/v1/projects/bartek/first-project/findings';

const KEY = {
  id: 'aaaaaaaa-1111-4111-8111-111111111111',
  rule: 'aws-access-key',
  certain: true,
  path: 'deploy.py',
  line: 1,
  snippet: "KEY = 'AKIA…'",
  commit: '0'.repeat(40),
  state: 'open' as const,
  createdAt: '2026-09-20T08:00:00Z',
  lastSeenAt: '2026-09-20T08:00:00Z',
};

const GUESS = {
  ...KEY,
  id: 'bbbbbbbb-2222-4222-8222-222222222222',
  rule: 'password-in-code',
  certain: false,
  path: 'settings.py',
  snippet: "PASSWORD = 'hunter…'",
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
        <FindingList project={PROJECT} />
      </ThemeProvider>
    </MemoryRouter>,
  );
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('FindingList', () => {
  it('shows where the secret sits without showing the secret', async () => {
    mockApi({ [FINDINGS]: jsonResponse([KEY]) });
    show();

    expect(await screen.findByText('Klucz AWS')).toBeInTheDocument();
    expect(screen.getByText('deploy.py:1')).toBeInTheDocument();
    expect(screen.getByText("KEY = 'AKIA…'")).toBeInTheDocument();
    expect(screen.getByText('do sprawdzenia: 1')).toBeInTheDocument();
  });

  it('marks a rule that guesses as one to confirm', async () => {
    mockApi({ [FINDINGS]: jsonResponse([KEY, GUESS]) });
    show();

    await screen.findByText('Hasło w kodzie');
    expect(screen.getAllByText('do potwierdzenia')).toHaveLength(1);
  });

  it('says so when the branch is clean', async () => {
    mockApi({ [FINDINGS]: jsonResponse([]) });
    show();

    expect(await screen.findByText('Nic podejrzanego w gałęzi głównej.')).toBeInTheDocument();
  });

  it('asks the API to look again', async () => {
    const sent: string[] = [];
    mockApi({ [FINDINGS]: jsonResponse([]), [`${FINDINGS}/scan`]: jsonResponse({}) }, sent);
    const user = userEvent.setup();
    show();

    await screen.findByText('Nic podejrzanego w gałęzi głównej.');
    await user.click(screen.getByRole('button', { name: 'Przejrzyj teraz' }));

    expect(sent).toContain(`POST ${FINDINGS}/scan`);
  });

  it('lets a finding be called fine', async () => {
    const sent: string[] = [];
    mockApi(
      { [FINDINGS]: jsonResponse([KEY]), [`${FINDINGS}/${KEY.id}`]: jsonResponse(KEY) },
      sent,
    );
    const user = userEvent.setup();
    show();

    await screen.findByText('Klucz AWS');
    await user.click(screen.getByRole('button', { name: 'Uznaj za nieistotne: deploy.py' }));

    expect(sent).toContain(`PATCH ${FINDINGS}/${KEY.id}`);
  });
});

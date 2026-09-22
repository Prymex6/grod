import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ThemeProvider } from '../../theme/ThemeProvider';
import { GroupPage } from './GroupPage';
import { ProfilePage } from './ProfilePage';

const PROJECT = {
  id: '66666666-6666-4666-8666-666666666666',
  ownerLogin: 'kowale',
  slug: 'narzedzia',
  name: 'Narzedzia',
  description: 'Wspolne narzedzia',
  visibility: 'private' as const,
  defaultBranch: 'main',
  empty: false,
  cloneUrl: 'http://localhost:5173/kowale/narzedzia.git',
  createdAt: '2026-09-18T09:00:00Z',
  access: { read: true, write: true, manage: false, own: false },
  stars: 3,
  starred: false,
};

const GROUP = {
  id: '77777777-7777-4777-8777-777777777777',
  slug: 'kowale',
  name: 'Kowale',
  description: 'Wspolne narzedzia',
  visibility: 'private' as const,
  createdAt: '2026-09-18T08:00:00Z',
  role: 'guest' as const,
  memberCount: 2,
};

const MEMBERS = [
  {
    login: 'bartek',
    displayName: 'Bartek',
    role: 'owner' as const,
    createdAt: '2026-09-18T08:00:00Z',
  },
  {
    login: 'anna.k',
    displayName: 'Anna Kowalska',
    role: 'developer' as const,
    createdAt: '2026-09-18T08:30:00Z',
  },
];

const PROFILE = {
  login: 'bartek',
  displayName: 'Bartek',
  createdAt: '2026-09-17T18:00:00Z',
  projects: [PROJECT],
  starsGiven: 1,
  starsReceived: 3,
};

const jsonResponse = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

const mockApi = (answers: Record<string, Response>): void => {
  vi.stubGlobal(
    'fetch',
    vi.fn((path: string) =>
      Promise.resolve(answers[path] ?? jsonResponse({ detail: 'not mocked' }, 404)),
    ),
  );
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('GroupPage', () => {
  it('shows the projects and the members of a group', async () => {
    mockApi({
      '/api/v1/groups/kowale': jsonResponse(GROUP),
      '/api/v1/groups/kowale/projects': jsonResponse([PROJECT]),
      '/api/v1/groups/kowale/members': jsonResponse(MEMBERS),
    });
    render(
      <MemoryRouter initialEntries={['/groups/kowale']}>
        <ThemeProvider>
          <Routes>
            <Route path="/groups/:slug" element={<GroupPage />} />
          </Routes>
        </ThemeProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText('Kowale')).toBeInTheDocument();
    expect(screen.getByText('kowale/narzedzia')).toBeInTheDocument();
    expect(screen.getByText('Anna Kowalska')).toBeInTheDocument();
    expect(screen.getByText('właściciel')).toBeInTheDocument();
    // A guest may look, not change: no form to add anybody.
    expect(screen.queryByRole('button', { name: 'Dodaj' })).not.toBeInTheDocument();
  });
});

describe('ProfilePage', () => {
  it('counts the projects and the stars of an account', async () => {
    mockApi({ '/api/v1/users/bartek': jsonResponse(PROFILE) });
    render(
      <MemoryRouter initialEntries={['/bartek']}>
        <ThemeProvider>
          <Routes>
            <Route path="/:login" element={<ProfilePage />} />
          </Routes>
        </ThemeProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText('Bartek')).toBeInTheDocument();
    expect(screen.getByText('otrzymane gwiazdki')).toBeInTheDocument();
    expect(screen.getByLabelText('Gwiazdki: 3')).toBeInTheDocument();
  });
});

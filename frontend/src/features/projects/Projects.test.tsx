import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ThemeProvider } from '../../theme/ThemeProvider';
import { ProjectPage } from './ProjectPage';
import { ProjectSettings } from './ProjectSettings';
import { ProjectsPage } from './ProjectsPage';

const PROJECT = {
  id: '33333333-3333-4333-8333-333333333333',
  ownerLogin: 'bartek',
  slug: 'first-project',
  name: 'First project',
  description: 'Test konsoli',
  visibility: 'private' as const,
  defaultBranch: 'main',
  empty: false,
  cloneUrl: 'http://localhost:5173/bartek/first-project.git',
  createdAt: '2026-09-17T21:00:00Z',
  access: { read: true, write: true, manage: true, own: true },
  stars: 0,
  starred: false,
};

const TREE = [
  { name: 'src', path: 'src', type: 'tree' as const, size: null },
  { name: 'README.md', path: 'README.md', type: 'blob' as const, size: 76 },
];

const COMMIT_HASH = '00296a4bcf653ebf27c73f618881bd192aa33b4d';

const COMMITS = [
  {
    hash: COMMIT_HASH,
    authorName: 'Bartek',
    authorEmail: 'bartek@grod.dev',
    authoredAt: '2026-09-17T21:31:14Z',
    subject: 'Pierwszy commit w Grodzie',
  },
];

const jsonResponse = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

/** Answers the project endpoints, whatever order the pages call them in. */
const mockApi = (overrides: Record<string, Response> = {}): ReturnType<typeof vi.fn> => {
  const base = '/api/v1/projects/bartek/first-project';
  const answers: Record<string, () => Response> = {
    '/api/v1/projects': () => jsonResponse([PROJECT]),
    [base]: () => jsonResponse(PROJECT),
    [`${base}/branches`]: () => jsonResponse([{ name: 'main', commit: COMMIT_HASH }]),
    [`${base}/tree?ref=main`]: () => jsonResponse(TREE),
    [`${base}/commits?ref=main&limit=30`]: () => jsonResponse(COMMITS),
  };
  const fetchMock = vi.fn((path: string) => {
    const override = overrides[path];
    if (override) return Promise.resolve(override);
    const answer = answers[path];
    return Promise.resolve(answer ? answer() : jsonResponse({ detail: 'not mocked' }, 404));
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
};

const renderProjects = (): void => {
  render(
    <MemoryRouter>
      <ThemeProvider>
        <ProjectsPage />
      </ThemeProvider>
    </MemoryRouter>,
  );
};

const renderProject = (search = ''): void => {
  render(
    <MemoryRouter initialEntries={[`/bartek/first-project${search}`]}>
      <ThemeProvider>
        <Routes>
          <Route path="/:owner/:slug" element={<ProjectPage />} />
        </Routes>
      </ThemeProvider>
    </MemoryRouter>,
  );
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('ProjectsPage', () => {
  it('lists the projects with their visibility', async () => {
    mockApi();
    renderProjects();

    expect(await screen.findByText('bartek/first-project')).toBeInTheDocument();
    expect(screen.getByText('prywatny')).toBeInTheDocument();
  });

  it('says so when there is no project yet', async () => {
    mockApi({ '/api/v1/projects': jsonResponse([]) });
    renderProjects();

    expect(await screen.findByText('Nie masz jeszcze żadnego projektu.')).toBeInTheDocument();
  });
});

describe('ProjectPage', () => {
  it('shows the file tree of the default branch', async () => {
    mockApi();
    renderProject();

    expect(await screen.findByText('src')).toBeInTheDocument();
    expect(screen.getByText('README.md')).toBeInTheDocument();
    expect(screen.getByText('76 B')).toBeInTheDocument();
  });

  it('shows the history after switching to the commits tab', async () => {
    mockApi();
    const user = userEvent.setup();
    renderProject();

    await user.click(await screen.findByRole('button', { name: 'Commity' }));

    expect(await screen.findByText('Pierwszy commit w Grodzie')).toBeInTheDocument();
    expect(screen.getByText('00296a4b')).toBeInTheDocument();
  });

  it('explains how to push into an empty repository', async () => {
    mockApi({
      '/api/v1/projects/bartek/first-project': jsonResponse({ ...PROJECT, empty: true }),
    });
    renderProject();

    expect(await screen.findByText('Repozytorium jest puste')).toBeInTheDocument();
    expect(
      screen.getByText(/git remote add origin http:\/\/localhost:5173\/bartek/u),
    ).toBeInTheDocument();
  });

  it('reports a project it cannot read', async () => {
    mockApi({
      '/api/v1/projects/bartek/first-project': jsonResponse({ detail: 'No such project' }, 404),
    });
    renderProject();

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Nie ma takiego projektu albo nie masz do niego dostępu.',
    );
  });
});

const SEARCH_MATCHES = [
  { path: 'README.md', lineNumber: 1, line: '# First project w Grodzie' },
  { path: 'src/main.py', lineNumber: 2, line: '    print("Witaj w Grodzie")' },
];

const PROTECTED_RULE = {
  id: '55555555-5555-4555-8555-555555555555',
  pattern: 'main',
  createdAt: '2026-09-17T22:00:00Z',
};

describe('ProjectPage search and settings', () => {
  it('shows the lines a search found', async () => {
    mockApi({
      '/api/v1/projects/bartek/first-project/search?q=Grodzie&ref=main':
        jsonResponse(SEARCH_MATCHES),
    });
    const user = userEvent.setup();
    renderProject('?tab=search');

    await user.type(await screen.findByLabelText('Szukaj w plikach tej gałęzi…'), 'Grodzie');
    // Two buttons read "Szukaj": the tab and the one inside the form.
    await user.click(within(screen.getByRole('search')).getByRole('button', { name: 'Szukaj' }));

    expect(await screen.findByText('README.md:1')).toBeInTheDocument();
    expect(screen.getByText('src/main.py:2')).toBeInTheDocument();
  });

  it('keeps the settings tab away from somebody who may not manage the project', async () => {
    mockApi({
      '/api/v1/projects/bartek/first-project': jsonResponse({
        ...PROJECT,
        access: { read: true, write: false, manage: false, own: false },
      }),
    });
    renderProject('?tab=settings');

    // The API decides what the caller may do; a guest falls back to the code
    // view instead of the settings.
    expect(await screen.findByText('README.md')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Ustawienia' })).not.toBeInTheDocument();
  });

  it('lists the protected branches of a project', async () => {
    mockApi({
      '/api/v1/projects/bartek/first-project/protected-branches': jsonResponse([PROTECTED_RULE]),
    });
    render(
      <MemoryRouter>
        <ThemeProvider>
          <ProjectSettings project={PROJECT} />
        </ThemeProvider>
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole('button', { name: 'Zdejmij ochronę z main' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Usuń projekt' })).toBeDisabled();
  });
});

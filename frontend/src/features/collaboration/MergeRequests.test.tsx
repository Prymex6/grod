import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ThemeProvider } from '../../theme/ThemeProvider';
import type { Project } from '../projects/api';
import { MergeRequestDetail } from './MergeRequestDetail';
import { parsePatch } from './diff';

const PATCH = `diff --git a/src/main.py b/src/main.py
index 1111111..2222222 100644
--- a/src/main.py
+++ b/src/main.py
@@ -1,3 +1,4 @@
 def main():
-    print("old")
+    print("new")
+    return 0
 `;

const PROJECT: Project = {
  id: '44444444-4444-4444-8444-444444444444',
  ownerLogin: 'bartek',
  slug: 'first-project',
  name: 'First project',
  description: '',
  visibility: 'private',
  defaultBranch: 'main',
  empty: false,
  cloneUrl: 'http://localhost:5173/bartek/first-project.git',
  createdAt: '2026-09-18T08:00:00Z',
  access: { read: true, write: true, manage: true, own: true },
  stars: 0,
  starred: false,
};

const REQUEST = {
  id: '55555555-5555-4555-8555-555555555555',
  number: 1,
  title: 'Dodaj poradnik',
  description: 'Nowy rozdział',
  state: 'open' as const,
  sourceBranch: 'feature',
  targetBranch: 'main',
  mergeCommit: null,
  author: { login: 'bartek', displayName: 'Bartek' },
  createdAt: '2026-09-18T09:00:00Z',
  updatedAt: null,
  mergedAt: null,
  closedAt: null,
};

const CHANGES = [{ path: 'src/main.py', additions: 2, deletions: 1, binary: false, patch: PATCH }];

const jsonResponse = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

const BASE = '/api/v1/projects/bartek/first-project/merge-requests/1';

const mockApi = (overrides: Record<string, Response> = {}): void => {
  const answers: Record<string, () => Response> = {
    [BASE]: () => jsonResponse(REQUEST),
    [`${BASE}/comments`]: () => jsonResponse([]),
    [`${BASE}/commits`]: () => jsonResponse([]),
    [`${BASE}/changes`]: () => jsonResponse(CHANGES),
    [`${BASE}/findings`]: () => jsonResponse([]),
    [`${BASE}/stack`]: () => jsonResponse([]),
    [`${BASE}/approvals`]: () =>
      jsonResponse({ given: [], required: 0, counted: 0, missingOwners: [], satisfied: true }),
  };
  vi.stubGlobal(
    'fetch',
    vi.fn((path: string) => {
      const override = overrides[path];
      if (override) return Promise.resolve(override);
      const answer = answers[path];
      return Promise.resolve(answer ? answer() : jsonResponse({ detail: 'not mocked' }, 404));
    }),
  );
};

const renderDetail = (): void => {
  render(
    <MemoryRouter>
      <ThemeProvider>
        <MergeRequestDetail
          project={PROJECT}
          number={1}
          signedIn
          mayMerge
          login="bartek"
          onBack={() => undefined}
          onOpen={() => undefined}
        />
      </ThemeProvider>
    </MemoryRouter>,
  );
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('parsePatch', () => {
  it('numbers the lines on both sides of the change', () => {
    const [hunk] = parsePatch(PATCH);

    expect(hunk?.header).toBe('@@ -1,3 +1,4 @@');
    expect(hunk?.lines.map((line) => line.kind)).toEqual([
      'context',
      'removed',
      'added',
      'added',
      'context',
    ]);
    // The removed line keeps its old number and has none on the new side.
    expect(hunk?.lines[1]).toMatchObject({ oldNumber: 2, newNumber: null });
    expect(hunk?.lines[2]).toMatchObject({ oldNumber: null, newNumber: 2 });
  });

  it('ignores a patch without a hunk header', () => {
    expect(parsePatch('Binary files differ\n')).toEqual([]);
  });
});

describe('MergeRequestDetail', () => {
  it('shows the branches, the state and the changed file', async () => {
    mockApi();
    const user = userEvent.setup();
    renderDetail();

    expect(await screen.findByText('Dodaj poradnik')).toBeInTheDocument();
    expect(screen.getAllByText('feature').length).toBeGreaterThan(0);
    expect(screen.getByText('otwarty')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Zmiany' }));

    expect(await screen.findByText('src/main.py')).toBeInTheDocument();
    expect(screen.getByText('+2')).toBeInTheDocument();
    expect(screen.getByText('print("new")')).toBeInTheDocument();
  });

  it('lists the conflicting files when the merge is refused', async () => {
    mockApi({
      [`${BASE}/merge`]: jsonResponse(
        { detail: { message: 'The branches conflict', conflicts: ['README.md'] } },
        409,
      ),
    });
    const user = userEvent.setup();
    renderDetail();

    await user.click(await screen.findByRole('button', { name: 'Scal' }));

    expect(await screen.findByText('Pliki w konflikcie')).toBeInTheDocument();
    expect(screen.getByText('README.md')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Scal' })).toBeDisabled();
  });
});

describe('stos merge requestów', () => {
  const STACK = [
    {
      number: 1,
      title: 'Pierwsza',
      state: 'open' as const,
      sourceBranch: 'pierwsza',
      targetBranch: 'main',
      position: 1,
    },
    {
      number: 2,
      title: 'Druga',
      state: 'open' as const,
      sourceBranch: 'druga',
      targetBranch: 'pierwsza',
      position: 2,
    },
  ];

  it('shows the whole stack with the one that goes in first at the top', async () => {
    mockApi({ [`${BASE}/stack`]: jsonResponse(STACK) });
    renderDetail();

    expect(await screen.findByText('Stos merge requestów: 2')).toBeInTheDocument();
    expect(screen.getByText('Pierwsza')).toBeInTheDocument();
    expect(screen.getByText('1. !1')).toBeInTheDocument();
    expect(screen.getByText('2. !2')).toBeInTheDocument();
  });

  it('says nothing about a request that stands alone', async () => {
    mockApi();
    renderDetail();

    // The title is enough to know the view has loaded.
    await screen.findByText('Dodaj poradnik');
    expect(screen.queryByText(/Stos merge/)).not.toBeInTheDocument();
  });
});

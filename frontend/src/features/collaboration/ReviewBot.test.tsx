import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ThemeProvider } from '../../theme/ThemeProvider';
import type { Project } from '../projects/api';
import { MergeRequestDetail } from './MergeRequestDetail';

const PROJECT: Project = {
  id: '77777777-7777-4777-8777-777777777777',
  ownerLogin: 'bartek',
  slug: 'first-project',
  name: 'First project',
  description: '',
  visibility: 'private',
  defaultBranch: 'main',
  empty: false,
  cloneUrl: 'http://localhost:5173/bartek/first-project.git',
  createdAt: '2026-09-21T08:00:00Z',
  access: { read: true, write: true, manage: true, own: true },
  stars: 0,
  starred: false,
};

const REQUEST = {
  id: '11111111-1111-4111-8111-111111111111',
  number: 1,
  title: 'Poprawka',
  description: '',
  state: 'open' as const,
  sourceBranch: 'fix',
  targetBranch: 'main',
  mergeCommit: null,
  author: { login: 'bartek', displayName: 'Bartek' },
  createdAt: '2026-09-21T08:00:00Z',
  updatedAt: '2026-09-21T08:00:00Z',
  mergedAt: null,
  closedAt: null,
};

const CHANGES = [
  {
    path: 'src/main.py',
    additions: 1,
    deletions: 0,
    binary: false,
    patch: '@@ -0,0 +1 @@\n+print("x")\n',
  },
];

const COMMENT = {
  id: '22222222-2222-4222-8222-222222222222',
  body: 'Lepiej tak:\n\n```suggestion\nprint("poprawione")\n```',
  filePath: 'src/main.py',
  lineNumber: 1,
  author: { login: 'anna.k', displayName: 'Anna Kowalska' },
  createdAt: '2026-09-21T08:10:00Z',
};

const FINDING = {
  path: 'src/main.py',
  line: 1,
  column: 5,
  tool: 'lintery',
  message: 'E501 Line too long (120 > 100)',
};

const BASE = '/api/v1/projects/bartek/first-project/merge-requests/1';

const jsonResponse = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

const mockApi = (overrides: Record<string, Response> = {}, sent: string[] = []): void => {
  const answers: Record<string, () => Response> = {
    [BASE]: () => jsonResponse(REQUEST),
    [`${BASE}/comments`]: () => jsonResponse([]),
    [`${BASE}/commits`]: () => jsonResponse([]),
    [`${BASE}/changes`]: () => jsonResponse(CHANGES),
    [`${BASE}/findings`]: () => jsonResponse([]),
    [`${BASE}/approvals`]: () =>
      jsonResponse({ given: [], required: 0, counted: 0, missingOwners: [], satisfied: true }),
  };
  vi.stubGlobal(
    'fetch',
    vi.fn((path: string, options?: { method?: string }) => {
      sent.push(`${options?.method ?? 'GET'} ${path}`);
      const override = overrides[path];
      if (override) return Promise.resolve(override);
      const answer = answers[path];
      return Promise.resolve(answer ? answer() : jsonResponse({ detail: 'not mocked' }, 404));
    }),
  );
};

const show = (): void => {
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

describe('remarks from the tools', () => {
  it('shows what a tool said under the line it is about', async () => {
    mockApi({ [`${BASE}/findings`]: jsonResponse([FINDING]) });
    show();

    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: /Zmiany/ }));

    expect(await screen.findByText(/E501 Line too long/)).toBeInTheDocument();
    expect(screen.getByText('lintery')).toBeInTheDocument();
  });

  it('says nothing when no run has looked at the branch', async () => {
    mockApi();
    show();

    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: /Zmiany/ }));

    expect(screen.queryByText(/E501/)).not.toBeInTheDocument();
  });
});

describe('suggestions in a review', () => {
  it('offers to take a suggestion that a comment carries', async () => {
    const sent: string[] = [];
    mockApi(
      {
        [`${BASE}/comments`]: jsonResponse([COMMENT]),
        [`${BASE}/comments/${COMMENT.id}/apply`]: jsonResponse({
          hash: '0'.repeat(40),
          shortHash: '0000000',
          subject: 'Zastosuj sugestię do src/main.py:1',
          authorName: 'Bartek',
          authoredAt: '2026-09-21T08:20:00Z',
        }),
      },
      sent,
    );
    show();

    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: /Zmiany/ }));
    await user.click(await screen.findByRole('button', { name: 'Zastosuj sugestię' }));

    expect(sent).toContain(`POST ${BASE}/comments/${COMMENT.id}/apply`);
  });

  it('offers nothing on a comment that is only a remark', async () => {
    mockApi({
      [`${BASE}/comments`]: jsonResponse([{ ...COMMENT, body: 'Tylko uwaga' }]),
    });
    show();

    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: /Zmiany/ }));

    expect(await screen.findByText('Tylko uwaga')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Zastosuj sugestię' })).not.toBeInTheDocument();
  });
});

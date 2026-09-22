import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ThemeProvider } from '../../theme/ThemeProvider';
import type { Project } from '../projects/api';
import { PipelineDetail } from './PipelineDetail';
import { PipelineList } from './PipelineList';

const PROJECT: Project = {
  id: '88888888-8888-4888-8888-888888888888',
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

const JOBS = [
  {
    id: 'aaaaaaaa-1111-4111-8111-111111111111',
    name: 'budowa',
    stage: 'budowa',
    state: 'success' as const,
    image: null,
    script: ['echo "buduje"'],
    startedAt: '2026-09-18T10:00:00Z',
    finishedAt: '2026-09-18T10:00:05Z',
  },
  {
    id: 'bbbbbbbb-2222-4222-8222-222222222222',
    name: 'testy',
    stage: 'testy',
    state: 'failed' as const,
    image: 'python:3.14',
    script: ['pytest'],
    startedAt: '2026-09-18T10:00:06Z',
    finishedAt: '2026-09-18T10:00:20Z',
  },
];

const PIPELINE = {
  id: 'cccccccc-3333-4333-8333-333333333333',
  number: 7,
  ref: 'main',
  commit: '00296a4bcf653ebf27c73f618881bd192aa33b4d',
  commitSubject: 'Dodaj bufor',
  state: 'failed' as const,
  createdAt: '2026-09-18T10:00:00Z',
  startedAt: '2026-09-18T10:00:00Z',
  finishedAt: '2026-09-18T10:00:20Z',
  jobs: JOBS,
};

const BASE = '/api/v1/projects/bartek/first-project';

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

describe('PipelineList', () => {
  it('shows the pipelines with their branch and state', async () => {
    mockApi({ [`${BASE}/pipelines`]: jsonResponse([PIPELINE]) });
    render(
      <MemoryRouter>
        <ThemeProvider>
          <PipelineList
            project={PROJECT}
            reference="main"
            mayRun
            onOpenPipeline={() => undefined}
          />
        </ThemeProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText('Dodaj bufor')).toBeInTheDocument();
    expect(screen.getByText('#7')).toBeInTheDocument();
    expect(screen.getByText('błąd')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Uruchom dla main' })).toBeInTheDocument();
  });

  it('points at the file when a branch describes no pipeline', async () => {
    mockApi({ [`${BASE}/pipelines`]: jsonResponse([]) });
    render(
      <MemoryRouter>
        <ThemeProvider>
          <PipelineList
            project={PROJECT}
            reference="main"
            mayRun={false}
            onOpenPipeline={() => undefined}
          />
        </ThemeProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText('.grod/ci.yml')).toBeInTheDocument();
    // Somebody without the right to push may not start one either.
    expect(screen.queryByRole('button', { name: /Uruchom/ })).not.toBeInTheDocument();
  });
});

describe('PipelineDetail', () => {
  it('shows the jobs by stage and the log of the chosen one', async () => {
    mockApi({
      [`${BASE}/pipelines/7`]: jsonResponse(PIPELINE),
      [`${BASE}/jobs/${JOBS[0]?.id ?? ''}/log`]: jsonResponse({
        id: JOBS[0]?.id,
        state: 'success',
        log: '$ echo "buduje"\nbuduje\n',
      }),
      [`${BASE}/jobs/${JOBS[1]?.id ?? ''}/log`]: jsonResponse({
        id: JOBS[1]?.id,
        state: 'failed',
        log: 'E   assert 1 == 2\n',
      }),
    });
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <ThemeProvider>
          <PipelineDetail project={PROJECT} number={7} mayRun onBack={() => undefined} />
        </ThemeProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText('budowa', { selector: 'h2' })).toBeInTheDocument();
    expect(await screen.findByText(/buduje/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'testy' }));

    expect(await screen.findByText(/assert 1 == 2/)).toBeInTheDocument();
    // A pipeline that already ended cannot be stopped.
    expect(screen.queryByRole('button', { name: 'Przerwij' })).not.toBeInTheDocument();
  });
});

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { jsonResponse, mockApi, nthButton, show } from '../../test/api';
import { FunctionsPage } from './FunctionsPage';
import type { GrodFunction } from './api';

const FUNCTIONS = '/api/v1/functions';

const GREETING: GrodFunction = {
  id: 'aaaaaaaa-1111-4111-8111-111111111111',
  name: 'greeting',
  runtime: 'python',
  source: "print('hello')\n",
  timeoutSeconds: 5,
  memoryMb: 128,
  calls: 4,
  failures: 0,
  lastCalledAt: '2026-09-20T09:00:00Z',
  lastDurationMs: 12,
  lastError: '',
  createdAt: '2026-09-20T08:00:00Z',
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('FunctionsPage', () => {
  it('lists the functions with how often each has been called', async () => {
    mockApi({ [FUNCTIONS]: jsonResponse([GREETING]) });
    show(<FunctionsPage />);

    expect((await screen.findAllByText('greeting')).length).toBeGreaterThan(0);
    expect(screen.getByText(/wywołań: 4/)).toBeInTheDocument();
  });

  it('says so when there is no function yet', async () => {
    mockApi({ [FUNCTIONS]: jsonResponse([]) });
    show(<FunctionsPage />);

    expect(await screen.findByText('Nie masz jeszcze żadnej funkcji.')).toBeInTheDocument();
  });

  it('sends a new function to the API', async () => {
    const sent = mockApi({ [FUNCTIONS]: jsonResponse([]) });
    const user = userEvent.setup();
    show(<FunctionsPage />);

    await screen.findByText('Nie masz jeszcze żadnej funkcji.');
    await user.click(screen.getByRole('button', { name: 'Nowa funkcja' }));
    await user.type(screen.getByLabelText('Nazwa'), 'greeting');
    await user.click(nthButton('Nowa funkcja', 1));

    expect(sent).toContain(`POST ${FUNCTIONS}`);
  });

  it('shows a plain message when the list cannot be read', async () => {
    mockApi({});
    show(<FunctionsPage />);

    expect(await screen.findByText('Nie udało się wczytać funkcji.')).toBeInTheDocument();
  });
});

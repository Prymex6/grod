import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { jsonResponse, mockApi, nthButton, show } from '../../test/api';
import { QueuesPage } from './QueuesPage';
import type { Queue } from './api';

const QUEUES = '/api/v1/queues';

const ORDERS: Queue = {
  id: 'aaaaaaaa-1111-4111-8111-111111111111',
  name: 'orders',
  visibilitySeconds: 30,
  maxAttempts: 5,
  waiting: 2,
  taken: 1,
  dead: 0,
  createdAt: '2026-09-20T08:00:00Z',
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('QueuesPage', () => {
  it('lists the queues and how much is standing in each', async () => {
    mockApi({ [QUEUES]: jsonResponse([ORDERS]) });
    show(<QueuesPage />);

    expect(await screen.findByText('orders')).toBeInTheDocument();
    expect(screen.getByText(/czeka 2/)).toBeInTheDocument();
    expect(screen.getByText(/w rękach 1/)).toBeInTheDocument();
  });

  it('says so when there is no queue yet', async () => {
    mockApi({ [QUEUES]: jsonResponse([]) });
    show(<QueuesPage />);

    expect(await screen.findByText('Nie masz jeszcze żadnej kolejki.')).toBeInTheDocument();
  });

  it('sends a new queue to the API', async () => {
    const sent = mockApi({ [QUEUES]: jsonResponse([]) });
    const user = userEvent.setup();
    show(<QueuesPage />);

    await screen.findByText('Nie masz jeszcze żadnej kolejki.');
    await user.click(screen.getByRole('button', { name: 'Nowa kolejka' }));
    await user.type(screen.getByLabelText('Nazwa kolejki'), 'invoices');
    await user.click(nthButton('Nowa kolejka', 1));

    expect(sent).toContain(`POST ${QUEUES}`);
  });

  it('shows a plain message when the list cannot be read', async () => {
    mockApi({});
    show(<QueuesPage />);

    expect(await screen.findByText('Nie udało się wczytać kolejek.')).toBeInTheDocument();
  });
});

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { jsonResponse, mockApi, nthButton, show } from '../../test/api';
import { StoragePage } from './StoragePage';
import type { Bucket } from './api';

const BUCKETS = '/api/v1/storage/buckets';

const PHOTOS: Bucket = {
  id: 'aaaaaaaa-1111-4111-8111-111111111111',
  name: 'photos',
  access: 'private',
  createdAt: '2026-09-20T08:00:00Z',
  objects: 3,
  bytes: 2048,
};

/** The page header and the submit button carry the same label. */
const submit = (): HTMLElement => nthButton('Nowy kosz', 1);

const openTheForm = async (user: ReturnType<typeof userEvent.setup>): Promise<void> => {
  await user.click(screen.getByRole('button', { name: 'Nowy kosz' }));
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('StoragePage', () => {
  it('lists the buckets with how much sits in each', async () => {
    mockApi({ [BUCKETS]: jsonResponse([PHOTOS]) });
    show(<StoragePage />);

    expect(await screen.findByText('photos')).toBeInTheDocument();
    expect(screen.getByText(/plików: 3/)).toBeInTheDocument();
    expect(screen.getByText('prywatny')).toBeInTheDocument();
  });

  it('says so when there is no bucket yet', async () => {
    mockApi({ [BUCKETS]: jsonResponse([]) });
    show(<StoragePage />);

    expect(await screen.findByText('Nie masz jeszcze żadnego kosza.')).toBeInTheDocument();
  });

  it('sends a new bucket to the API', async () => {
    const sent = mockApi({ [BUCKETS]: jsonResponse([]) });
    const user = userEvent.setup();
    show(<StoragePage />);

    await screen.findByText('Nie masz jeszcze żadnego kosza.');
    await openTheForm(user);
    await user.type(screen.getByLabelText('Nazwa kosza'), 'holiday');
    await user.click(submit());

    expect(sent).toContain(`POST ${BUCKETS}`);
  });

  it('explains a name that is already taken instead of failing quietly', async () => {
    const taken = jsonResponse({ detail: 'A bucket with that name already exists' }, 409);
    vi.stubGlobal(
      'fetch',
      vi.fn((_path: string, options?: { method?: string }) =>
        Promise.resolve(options?.method === 'POST' ? taken.clone() : jsonResponse([])),
      ),
    );
    const user = userEvent.setup();
    show(<StoragePage />);

    await screen.findByText('Nie masz jeszcze żadnego kosza.');
    await openTheForm(user);
    await user.type(screen.getByLabelText('Nazwa kosza'), 'photos');
    await user.click(submit());

    expect(await screen.findByText('Kosz o tej nazwie już istnieje.')).toBeInTheDocument();
  });

  it('shows a plain message when the list cannot be read', async () => {
    mockApi({});
    show(<StoragePage />);

    expect(await screen.findByText('Nie udało się wczytać koszy.')).toBeInTheDocument();
  });
});

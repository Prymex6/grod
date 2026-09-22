import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { jsonResponse, mockApi, show } from '../../test/api';
import { AppsPage } from './AppsPage';
import type { Application } from './api';

const APPS = '/api/v1/apps';
const ENGINE = `${APPS}/engine`;

const SITE: Application = {
  id: 'aaaaaaaa-1111-4111-8111-111111111111',
  name: 'my-site',
  image: 'nginx:1.27-alpine',
  command: '',
  environment: {},
  port: 80,
  hostPort: 14000,
  memoryMb: 256,
  cpus: 0.5,
  state: 'stopped',
  lastError: '',
  createdAt: '2026-09-20T08:00:00Z',
  url: null,
};

const RUNNING: Application = { ...SITE, state: 'running', url: 'http://127.0.0.1:14000' };

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('AppsPage', () => {
  it('lists the applications with the image each one runs', async () => {
    mockApi({ [APPS]: jsonResponse([SITE]), [ENGINE]: jsonResponse({ available: true }) });
    show(<AppsPage />);

    expect(await screen.findByText('my-site')).toBeInTheDocument();
    expect(screen.getByText(/nginx:1.27-alpine/)).toBeInTheDocument();
  });

  it('names every control after the application it acts on', async () => {
    mockApi({ [APPS]: jsonResponse([SITE]), [ENGINE]: jsonResponse({ available: true }) });
    show(<AppsPage />);

    // Icon-only buttons, so the name is the only thing a screen reader gets.
    expect(await screen.findByRole('button', { name: 'Uruchom my-site' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Zatrzymaj my-site' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Usuń my-site' })).toBeInTheDocument();
  });

  it('warns when the instance has no container engine', async () => {
    mockApi({ [APPS]: jsonResponse([]), [ENGINE]: jsonResponse({ available: false }) });
    show(<AppsPage />);

    expect(
      await screen.findByText(
        'Ta instancja nie ma silnika kontenerów, więc aplikacji nie da się uruchomić.',
      ),
    ).toBeInTheDocument();
  });

  it('asks the API to start an application', async () => {
    const sent = mockApi({
      [APPS]: jsonResponse([SITE]),
      [ENGINE]: jsonResponse({ available: true }),
      [`${APPS}/my-site/start`]: jsonResponse(RUNNING),
    });
    const user = userEvent.setup();
    show(<AppsPage />);

    await user.click(await screen.findByRole('button', { name: 'Uruchom my-site' }));

    expect(sent).toContain(`POST ${APPS}/my-site/start`);
  });

  it('says so when there is no application yet', async () => {
    mockApi({ [APPS]: jsonResponse([]), [ENGINE]: jsonResponse({ available: true }) });
    show(<AppsPage />);

    expect(await screen.findByText('Nie masz jeszcze żadnej aplikacji.')).toBeInTheDocument();
  });

  it('shows a plain message when the list cannot be read', async () => {
    mockApi({});
    show(<AppsPage />);

    expect(await screen.findByText('Nie udało się wczytać aplikacji.')).toBeInTheDocument();
  });
});

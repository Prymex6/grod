import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ThemeProvider } from '../../theme/ThemeProvider';
import { SettingsPage } from './SettingsPage';

const ACCOUNT = {
  id: '00000000-0000-4000-8000-000000000000',
  email: 'anna.k@grod.dev',
  displayName: 'Anna Kowalska',
  totpEnabled: false,
  createdAt: '2026-09-17T18:00:00Z',
};

const PASSKEY = {
  id: '11111111-1111-4111-8111-111111111111',
  label: 'Klucz z laptopa',
  createdAt: '2026-09-17T18:10:00Z',
  lastUsedAt: null,
};

const AUTHORIZATION = {
  clientId: 'app-123',
  name: 'Moja aplikacja',
  scopes: ['openid', 'email'],
  grantedAt: '2026-09-17T18:15:00Z',
};

const TOKEN = {
  id: '22222222-2222-4222-8222-222222222222',
  name: 'Laptop',
  scopes: ['repo:read', 'repo:write'],
  createdAt: '2026-09-17T18:12:00Z',
  expiresAt: null,
  lastUsedAt: null,
};

const SSH_KEY = {
  id: '44444444-4444-4444-8444-444444444444',
  name: 'Laptop SSH',
  algorithm: 'ssh-ed25519',
  fingerprint: 'SHA256:abcdef1234567890',
  createdAt: '2026-09-17T18:14:00Z',
  lastUsedAt: null,
};

const SESSIONS = [
  { createdAt: '2026-09-17T18:20:00Z', userAgent: 'Chrome na Windowsie', current: true },
  { createdAt: '2026-09-17T18:05:00Z', userAgent: 'Telefon', current: false },
];

const jsonResponse = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

/** Answers each endpoint the page calls, whatever the order. */
const mockApi = (overrides: Record<string, Response> = {}): ReturnType<typeof vi.fn> => {
  const answers: Record<string, () => Response> = {
    '/api/v1/auth/me': () => jsonResponse(ACCOUNT),
    '/api/v1/auth/passkeys': () => jsonResponse([PASSKEY]),
    '/api/v1/auth/sessions': () => jsonResponse(SESSIONS),
    '/api/v1/oauth/authorizations': () => jsonResponse([AUTHORIZATION]),
    '/api/v1/tokens': () => jsonResponse([TOKEN]),
    '/api/v1/ssh-keys': () => jsonResponse([SSH_KEY]),
    '/api/v1/auth/totp/setup': () =>
      jsonResponse({ secret: 'JBSWY3DPEHPK3PXP', provisioningUri: 'otpauth://totp/test' }),
  };
  const fetchMock = vi.fn((path: string) => {
    const override = overrides[path];
    if (override) return Promise.resolve(override);
    const answer = answers[path];
    return Promise.resolve(answer ? answer() : jsonResponse({ detail: 'not mocked' }, 500));
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
};

const renderSettings = (): void => {
  render(
    <MemoryRouter>
      <ThemeProvider>
        <SettingsPage />
      </ThemeProvider>
    </MemoryRouter>,
  );
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('SettingsPage', () => {
  it('shows two-factor state, passkeys and sessions', async () => {
    mockApi();
    renderSettings();

    expect(await screen.findByText('Wyłączone')).toBeInTheDocument();
    expect(screen.getByText('Klucz z laptopa')).toBeInTheDocument();
    expect(screen.getByText('Chrome na Windowsie')).toBeInTheDocument();
    expect(screen.getByText('To urządzenie')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Wyloguj pozostałe urządzenia (1)' })).toBeEnabled();
  });

  it('shows the secret to enter by hand when two-factor is being turned on', async () => {
    mockApi();
    const user = userEvent.setup();
    renderSettings();

    await user.click(await screen.findByRole('button', { name: 'Włącz' }));

    expect(await screen.findByText('JBSWY3DPEHPK3PXP')).toBeInTheDocument();
    expect(screen.getAllByLabelText(/^Cyfra \d z 6$/u)).toHaveLength(6);
  });

  it('reports a failure to load the settings', async () => {
    mockApi({ '/api/v1/auth/sessions': jsonResponse({ detail: 'boom' }, 500) });
    renderSettings();

    expect(await screen.findByRole('alert')).toHaveTextContent('Nie udało się wczytać ustawień.');
  });
});

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ThemeProvider } from '../../theme/ThemeProvider';
import { LoginPage } from './LoginPage';

const EMAIL = 'anna.k@grod.dev';
const PASSWORD = 'correct-horse-battery';

const ACCOUNT = {
  id: '00000000-0000-4000-8000-000000000000',
  email: EMAIL,
  displayName: 'Anna Kowalska',
  totpEnabled: false,
  createdAt: '2026-09-17T18:00:00Z',
};

const jsonResponse = (status: number, body: unknown): Response =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

const mockFetch = (...answers: (Response | Error)[]): ReturnType<typeof vi.fn> => {
  const fetchMock = vi.fn(() => {
    const answer = answers.shift();
    if (answer instanceof Error) return Promise.reject(answer);
    return Promise.resolve(answer ?? jsonResponse(500, {}));
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
};

const renderLoginPage = (): void => {
  render(
    <MemoryRouter>
      <ThemeProvider>
        <LoginPage />
      </ThemeProvider>
    </MemoryRouter>,
  );
};

const fillCredentials = async (user: ReturnType<typeof userEvent.setup>): Promise<void> => {
  await user.type(screen.getByLabelText('Adres e-mail'), EMAIL);
  await user.type(screen.getByLabelText('Hasło'), PASSWORD);
  await user.click(screen.getByRole('button', { name: 'Zaloguj się' }));
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('LoginPage', () => {
  it('shows the credentials step in Polish by default', () => {
    renderLoginPage();

    expect(screen.getByRole('heading', { name: 'Brama' })).toBeInTheDocument();
    expect(screen.getByLabelText('Adres e-mail')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Zaloguj się' })).toBeInTheDocument();
  });

  it('sends the credentials to Brama', async () => {
    const fetchMock = mockFetch(jsonResponse(200, { status: 'signed_in', account: ACCOUNT }));
    const user = userEvent.setup();
    renderLoginPage();

    await fillCredentials(user);

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/auth/login',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
      }),
    );
  });

  it('reports a wrong password', async () => {
    mockFetch(jsonResponse(401, { detail: 'Invalid email or password' }));
    const user = userEvent.setup();
    renderLoginPage();

    await fillCredentials(user);

    expect(await screen.findByRole('alert')).toHaveTextContent('Niepoprawny e-mail lub hasło.');
  });

  it('reports that the API is unreachable', async () => {
    mockFetch(new TypeError('Failed to fetch'));
    const user = userEvent.setup();
    renderLoginPage();

    await fillCredentials(user);

    expect(await screen.findByRole('alert')).toHaveTextContent('Brak połączenia z API Grodu.');
  });

  it('asks for the two-factor code and sends it with the pending token', async () => {
    const fetchMock = mockFetch(
      jsonResponse(200, { status: 'totp_required', pendingToken: 'pending-123' }),
      jsonResponse(200, { status: 'signed_in', account: { ...ACCOUNT, totpEnabled: true } }),
    );
    const user = userEvent.setup();
    renderLoginPage();

    await fillCredentials(user);

    expect(await screen.findAllByLabelText(/^Cyfra \d z 6$/u)).toHaveLength(6);

    await user.type(screen.getByLabelText('Cyfra 1 z 6'), '123456');
    await user.click(screen.getByRole('button', { name: 'Zweryfikuj i zaloguj' }));

    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/v1/auth/login/totp',
      expect.objectContaining({
        body: JSON.stringify({ pendingToken: 'pending-123', code: '123456' }),
      }),
    );
  });

  it('moves focus to the next box while the code is typed', async () => {
    mockFetch(jsonResponse(200, { status: 'totp_required', pendingToken: 'pending-123' }));
    const user = userEvent.setup();
    renderLoginPage();

    await fillCredentials(user);
    await user.type(await screen.findByLabelText('Cyfra 1 z 6'), '1');

    expect(screen.getByLabelText('Cyfra 2 z 6')).toHaveFocus();
  });
});

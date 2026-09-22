import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ThemeProvider } from '../../theme/ThemeProvider';
import { RegisterPage } from './RegisterPage';

const EMAIL = 'nowy@grod.dev';
const PASSWORD = 'correct-horse-battery';
const DISPLAY_NAME = 'Nowy Użytkownik';

const jsonResponse = (status: number, body: unknown): Response =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

const mockFetch = (answer: Response): ReturnType<typeof vi.fn> => {
  const fetchMock = vi.fn(() => Promise.resolve(answer));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
};

const fillForm = async (user: ReturnType<typeof userEvent.setup>): Promise<void> => {
  await user.type(screen.getByLabelText('Nazwa wyświetlana'), DISPLAY_NAME);
  await user.type(screen.getByLabelText('Adres e-mail'), EMAIL);
  await user.type(screen.getByLabelText('Hasło'), PASSWORD);
  await user.click(screen.getByRole('button', { name: 'Załóż konto' }));
};

const renderRegisterPage = (): void => {
  render(
    <MemoryRouter>
      <ThemeProvider>
        <RegisterPage />
      </ThemeProvider>
    </MemoryRouter>,
  );
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('RegisterPage', () => {
  it('sends the new account to Brama', async () => {
    const fetchMock = mockFetch(jsonResponse(201, { status: 'signed_in', account: {} }));
    const user = userEvent.setup();
    renderRegisterPage();

    await fillForm(user);

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/auth/register',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ email: EMAIL, displayName: DISPLAY_NAME, password: PASSWORD }),
      }),
    );
  });

  it('reports an address that is already taken', async () => {
    mockFetch(jsonResponse(409, { detail: 'This email is already registered' }));
    const user = userEvent.setup();
    renderRegisterPage();

    await fillForm(user);

    expect(await screen.findByRole('alert')).toHaveTextContent('Konto z tym adresem już istnieje.');
  });

  it('requires a password of at least twelve characters', () => {
    renderRegisterPage();

    expect(screen.getByLabelText('Hasło')).toHaveAttribute('minLength', '12');
  });
});

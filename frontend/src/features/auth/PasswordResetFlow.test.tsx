import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ThemeProvider } from '../../theme/ThemeProvider';
import { ForgotPasswordPage } from './ForgotPasswordPage';
import { ResetPasswordPage } from './ResetPasswordPage';

const EMAIL = 'anna.k@grod.dev';
const NEW_PASSWORD = 'brand-new-password-2026';
const TOKEN = 'reset-token-123';

const emptyResponse = (status: number): Response => new Response(null, { status });

const mockFetch = (answer: Response): ReturnType<typeof vi.fn> => {
  const fetchMock = vi.fn(() => Promise.resolve(answer));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
};

const renderPage = (page: 'forgot' | 'reset', search = ''): void => {
  render(
    <MemoryRouter initialEntries={[`/password/${page}${search}`]}>
      <ThemeProvider>
        {page === 'forgot' ? <ForgotPasswordPage /> : <ResetPasswordPage />}
      </ThemeProvider>
    </MemoryRouter>,
  );
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('ForgotPasswordPage', () => {
  it('asks Brama for a reset link and confirms it was sent', async () => {
    const fetchMock = mockFetch(emptyResponse(202));
    const user = userEvent.setup();
    renderPage('forgot');

    await user.type(screen.getByLabelText('Adres e-mail'), EMAIL);
    await user.click(screen.getByRole('button', { name: 'Wyślij link' }));

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/auth/password/reset-request',
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ email: EMAIL }) }),
    );
    expect(await screen.findByText(/link już do niego poleciał/u)).toBeInTheDocument();
  });
});

describe('ResetPasswordPage', () => {
  it('sends the token with the new password', async () => {
    const fetchMock = mockFetch(emptyResponse(204));
    const user = userEvent.setup();
    renderPage('reset', `?token=${TOKEN}`);

    await user.type(screen.getByLabelText('Nowe hasło'), NEW_PASSWORD);
    await user.type(screen.getByLabelText('Powtórz hasło'), NEW_PASSWORD);
    await user.click(screen.getByRole('button', { name: 'Zapisz hasło' }));

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/auth/password/reset',
      expect.objectContaining({
        body: JSON.stringify({ token: TOKEN, password: NEW_PASSWORD }),
      }),
    );
  });

  it('refuses two different passwords without calling the API', async () => {
    const fetchMock = mockFetch(emptyResponse(204));
    const user = userEvent.setup();
    renderPage('reset', `?token=${TOKEN}`);

    await user.type(screen.getByLabelText('Nowe hasło'), NEW_PASSWORD);
    await user.type(screen.getByLabelText('Powtórz hasło'), 'something-else-entirely');
    await user.click(screen.getByRole('button', { name: 'Zapisz hasło' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Hasła się różnią.');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('explains a link without a token', () => {
    mockFetch(emptyResponse(204));
    renderPage('reset');

    expect(screen.getByRole('alert')).toHaveTextContent('Ten link już nie działa.');
  });
});

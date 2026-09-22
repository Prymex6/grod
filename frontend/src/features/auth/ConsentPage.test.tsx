import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ThemeProvider } from '../../theme/ThemeProvider';
import { ConsentPage } from './ConsentPage';

const HANDLE = 'request-handle-123';
const REDIRECT_TO = 'https://app.example.com/callback?code=abc&state=xyz';

const jsonResponse = (status: number, body: unknown): Response =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

const mockFetch = (...answers: Response[]): ReturnType<typeof vi.fn> => {
  const fetchMock = vi.fn(() => Promise.resolve(answers.shift() ?? jsonResponse(500, {})));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
};

const renderConsentPage = (search = `?request=${HANDLE}`): void => {
  render(
    <MemoryRouter initialEntries={[`/oauth/consent${search}`]}>
      <ThemeProvider>
        <ConsentPage />
      </ThemeProvider>
    </MemoryRouter>,
  );
};

const assign = vi.fn();

beforeEach(() => {
  assign.mockClear();
  vi.stubGlobal('location', { assign, href: 'http://localhost:5173/oauth/consent' });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('ConsentPage', () => {
  it('shows the application and what it asks for', async () => {
    mockFetch(jsonResponse(200, { clientName: 'Moja aplikacja', scopes: ['openid', 'email'] }));
    renderConsentPage();

    expect(
      await screen.findByText(
        'Aplikacja Moja aplikacja chce uzyskać dostęp do Twojego konta w Grodzie.',
      ),
    ).toBeInTheDocument();
    expect(screen.getByText('Potwierdzenie Twojej tożsamości')).toBeInTheDocument();
    expect(screen.getByText('Twój adres e-mail')).toBeInTheDocument();
  });

  it('sends the browser back to the application after consent', async () => {
    mockFetch(
      jsonResponse(200, { clientName: 'Moja aplikacja', scopes: ['openid'] }),
      jsonResponse(200, { redirectTo: REDIRECT_TO }),
    );
    const user = userEvent.setup();
    renderConsentPage();

    await user.click(await screen.findByRole('button', { name: 'Zezwól' }));

    expect(assign).toHaveBeenCalledWith(REDIRECT_TO);
  });

  it('explains an expired request', async () => {
    mockFetch(jsonResponse(404, { detail: 'Request expired' }));
    renderConsentPage();

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Żądanie wygasło. Zacznij logowanie w aplikacji od nowa.',
    );
  });

  it('sends a visitor without a session to the sign-in screen', async () => {
    mockFetch(jsonResponse(401, { detail: 'Not signed in' }));
    renderConsentPage();

    await vi.waitFor(() => {
      expect(assign).toHaveBeenCalledWith(
        '/login?next=http%3A%2F%2Flocalhost%3A5173%2Foauth%2Fconsent',
      );
    });
  });
});

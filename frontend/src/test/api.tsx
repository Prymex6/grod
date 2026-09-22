import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router';
import { vi } from 'vitest';

import { ThemeProvider } from '../theme/ThemeProvider';

/** One answer the stubbed fetch should give, or a status to fail with. */
export type Answer = Response;

export const jsonResponse = (body: unknown, status = 200): Answer =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

export const emptyResponse = (status = 204): Answer => new Response(null, { status });

/**
 * Answer only the paths a test names, and record what was asked for.
 *
 * Anything not named comes back 404, so a component quietly calling an
 * endpoint the test did not think about shows up as a failure rather than
 * passing on a coincidence.
 */
export const mockApi = (answers: Record<string, Answer>, sent: string[] = []): string[] => {
  vi.stubGlobal(
    'fetch',
    vi.fn((path: string, options?: { method?: string }) => {
      sent.push(`${options?.method ?? 'GET'} ${path}`);
      const answer = answers[path];
      // A Response body can only be read once, so each answer is cloned.
      return Promise.resolve(answer ? answer.clone() : jsonResponse({ detail: 'not mocked' }, 404));
    }),
  );
  return sent;
};

/**
 * The nth control with this name.
 *
 * Several pages label the header button and the submit button alike, so a
 * test has to say which one it means.
 */
export const nthButton = (name: string, index: number): HTMLElement => {
  const found = screen.getAllByRole('button', { name });
  const button = found[index];
  if (button === undefined) throw new Error(`no button "${name}" at ${String(index)}`);
  return button;
};

/** Render a page the way the application does: inside a router and a theme. */
export const show = (element: ReactNode): void => {
  render(
    <MemoryRouter>
      <ThemeProvider>{element}</ThemeProvider>
    </MemoryRouter>,
  );
};

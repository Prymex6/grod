const API_PREFIX = '/api/v1';

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    /** Whatever the API put in "detail"; some refusals explain themselves there. */
    readonly detail: unknown = null,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/** Pull the "detail" out of a failed answer, ignoring anything that is not JSON. */
const detailOf = (body: string): unknown => {
  try {
    return (JSON.parse(body) as { detail?: unknown }).detail ?? null;
  } catch {
    return null;
  }
};

/** Raised when the API cannot be reached at all. */
export class NetworkError extends Error {
  constructor() {
    super('The API is unreachable');
    this.name = 'NetworkError';
  }
}

interface RequestOptions {
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  headers?: Record<string, string>;
  body?: string;
  signal?: AbortSignal;
}

const send = async <T>(path: string, options: RequestOptions): Promise<T> => {
  let response: Response;
  try {
    response = await fetch(`${API_PREFIX}${path}`, {
      ...options,
      headers: { Accept: 'application/json', ...options.headers },
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause;
    throw new NetworkError();
  }

  if (!response.ok) {
    throw new ApiError(
      `Request failed with status ${String(response.status)}`,
      response.status,
      detailOf(await response.text()),
    );
  }
  // Some answers carry no body at all (204 No Content, 202 Accepted).
  const body = await response.text();
  return (body === '' ? undefined : JSON.parse(body)) as T;
};

/** GET a JSON resource from the platform API. */
export const getJson = <T>(path: string, signal?: AbortSignal): Promise<T> =>
  send<T>(path, { method: 'GET', signal });

/** PUT a resource, for an action that may safely be repeated. */
export const sendPut = async (path: string): Promise<void> => {
  await send<undefined>(path, { method: 'PUT' });
};

/** DELETE a resource in the platform API. */
export const sendDelete = async (path: string): Promise<void> => {
  await send<undefined>(path, { method: 'DELETE' });
};

/** DELETE a resource that answers with a body of its own. */
export const sendDeleteJson = <T>(path: string): Promise<T> => send<T>(path, { method: 'DELETE' });

const withBody = (method: 'POST' | 'PUT' | 'PATCH', body: unknown): RequestOptions => ({
  method,
  headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
  body: body === undefined ? undefined : JSON.stringify(body),
});

/** POST a JSON body to the platform API. */
export const postJson = <T>(path: string, body?: unknown): Promise<T> =>
  send<T>(path, withBody('POST', body));

/** PUT a JSON body, for a setting that is written whole every time. */
export const sendPutJson = <T>(path: string, body: unknown): Promise<T> =>
  send<T>(path, withBody('PUT', body));

/** PATCH a JSON body, to change part of a resource. */
export const patchJson = <T>(path: string, body: unknown): Promise<T> =>
  send<T>(path, withBody('PATCH', body));

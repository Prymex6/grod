import { Check, Download, Loader2, Plus, Send, Trash2 } from 'lucide-react';
import { useEffect, useState, type ReactNode, type SyntheticEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import { ApiError } from '../../lib/api';
import {
  acknowledgeMessage,
  createQueue,
  deleteQueue,
  fetchQueues,
  publishMessage,
  purgeQueue,
  receiveMessages,
  type Queue,
  type QueueMessage,
} from './api';

const HTTP_CONFLICT = 409;
const NAME_MAX_LENGTH = 63;
const DEFAULT_VISIBILITY = 30;
const DEFAULT_ATTEMPTS = 5;

/** Queues the account keeps, with a way to send and take one message. */
export function QueuesPage(): ReactNode {
  const { t } = useTranslation();
  const [queues, setQueues] = useState<Queue[] | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  const [body, setBody] = useState('{"zadanie": "wyslij-maila"}');
  const [taken, setTaken] = useState<QueueMessage[]>([]);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    fetchQueues(controller.signal)
      .then((found) => {
        setQueues(found);
        setChosen((current) => current ?? found[0]?.name ?? null);
      })
      .catch(() => {
        if (!controller.signal.aborted) setError(t('queues.error.load'));
      });
    return () => {
      controller.abort();
    };
  }, [reloads, t]);

  const reload = (): void => {
    setReloads((count) => count + 1);
  };

  const add = (event: SyntheticEvent<HTMLFormElement>): void => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    createQueue({
      name: name.trim().toLowerCase(),
      visibilitySeconds: DEFAULT_VISIBILITY,
      maxAttempts: DEFAULT_ATTEMPTS,
    })
      .then((created) => {
        setName('');
        setCreating(false);
        setChosen(created.name);
        reload();
      })
      .catch((cause: unknown) => {
        const conflict = cause instanceof ApiError && cause.status === HTTP_CONFLICT;
        setError(t(conflict ? 'queues.error.taken' : 'queues.error.create'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const send = (): void => {
    if (chosen === null) return;
    let payload: unknown;
    try {
      payload = JSON.parse(body);
    } catch {
      setError(t('queues.error.body'));
      return;
    }
    setBusy(true);
    setError(null);
    publishMessage(chosen, payload)
      .then(reload)
      .catch(() => {
        setError(t('queues.error.publish'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const take = (): void => {
    if (chosen === null) return;
    setBusy(true);
    setError(null);
    receiveMessages(chosen, 1)
      .then((messages) => {
        setTaken(messages);
        reload();
      })
      .catch(() => {
        setError(t('queues.error.receive'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const finish = (message: QueueMessage): void => {
    if (chosen === null) return;
    setBusy(true);
    acknowledgeMessage(chosen, message.id, message.receipt)
      .then(() => {
        setTaken((current) => current.filter((item) => item.id !== message.id));
        reload();
      })
      .catch(() => {
        setError(t('queues.error.ack'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const act = (action: (queueName: string) => Promise<unknown>): void => {
    if (chosen === null) return;
    setBusy(true);
    action(chosen)
      .then(() => {
        setTaken([]);
        reload();
      })
      .catch(() => {
        setError(t('queues.error.create'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const current = queues?.find((item) => item.name === chosen) ?? null;

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight text-app">
            <Send className="h-6 w-6 text-accent" aria-hidden="true" />
            {t('queues.title')}
          </h1>
          <p className="mt-1 text-sm text-muted">{t('queues.subtitle')}</p>
        </div>
        <button
          type="button"
          onClick={() => {
            setCreating((open) => !open);
          }}
          className="flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          {t('queues.create')}
        </button>
      </div>

      {error !== null && <ErrorBanner message={error} />}

      {creating && (
        <form
          className="flex flex-wrap items-end gap-3 rounded-xl border border-app bg-surface p-4 shadow-app-sm"
          onSubmit={add}
        >
          <div className="min-w-48 flex-1">
            <label htmlFor="queueName" className="mb-1.5 block text-sm font-medium text-app">
              {t('queues.field.name')}
            </label>
            <input
              id="queueName"
              type="text"
              required
              maxLength={NAME_MAX_LENGTH}
              value={name}
              onChange={(event) => {
                setName(event.target.value);
              }}
              placeholder="zamowienia"
              className="w-full rounded-lg border border-app bg-app px-3 py-2 font-mono text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
            />
          </div>
          <button
            type="submit"
            disabled={busy}
            className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
          >
            {t('queues.create')}
          </button>
        </form>
      )}

      {queues === null && error === null && (
        <p className="flex items-center gap-2 text-sm text-muted">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          {t('queues.loading')}
        </p>
      )}

      {queues !== null && queues.length === 0 && (
        <p className="rounded-xl border border-app bg-surface px-4 py-6 text-center text-sm text-muted">
          {t('queues.empty')}
        </p>
      )}

      {queues !== null && queues.length > 0 && (
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
          <ul className="w-full shrink-0 space-y-1.5 lg:w-64">
            {queues.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => {
                    setChosen(item.name);
                    setTaken([]);
                  }}
                  aria-pressed={item.name === chosen}
                  className={`w-full rounded-lg border px-3 py-2 text-left ${
                    item.name === chosen
                      ? 'border-accent bg-accent-subtle'
                      : 'border-app bg-surface hover:bg-surface-raised'
                  }`}
                >
                  <p className="truncate font-mono text-sm text-app">{item.name}</p>
                  <p className="mt-0.5 truncate text-xs text-muted">
                    {t('queues.depth', {
                      waiting: item.waiting,
                      taken: item.taken,
                      dead: item.dead,
                    })}
                  </p>
                </button>
              </li>
            ))}
          </ul>

          {current !== null && (
            <div className="min-w-0 flex-1 space-y-3">
              <div>
                <label htmlFor="queueBody" className="mb-1.5 block text-sm font-medium text-app">
                  {t('queues.field.body')}
                </label>
                <textarea
                  id="queueBody"
                  rows={3}
                  value={body}
                  onChange={(event) => {
                    setBody(event.target.value);
                  }}
                  spellCheck={false}
                  className="w-full rounded-lg border border-app bg-app px-3 py-2 font-mono text-xs text-app focus:border-accent focus:outline-none"
                />
              </div>

              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={send}
                  disabled={busy}
                  className="flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
                >
                  <Send className="h-4 w-4" aria-hidden="true" />
                  {t('queues.publish')}
                </button>
                <button
                  type="button"
                  onClick={take}
                  disabled={busy}
                  className="flex items-center gap-2 rounded-lg border border-app bg-surface px-3 py-2 text-sm text-app hover:bg-surface-raised disabled:opacity-60"
                >
                  <Download className="h-4 w-4" aria-hidden="true" />
                  {t('queues.receive')}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    act(purgeQueue);
                  }}
                  disabled={busy}
                  className="rounded-lg border border-app bg-surface px-3 py-2 text-sm text-muted hover:bg-surface-raised hover:text-app disabled:opacity-60"
                >
                  {t('queues.purge')}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    act(deleteQueue);
                  }}
                  disabled={busy}
                  aria-label={t('queues.remove', { name: current.name })}
                  className="flex h-9 w-9 items-center justify-center rounded-md text-muted hover:bg-surface-raised hover:text-error disabled:opacity-60"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>

              {taken.length === 0 ? (
                <p className="rounded-xl border border-app bg-surface px-4 py-6 text-center text-sm text-muted">
                  {t('queues.nothingTaken')}
                </p>
              ) : (
                <ul className="space-y-2">
                  {taken.map((message) => (
                    <li
                      key={message.id}
                      className="space-y-2 rounded-xl border border-app bg-surface p-3 shadow-app-sm"
                    >
                      <p className="flex flex-wrap items-center gap-2 text-xs text-muted">
                        <span className="font-mono">{message.id.slice(0, 12)}</span>
                        <span>{t('queues.attempt', { count: message.attempts })}</span>
                        <button
                          type="button"
                          onClick={() => {
                            finish(message);
                          }}
                          disabled={busy}
                          className="ml-auto flex items-center gap-1.5 rounded-lg bg-accent px-2.5 py-1 text-xs font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
                        >
                          <Check className="h-3.5 w-3.5" aria-hidden="true" />
                          {t('queues.ack')}
                        </button>
                      </p>
                      <pre className="overflow-auto whitespace-pre-wrap break-words rounded-lg bg-app p-2 font-mono text-xs text-app">
                        {JSON.stringify(message.body, null, 2)}
                      </pre>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

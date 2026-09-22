import { getJson, postJson, sendDelete } from '../../lib/api';

export interface Queue {
  id: string;
  name: string;
  visibilitySeconds: number;
  maxAttempts: number;
  waiting: number;
  taken: number;
  dead: number;
  createdAt: string;
}

export interface QueueMessage {
  id: string;
  body: unknown;
  attempts: number;
  receipt: string;
}

const base = '/queues';
const path = (name: string): string => `${base}/${encodeURIComponent(name)}`;

export const fetchQueues = (signal?: AbortSignal): Promise<Queue[]> =>
  getJson<Queue[]>(base, signal);

export const createQueue = (values: {
  name: string;
  visibilitySeconds: number;
  maxAttempts: number;
}): Promise<Queue> => postJson<Queue>(base, values);

export const publishMessage = (name: string, message: unknown): Promise<{ id: string }> =>
  postJson<{ id: string }>(`${path(name)}/messages`, message);

export const receiveMessages = (name: string, limit = 1): Promise<QueueMessage[]> =>
  postJson<QueueMessage[]>(`${path(name)}/receive?limit=${String(limit)}`, {});

export const acknowledgeMessage = async (
  name: string,
  messageId: string,
  receipt: string,
): Promise<void> => {
  const address = `${path(name)}/messages/${encodeURIComponent(messageId)}/ack`;
  await postJson<undefined>(`${address}?receipt=${encodeURIComponent(receipt)}`, {});
};

export const fetchDeadMessages = (name: string, signal?: AbortSignal): Promise<QueueMessage[]> =>
  getJson<QueueMessage[]>(`${path(name)}/dead`, signal);

export const purgeQueue = async (name: string): Promise<void> => {
  await postJson<undefined>(`${path(name)}/purge`, {});
};

export const deleteQueue = (name: string): Promise<void> => sendDelete(path(name));

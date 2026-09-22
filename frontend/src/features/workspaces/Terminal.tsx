import { FitAddon } from '@xterm/addon-fit';
import { Terminal as XTerm } from '@xterm/xterm';
import '@xterm/xterm/css/xterm.css';
import { useEffect, useRef, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { terminalUrl } from './api';

const FONT_SIZE = 13;

interface TerminalProps {
  workspace: string;
  onClosed: () => void;
}

/** A shell inside the container, carried over a WebSocket. */
export function Terminal({ workspace, onClosed }: TerminalProps): ReactNode {
  const { t } = useTranslation();
  const holder = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = holder.current;
    if (element === null) return undefined;

    const terminal = new XTerm({
      fontSize: FONT_SIZE,
      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
      cursorBlink: true,
      convertEol: true,
    });
    const fit = new FitAddon();
    terminal.loadAddon(fit);
    terminal.open(element);
    fit.fit();

    const socket = new WebSocket(terminalUrl(workspace));
    socket.onmessage = (event: MessageEvent<string>) => {
      terminal.write(event.data);
    };
    socket.onclose = () => {
      terminal.writeln(`\r\n${t('workspaces.terminal.closed')}`);
      onClosed();
    };
    terminal.onData((typed) => {
      if (socket.readyState === WebSocket.OPEN) socket.send(typed);
    });

    const resize = (): void => {
      fit.fit();
    };
    window.addEventListener('resize', resize);

    return () => {
      window.removeEventListener('resize', resize);
      socket.close();
      terminal.dispose();
    };
  }, [workspace, onClosed, t]);

  return (
    <div
      ref={holder}
      aria-label={t('workspaces.terminal.label', { name: workspace })}
      className="h-96 overflow-hidden rounded-xl border border-app bg-black p-2"
    />
  );
}

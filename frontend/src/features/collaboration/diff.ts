/** Turning the patch git produces into something the diff view can render. */

export type LineKind = 'context' | 'added' | 'removed';

export interface DiffLine {
  kind: LineKind;
  oldNumber: number | null;
  newNumber: number | null;
  content: string;
}

export interface DiffHunk {
  header: string;
  lines: DiffLine[];
}

const HUNK_PATTERN = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/;
const SIGN_LENGTH = 1;

const startOf = (header: string): { oldNumber: number; newNumber: number } | null => {
  const found = HUNK_PATTERN.exec(header);
  if (found === null) return null;
  return { oldNumber: Number(found[1]), newNumber: Number(found[2]) };
};

/**
 * Split a unified patch into hunks.
 *
 * Everything before the first `@@` is the file header git writes, which the
 * view already shows as the path, so it is dropped.
 */
export function parsePatch(patch: string): DiffHunk[] {
  const hunks: DiffHunk[] = [];
  let current: DiffHunk | null = null;
  let oldNumber = 0;
  let newNumber = 0;

  for (const line of patch.split('\n')) {
    const start = startOf(line);
    if (start !== null) {
      current = { header: line, lines: [] };
      hunks.push(current);
      oldNumber = start.oldNumber;
      newNumber = start.newNumber;
      continue;
    }
    if (current === null) continue;

    const content = line.slice(SIGN_LENGTH);
    if (line.startsWith('+')) {
      current.lines.push({ kind: 'added', oldNumber: null, newNumber, content });
      newNumber += 1;
    } else if (line.startsWith('-')) {
      current.lines.push({ kind: 'removed', oldNumber, newNumber: null, content });
      oldNumber += 1;
    } else if (line.startsWith(' ')) {
      current.lines.push({ kind: 'context', oldNumber, newNumber, content });
      oldNumber += 1;
      newNumber += 1;
    }
    // "\ No newline at end of file" and empty trailing lines carry no change.
  }

  return hunks;
}

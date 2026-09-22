const BYTES_IN_UNIT = 1024;
const UNITS = ['B', 'kB', 'MB', 'GB', 'TB'] as const;

/** Turn a number of bytes into something short a person can read. */
export function readableSize(bytes: number): string {
  let size = bytes;
  let unit = 0;
  while (size >= BYTES_IN_UNIT && unit < UNITS.length - 1) {
    size /= BYTES_IN_UNIT;
    unit += 1;
  }
  return `${unit === 0 ? size.toString() : size.toFixed(1)} ${UNITS[unit] ?? 'B'}`;
}

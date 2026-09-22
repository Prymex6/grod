import hljs from 'highlight.js/lib/core';
import bash from 'highlight.js/lib/languages/bash';
import css from 'highlight.js/lib/languages/css';
import go from 'highlight.js/lib/languages/go';
import ini from 'highlight.js/lib/languages/ini';
import java from 'highlight.js/lib/languages/java';
import javascript from 'highlight.js/lib/languages/javascript';
import json from 'highlight.js/lib/languages/json';
import markdown from 'highlight.js/lib/languages/markdown';
import php from 'highlight.js/lib/languages/php';
import python from 'highlight.js/lib/languages/python';
import rust from 'highlight.js/lib/languages/rust';
import sql from 'highlight.js/lib/languages/sql';
import typescript from 'highlight.js/lib/languages/typescript';
import xml from 'highlight.js/lib/languages/xml';
import yaml from 'highlight.js/lib/languages/yaml';

/** Only the languages the console can colour are bundled. */
const LANGUAGES = {
  bash,
  css,
  go,
  ini,
  java,
  javascript,
  json,
  markdown,
  php,
  python,
  rust,
  sql,
  typescript,
  xml,
  yaml,
} as const;

for (const [name, language] of Object.entries(LANGUAGES)) {
  hljs.registerLanguage(name, language);
}

const BY_EXTENSION: Record<string, keyof typeof LANGUAGES> = {
  bash: 'bash',
  css: 'css',
  go: 'go',
  htm: 'xml',
  html: 'xml',
  ini: 'ini',
  java: 'java',
  js: 'javascript',
  json: 'json',
  jsx: 'javascript',
  md: 'markdown',
  mjs: 'javascript',
  php: 'php',
  py: 'python',
  rs: 'rust',
  sh: 'bash',
  sql: 'sql',
  svg: 'xml',
  toml: 'ini',
  ts: 'typescript',
  tsx: 'typescript',
  xml: 'xml',
  yaml: 'yaml',
  yml: 'yaml',
};

/** Language of a file, guessed from its name; null when we cannot colour it. */
export const languageOf = (path: string): keyof typeof LANGUAGES | null => {
  const extension = path.split('.').pop()?.toLowerCase() ?? '';
  return BY_EXTENSION[extension] ?? null;
};

/** Colour one file and return HTML, or null when the language is unknown. */
export const highlight = (path: string, code: string): string | null => {
  const language = languageOf(path);
  if (language === null) return null;
  try {
    return hljs.highlight(code, { language }).value;
  } catch {
    // A file that trips the grammar is still worth showing, just plain.
    return null;
  }
};

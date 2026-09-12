import { describe, expect, it } from 'vitest';
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import en from '@/i18n/locales/en.json';
import ko from '@/i18n/locales/ko.json';
import i18n from '@/i18n';
import { humanizeError, toApiError } from './errors';

type Tree = { [k: string]: string | Tree };

function flatten(tree: Tree, prefix = ''): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(tree)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (typeof v === 'string') out[key] = v;
    else Object.assign(out, flatten(v, key));
  }
  return out;
}

const flatEn = flatten(en as Tree);
const flatKo = flatten(ko as Tree);
const placeholders = (s: string) => [...s.matchAll(/\{\{\s*([\w.]+)\s*\}\}/g)].map((m) => m[1]).sort();

describe('locale parity', () => {
  it('has the same keys in en and ko', () => {
    expect(Object.keys(flatKo).sort()).toEqual(Object.keys(flatEn).sort());
  });

  it('uses the same {{placeholders}} in both languages', () => {
    const mismatched = Object.keys(flatEn).filter(
      (k) => placeholders(flatEn[k]).join() !== placeholders(flatKo[k] ?? '').join(),
    );
    expect(mismatched).toEqual([]);
  });

  it('maps every error code the console can branch on to a message in both languages', () => {
    const codes = Object.keys((en as Tree).error as Tree);
    for (const c of codes) expect((ko as Tree).error, `ko error.${c}`).toHaveProperty(c);
  });
});

// The backend is the source of every `error.code`; a code it can raise that the console cannot
// translate falls through to the server's English message, which a Korean user should never see.
// The check reads the backend sources when the monorepo is present, and is skipped elsewhere.
const backendDir = path.resolve(__dirname, '../../../backend/app');

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = path.join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (p.endsWith('.py')) out.push(p);
  }
  return out;
}

describe.skipIf(!existsSync(backendDir))('backend error codes', () => {
  it('every DomainError code the backend can raise has a translation', () => {
    const codes = new Set<string>();
    for (const file of walk(backendDir)) {
      const src = readFileSync(file, 'utf8');
      for (const m of src.matchAll(/code(?:, http)? = "([a-z_]+)"/g)) codes.add(m[1]);
      // Framework-raised statuses are mapped in errors.py's _HTTP_STATUS_CODES table.
      for (const m of src.matchAll(/\d{3}: "([a-z_]+)"/g)) codes.add(m[1]);
    }
    expect(codes.size).toBeGreaterThan(20);
    const errorKeys = (en as Tree).error as Tree;
    const missing = [...codes].filter((c) => !(c in errorKeys)).sort();
    expect(missing).toEqual([]);
  });
});

describe('humanizeError', () => {
  it('translates a known code and falls back to the server message otherwise', async () => {
    await i18n.changeLanguage('en');
    expect(humanizeError(toApiError({ error: { code: 'node_busy', message: 'x' } }, 409)))
      .toBe(flatEn['error.node_busy']);
    expect(humanizeError(toApiError({ error: { code: 'brand_new_code', message: 'server said so' } }, 409)))
      .toBe('server said so');
  });
});

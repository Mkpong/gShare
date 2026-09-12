import { describe, expect, it } from 'vitest';
import { credentialsCsv, parseCsv } from './UsersBulkImport';

describe('parseCsv', () => {
  it('parses email,name rows and lowercases emails', () => {
    const rows = parseCsv('A@U.AC.KR,Kim\nb@u.ac.kr,Lee');
    expect(rows).toHaveLength(2);
    expect(rows[0]).toMatchObject({ email: 'a@u.ac.kr', name: 'Kim', problem: null });
  });

  it('skips a header row', () => {
    const rows = parseCsv('email,name\na@u.ac.kr,Kim');
    expect(rows).toHaveLength(1);
    expect(rows[0].email).toBe('a@u.ac.kr');
  });

  it('flags invalid emails, in-file duplicates, and missing names', () => {
    const rows = parseCsv('a@u.ac.kr,Kim\nnot-an-email,X\na@u.ac.kr,Kim2\nc@u.ac.kr,');
    expect(rows.map((r) => r.problem)).toEqual([null, 'invalid_email', 'duplicate', 'missing_name']);
  });

  it('handles quoted names containing commas', () => {
    const rows = parseCsv('a@u.ac.kr,"Kim, Cheolsu"');
    expect(rows[0]).toMatchObject({ name: 'Kim, Cheolsu', problem: null });
  });

  it('flags a first data row with a bad address instead of dropping it as a header', () => {
    const rows = parseCsv('kim-at-u.ac.kr,Kim\nb@u.ac.kr,Lee');
    expect(rows.map((r) => [r.line, r.problem])).toEqual([[1, 'invalid_email'], [2, null]]);
  });

  it('recognises common header spellings', () => {
    for (const header of ['email,name', 'Email,Name', 'E-Mail,Full name', 'email address,name']) {
      expect(parseCsv(`${header}\na@u.ac.kr,Kim`).map((r) => r.email), header).toEqual(['a@u.ac.kr']);
    }
  });

  it('strips a UTF-8 BOM, skips blank lines and keeps file line numbers', () => {
    const rows = parseCsv('\uFEFFemail,name\r\na@u.ac.kr,Kim\r\n\r\n   \r\nb@u.ac.kr,Lee\r\n');
    expect(rows.map((r) => [r.line, r.email, r.problem])).toEqual([
      [2, 'a@u.ac.kr', null],
      [5, 'b@u.ac.kr', null],
    ]);
  });

  it('treats the same address in different case as a duplicate', () => {
    const rows = parseCsv('A@u.ac.kr,Kim\na@U.AC.KR,Kim');
    expect(rows[1].problem).toBe('duplicate');
  });
});

describe('credentialsCsv', () => {
  it('emits only created rows with their one-time passwords', () => {
    const csv = credentialsCsv([
      { row: 0, email: 'a@u.ac.kr', status: 'created', initial_password: 'pw-1' },
      { row: 1, email: 'b@u.ac.kr', status: 'exists' },
    ]);
    expect(csv).toBe('email,initial_password\na@u.ac.kr,pw-1');
  });
});

// Standalone synthetic framing probe for the shipped worker. No npm or Rust.
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const layoutKey = 'PROTEUS_MERMAID_PROOF_LAYOUT';
if (process.env[layoutKey] !== undefined) {
  // Only in the child: feed the worker's real stdin loop deterministic Buffers.
  const sizes = JSON.parse(process.env[layoutKey]);
  const bytes = readFileSync(0);
  assert.ok(sizes.every(size => Number.isSafeInteger(size) && size >= 0));
  assert.equal(sizes.reduce((sum, size) => sum + size, 0), bytes.length);
  Object.defineProperty(process.stdin, Symbol.asyncIterator, {
    async *value() {
      let start = 0;
      for (const size of sizes) {
        yield bytes.subarray(start, start + size);
        start += size;
      }
    },
  });
} else {
  const paths = process.argv.slice(2).map(path => resolve(path));
  assert.equal(paths.length, 2, 'pass paths to stock and candidate worker.mjs');
  const preload = fileURLToPath(import.meta.url);
  const sha = bytes => createHash('sha256').update(bytes).digest('hex');
  const theme = {
    foreground: '#e8e8ed', background: '#11131a', muted: '#8b8d98',
    border: '#424454', accent: '#8aabff', danger: '#ff7e88',
    surface: '#242633', surface_alt: '#303344',
    font_family: 'Inter, sans-serif', font_family_mono: 'monospace',
  };
  const flowchart = 'flowchart LR\n' + Array.from({ length: 32 }, (_, i) =>
    ` N${i}["Пример ${i} карты процесса и проверка результата"]${i ? `\n N${i - 1} --> N${i}` : ''}`,
  ).join('\n');
  const body = Buffer.from(JSON.stringify({ source: flowchart, theme }));
  assert.ok(body.length >= 2 * 1024 && body.length <= 8 * 1024);
  const simple = Buffer.from(JSON.stringify({ source: 'sequenceDiagram\n A->>B: Готово', theme }));
  const lf = Buffer.from('\n');
  const crlf = Buffer.from('\r\n');
  const frame = Buffer.concat([body, lf]);
  const brief = Buffer.concat([simple, lf]);
  const middle = body.indexOf(Buffer.from('П')) + 1;
  assert.ok(middle > 1 && body[middle] >= 128 && body[middle] < 192);
  const limit = 512 * 1024;
  const pad = length => Buffer.concat([simple, Buffer.alloc(length - simple.length, 32)]);
  const complete = (name, chunks, ok, code = 0) => ({ name, chunks, ok, code });
  const cases = [
    complete('ordinary-complete', [frame], [true]),
    complete('coalesced-blank-malformed-and-crlf', [Buffer.concat([brief, lf, Buffer.from('{\n'), body, crlf])], [true, false, false, true]),
    complete('split-utf8-followed-by-complete', [frame.subarray(0, middle), Buffer.concat([frame.subarray(middle), brief])], [true, true]),
    complete('empty-chunk-and-split-final-lf', [body, Buffer.alloc(0), lf], [true]),
    complete('exact-cap-lf', [Buffer.concat([pad(limit), lf])], [true]),
    complete('exact-cap-crlf', [Buffer.concat([pad(limit - 1), crlf])], [true]),
    complete('exact-cap-fragmented-before-lf', [pad(limit), lf], [true]),
    complete('over-cap-cr-counts-and-stops', [Buffer.concat([brief, pad(limit), crlf, frame])], [true], 1),
    complete('over-cap-fragmented-tail', [pad(limit), Buffer.from(' ')], [], 1),
    complete('unterminated-after-one', [Buffer.concat([brief, body])], [true], 1),
    complete('empty-stream', [], []),
  ];

  for (const scenario of cases) {
    const sizes = scenario.chunks.map(bytes => bytes.length);
    const input = Buffer.concat(scenario.chunks);
    const results = paths.map(path => spawnSync(process.execPath,
      ['--max-old-space-size=96', '--no-addons', '--import', preload, path], {
        cwd: dirname(path), input, timeout: 5000, maxBuffer: 2 * 1024 * 1024,
        env: { LANG: 'C', TZ: 'UTC', [layoutKey]: JSON.stringify(sizes) },
      },
    ));
    for (const result of results) {
      assert.ifError(result.error);
      assert.equal(result.signal, null, scenario.name);
      assert.equal(result.status, scenario.code, scenario.name);
      assert.equal(result.stderr.length, 0, scenario.name);
      const output = result.stdout.toString('utf8');
      assert.ok(output === '' || output.endsWith('\n'), scenario.name);
      const replies = output ? output.slice(0, -1).split('\n').map(line => JSON.parse(line)) : [];
      assert.deepEqual(replies.map(reply => reply.ok), scenario.ok, scenario.name);
      for (const reply of replies) {
        if (reply.ok) assert.ok(reply.svg.startsWith('<svg') && reply.width > 0 && reply.height > 0, scenario.name);
        else assert.ok(typeof reply.error === 'string' && reply.error.length > 0, scenario.name);
      }
    }
    assert.deepEqual(results[0].stdout, results[1].stdout, scenario.name);
    assert.deepEqual(results[0].stderr, results[1].stderr, scenario.name);
    console.log(JSON.stringify({ case: scenario.name, input_bytes: input.length, chunk_sizes: sizes,
      replies: scenario.ok, exit: scenario.code, stdout_sha256: sha(results[0].stdout), stderr_bytes: 0 }));
  }
}

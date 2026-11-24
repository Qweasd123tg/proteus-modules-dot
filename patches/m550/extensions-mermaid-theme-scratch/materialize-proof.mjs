import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const [root, output] = process.argv.slice(2);
const path = file => pathToFileURL(resolve(root, file)).href;
const { materializeSvg } = await import(path('svg-theme.mjs'));
const { render } = await import(path('vendor/pele/pele.mjs'));

const theme = {
  foreground: '#e8e8ed', background: '#11131a', muted: '#8b8d98',
  border: '#424454', accent: '#8aabff', danger: '#ff7e88',
  surface: '#242633', surface_alt: '#303344',
  font_family: "Inter, 'sans-serif'", font_family_mono: 'monospace',
};
const params = {idPrefix: 'm550-probe', maxWidth:640, responsive: false};
const flows = [
  ['branch', 'flowchart LR\n A["Привет 🦀"] --> B{Вперёд?}\n A-->C[Возврат]'],
  ['sequence', 'sequenceDiagram\n Аня->>Борис: Привет\n Борис-->>Аня: Готово'],
  ['gantt', 'gantt\n dateFormat X\n axisFormat %Y\n A :1700000000,1700003600'],
  ['pie', 'pie\n "Большой":999\n "Small":1'],
  ['larger', 'flowchart TB\n' + Array.from({length:40}, (_, i) => `N${i}[Я🦀] --> N${i+1}[Test]`).join('\n')],
];
const expectation = new Map([
  ['branch',"Привет"],
  ['sequence',"Готово"],
  ['gantt',"2023"],
  ['pie','pele-slice'],
  ['larger','Test'],
]);
const raws = flows.map(([name, source]) => [name, render(source, params).svg]);
raws.push(['style-frontier','<svg><!--test--><g style="--local:#123456">'
  + '<rect rx="99" ry="88" font-size="123" fill="currentColor"'
  + ' style="rx:1;rx:2;stroke:var(--local);ry:var(--unmatched,4);font:italic 9px Test;color:#abcdef"/>'
  + '<path style="cursor:help" stroke="var(--local)"/>'
  + '<path style="--alias:var(--local)" fill="var(--alias)"/>'
  + '<text x="1" style="">link &amp; var(--not-css)</text>'
  + '</g><path fill="currentColor"/><g style="font:italic"><text>Ж</text></g></svg>']);

const OriginalMap = globalThis.Map;
let count = 0;
const CountedMap = new Proxy(OriginalMap, {
  construct(target, args) {
    ++count;
    return Reflect.construct(target, args);
  },
});
const rows=[];
for (const [name, svg] of raws) {
  count = 0;
  globalThis.Map = CountedMap;
  let themed;
  try {
    // Count only constructor calls by the actual materializer. Vendor rendering
    // was outside the meter; result serialization is outside the meter.
    themed = materializeSvg(svg, theme);
  } finally {
    globalThis.Map = OriginalMap;
  }
  console.log(name, count, Buffer.byteLength(themed));
  if (name === 'style-frontier') {
    assert.match(themed, /<rect fill="#abcdef" style="stroke:#123456;color:#abcdef" rx="2" ry="4" font-size="9px"\/>/);
    assert.match(themed, /<path style="cursor:help" stroke="#123456"\/>/);
    assert.match(themed, /<path fill="#123456"\/>/);
    assert.match(themed, /<text x="1">link &amp; var\(--not-css\)<\/text>/);
    assert.match(themed, /<\/g><path fill="#e8e8ed"\/>/);
  } else {
    assert.ok(themed.includes(expectation.get(name)));
    assert.doesNotMatch(themed, /var\(|currentColor/);
  }
  rows.push(themed);
}
for (const [svg, pattern] of [
  ['<svg><rect fill="var(--bad)"/></svg>', /unresolved SVG variable/],
  ['<svg><g style="--x:var(--x);rx:var(--x)"/></svg>', /cyclic SVG variable/],
  ['<svg><g style="color:var(--bad);opacity:var(--also-bad)"/></svg>', /--bad/],
]) {
  assert.throws(() => materializeSvg(svg, theme), pattern);
  try { materializeSvg(svg, theme); } catch (error) { rows.push(error.message); }
}
const payload = JSON.stringify(rows);
writeFileSync(output,payload);
console.log('materialized', Buffer.byteLength(payload), createHash('sha256').update(payload).digest('hex'));

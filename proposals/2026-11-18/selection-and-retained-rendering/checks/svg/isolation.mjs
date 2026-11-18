import { resolve } from 'node:path'; import { pathToFileURL } from 'node:url'; import assert from 'node:assert/strict';
const {materializeSvg:render}=await import(pathToFileURL(resolve(process.argv[2])));
const theme={foreground:'#111111',background:'#ffffff',muted:'#777777',border:'#444444',accent:'#2233ee',danger:'#cc1122',surface:'#eeeeee',surface_alt:'#dddddd'};
const s='<svg style="--paint:var(--pele-fg)"><g style="--paint:var(--pele-accent)"><rect fill="var(--paint)"/></g><circle fill="var(--paint)"/></svg>';
assert.equal(render(s,theme),'<svg><g><rect fill="#2233ee"/></g><circle fill="#111111"/></svg>');
console.log('local color does not leak to a sibling');

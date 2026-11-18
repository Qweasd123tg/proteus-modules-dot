import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
import { writeFileSync } from 'node:fs';
import assert from 'node:assert/strict';
const { NativeResponseCollector } = await import(pathToFileURL(resolve(process.argv[2],'model/opencode-provider/response.mjs')));
const chunks=['{"answer":',' не JSON ','\n```rust\n','x()\n```'];
const collector=new NativeResponseCollector('00000000-0000-4000-8000-000000000042');
const modelEvents=[];
for(const event of [{type:'text-start',id:'text'},...chunks.map(text=>({type:'text-delta',id:'text',text})),{type:'text-end',id:'text',text:chunks.join('')},{type:'finish',reason:{normalized:'stop'}}]) {
    modelEvents.push(...collector.push(event));
}
const response=collector.finish();
const done=modelEvents.find(e=>e.MessageCompleted);
assert.equal(done.MessageCompleted.message,response.messages[0]);
assert.equal(response.messages[0].parts[0].payload.Text.text,chunks.join(''));
modelEvents.push({Response:{response}});
writeFileSync(process.argv[3],JSON.stringify(modelEvents)+'\n');
console.log('Pinned opencode NativeResponseCollector events:', modelEvents.map(e=>Object.keys(e)[0]).join(', '));

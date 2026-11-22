import { test } from 'node:test';
import assert from 'node:assert/strict';
import { NativeResponseCollector } from './response.mjs';

const MESSAGE = 'r135-native-response-fixture';
const event = (type, id, fields = {}) => ({ type, id, ...fields });
const finish = (normalized = 'stop') => ({ type: 'finish', reason: { normalized } });
const text = value => ({ TextDelta: { message_id: MESSAGE, phase: null, text: value } });
const reasoning = value => ({ ReasoningDelta: { message_id: MESSAGE, text: value } });
const malformed = { code: 'OPENCODE_MALFORMED_OUTPUT' };

test('first emitted visibility is independent by kind, block, and collector', () => {
    const c = new NativeResponseCollector(MESSAGE);
    assert.deepEqual(c.push(event('text-start', 'same:🪐')), []);
    assert.deepEqual(c.push(event('reasoning-start', 'same:🪐')), []);
    assert.deepEqual(c.push(event('text-delta', 'same:🪐', { text: '' })), []);
    assert.deepEqual(c.push(event('reasoning-delta', 'same:🪐', { text: 'думаю' })), [reasoning('думаю')]);
    assert.deepEqual(c.push(event('text-delta', 'same:🪐', { text: '答' })), [text('答')]);
    assert.deepEqual(c.push(event('text-delta', 'next:🌎', { text: '\nновый' })), [text('\n\nновый')]);
    assert.deepEqual(c.push(event('reasoning-end', 'next:🌎', { text: '🪐' })), [reasoning('\n🪐')]);
    assert.deepEqual(c.push(event('text-delta', 'same:🪐', { text: '案' })), [text('案')]);
    assert.deepEqual(c.push(event('reasoning-delta', 'same:🪐', { text: ' ещё' })), [reasoning(' ещё')]);
    assert.deepEqual(c.push(event('text-end', 'next:🌎')), []);
    assert.deepEqual(c.push(event('reasoning-end', 'same:🪐')), []);
    assert.deepEqual(c.push(finish()).map(Object.keys), [['MessageCompleted'], ['Done']]);
    assert.deepEqual(c.finish().messages[0].parts.map(part => part.payload), [
        { Text: { text: '答案' } }, { Reasoning: { text: 'думаю ещё', signature: null } },
        { Text: { text: '\nновый' } }, { Reasoning: { text: '🪐', signature: null } },
    ]);

    const next = new NativeResponseCollector(MESSAGE);
    assert.deepEqual(next.push(event('text-delta', 'next:🌎', { text: 'новый' })), [text('новый')]);
    assert.deepEqual(next.push(event('reasoning-end', 'next:🌎', { text: '🪐' })), [reasoning('🪐')]);
});

test('metadata-only blocks and zero-suffix endings never consume first visibility', () => {
    const c = new NativeResponseCollector(MESSAGE);
    const providerMetadata = { synthetic: { signature: 'opaque-signed-only' } };
    assert.deepEqual(c.push(event('reasoning-start', 'hidden', { providerMetadata })), []);
    assert.deepEqual(c.push(event('reasoning-end', 'hidden', { text: '' })), []);
    assert.deepEqual(c.push(event('text-end', 'blank')), []);
    assert.deepEqual(c.push(event('reasoning-end', 'first', { text: 'é' })), [reasoning('é')]);
    assert.deepEqual(c.push(event('text-end', 'first', { text: 'π' })), [text('π')]);
    assert.deepEqual(c.push(event('reasoning-end', 'second', { text: '字' })), [reasoning('\n字')]);
    assert.deepEqual(c.push(event('text-end', 'second', { text: '🐈' })), [text('\n🐈')]);
    c.push(finish());
    const m = c.finish().messages[0];
    assert.deepEqual(m.metadata.opencode_native.parts, [
        { type: 'reasoning', providerMetadata }, { type: 'text' }, { type: 'reasoning' },
        { type: 'text' }, { type: 'reasoning' }, { type: 'text' },
    ]);
    assert.deepEqual(m.parts[0].payload, { Reasoning: { text: '', signature: null } });
    const ids = m.parts.map(part => part.part_id);
    assert.ok(ids.every(id => /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(id)));
    assert.equal(new Set(ids).size, ids.length);

    const spaces = new NativeResponseCollector(MESSAGE);
    assert.deepEqual(spaces.push(event('text-end', 'space', { text: ' ' })), [text(' ')]);
    assert.deepEqual(spaces.push(event('text-end', 'next', { text: 'x' })), [text('\nx')]);
});

test('end corrections and step boundaries preserve existing delta and completion rules', () => {
    const c = new NativeResponseCollector(MESSAGE);
    assert.deepEqual(c.push(event('text-delta', 'draft', { text: 'чер' })), [text('чер')]);
    assert.deepEqual(c.push(event('text-end', 'draft', { text: 'готово' })), []);
    assert.deepEqual(c.push({ type: 'step-finish', reason: { normalized: 'stop' }, usage: {
        inputTokens: 3, outputTokens: 5,
    } }), []);
    assert.deepEqual(c.push({ type: 'step-start' }), []);
    assert.deepEqual(c.push(event('text-delta', 'more', { text: '🧪' })), [text('\n🧪')]);
    assert.deepEqual(c.push(event('text-end', 'more', { text: '🧪!' })), [text('!')]);
    assert.deepEqual(c.push(event('reasoning-end', 'draft', { text: 'заключение' })), [reasoning('заключение')]);
    const terminal = c.push(finish());
    const result = c.finish(), message = result.messages[0];
    assert.equal(message.id, MESSAGE);
    assert.equal(result.finish_reason, 'Stop');
    assert.equal(result.end_turn, true);
    assert.equal(terminal[0].Usage.usage, result.usage);
    assert.equal(terminal[1].MessageCompleted.message, message);
    assert.deepEqual(terminal[2], { Done: { finish_reason: 'Stop' } });
    assert.deepEqual(message.parts.map(part => part.payload), [
        { Text: { text: 'готово' } }, { Text: { text: '🧪!' } },
        { Reasoning: { text: 'заключение', signature: null } },
    ]);
    assert.throws(() => c.push(event('text-delta', 'late', { text: 'late' })), malformed);
    assert.throws(() => c.push(finish()), malformed);
    assert.equal(c.finish(), result);
});

test('existing type, ID and lifecycle errors remain sticky', () => {
    const bad = [
        () => [event('text-delta', 'a', { text: 7 })],
        () => [event('reasoning-end', 'a', { text: {} })],
        () => [event('reasoning-delta', '', { text: 'invalid' })],
        () => [event('text-start', 5)],
        () => [event('text-start', 'dupe'), event('text-start', 'dupe')],
        () => [event('reasoning-end', 'done'), event('reasoning-delta', 'done', { text: 'late' })],
        () => [event('not-a-native-event', 'out')],
    ];
    for (const make of bad) {
        const c = new NativeResponseCollector(MESSAGE);
        const frames = make();
        for (const frame of frames.slice(0, -1)) assert.deepEqual(c.push(frame), []);
        let first;
        assert.throws(() => c.push(frames.at(-1)), error => {
            first = error;
            return error.code === malformed.code;
        });
        assert.throws(() => c.push(finish()), error => error === first);
        assert.throws(() => c.finish(), error => error === first);
    }
    assert.throws(() => new NativeResponseCollector(MESSAGE).finish(), { code: 'OPENCODE_PREMATURE_EOF' });
});

test('tool JSON validation stays separate and tool traffic marks no visible kind', () => {
    const c = new NativeResponseCollector(MESSAGE);
    const callId = 'same-tool:text';
    assert.deepEqual(c.push(event('tool-input-start', callId, { name: 'inert' })), [
        { ToolCallDelta: { call_id: callId, name: 'inert', args_delta: '' } },
    ]);
    const call = c.push(event('tool-call', callId, { name: 'inert', input: { strings: ['á', '🪐'] } }));
    assert.equal(call[0].ToolCallFinished.call.name, 'inert');
    assert.deepEqual(c.push(event('text-end', callId, { text: 't' })), [text('t')]);
    assert.deepEqual(c.push(event('reasoning-end', callId, { text: 'r' })), [reasoning('r')]);
    c.push(finish('tool-calls'));
    assert.equal(c.finish().end_turn, false);
    assert.deepEqual(c.finish().tool_calls.map(({ id, args }) => [id, args]), [[callId, { strings: ['á', '🪐'] }]]);
    const invalid = new NativeResponseCollector(MESSAGE), cyclic = {};
    cyclic.self = cyclic;
    assert.throws(() => invalid.push(event('tool-call', 'cyclic', { name: 'inert', input: cyclic })), malformed);
});

# Modules JS: retire an unsent callback when encoding fails

When a host callback could not be converted into JSON, the adapter rejected the call but kept its waiter and abort listener. Clean up that unsent callback only when JSON encoding throws. Keep the original error, sequence and existing cancellation behavior. The stream write is outside the error handler, so backpressure and write failures are unchanged. Successful callbacks do not allocate an additional cleanup closure.

Exact owner and Desktop-pinned Modules preimage, also exact in M480. In an isolated Node run using the real `runComponent` with in-memory streams, five failed encodes in one invocation left five abort listeners in stock and zero with the patch. The next callback succeeded. Startup, normal results and rejections, cancellation, and write-failure behavior matched the stock fixture. This measures retained listeners, not whole-process memory. No production deployment.

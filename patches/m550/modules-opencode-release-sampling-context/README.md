# OpenCode: release sampling-only history after the model reply

After successful model sampling the request no longer needs the temporary history array containing the added context message. Restore its canonical history reference before awaiting the accepted-step event and checkpoint. The same request and contents are still sent during sampling and retries, and the overflow route is unchanged. The production host bridge serializes request data synchronously; the restored reference is not sent to Core.

The exact local workflow ran with an inert SDK and host. Fourteen paired cases matched. In separate Node processes, after 8,192 synthetic messages reached a deliberately held history checkpoint, the temporary array and inserted message were collectible in the new arm through three observation rounds. In the old arm both remained reachable until the checkpoint completed. Canonical history stayed live and paired outputs matched. This is a reachability result, not an application PSS or latency benchmark.

Exact source bases and the equivalent scoped variant following #739 and #747 are fingerprinted in the receipt.

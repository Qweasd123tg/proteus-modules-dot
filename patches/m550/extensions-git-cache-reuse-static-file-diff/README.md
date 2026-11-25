# Git-cache benchmark: reuse the encoded synthetic file diff

The owned fixture returns the same file-diff object for every request to that endpoint. Encode it once when the fixture starts. Commit previews remain distinct and are still encoded per request. Response bodies, lengths, request counts, and routing remain unchanged.

For the documented 48-request example, the file-diff payload is encoded once instead of 48 times. It is still sent separately and in full for each request. The fixture now retains one fixed 393,383-byte response at its documented default, and it encodes that response even in runs that never request it. The fixture is outside the measured product process tree. Keep this fixture version identical across comparison arms; there is no product speed, memory, or network traffic claim.

Apply `source.patch` to the pinned Extensions basis in `receipt.json`; no alternate is needed.

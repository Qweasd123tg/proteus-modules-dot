# Seed small external journal object reads from the open file size

The JSONL decoder asks the existing bounded read helper for a capacity
hint when the stored object is at most 256 KiB. Its content can be a small
manifest even when the logical payload is large. Size admission, regular
file checks, the read through EOF, typed decode and fingerprints are unchanged.

**Choose one**, exact Modules `f4bd470def2255f3459b7a42b50e96d0faa0bbf1`:
- Stock: `git apply --check source.patch && git apply source.patch`.
- After the exact standalone Dot #901 tree `04a33f14748cb08d236022395a95f4f7dfd97fa2`:
  `git apply --check after-dot901.patch && git apply after-dot901.patch`.
These are alternatives for one change, not cumulative.

On a 50,000-message synthetic JSONL write, reading the actual 54,774-byte
manifest saved 11 allocation requests and
76,266 cumulative requested bytes. Return bytes match;
the decoded typed record has the same digest. Empty and above-hint
controls remain unchanged. 118 storage tests
passed each on stock, standalone and after #901, with one existing ignored test.
Native SDK-worker smoke also matched the checked page for the 64-message
display and 50,000-message canonical fallback, with journal/blobs unchanged.
No total startup or process PSS estimate.

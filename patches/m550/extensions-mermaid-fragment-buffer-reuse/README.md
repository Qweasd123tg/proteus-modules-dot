# Mermaid worker: avoid repeatedly copying a fragmented request prefix

Keep a private, bounded scratch buffer while waiting for a line. Append into available capacity and grow only when necessary. Decode exactly the bytes received, retain existing request limits and EOF checks, and drop the buffer after each reply. Whole lines continue to bypass the buffer.

The exact local worker and bundled renderer matched on 16 benign paired wire cases across both source scopes, plus six selected stock tests per arm. On a 39,689-byte JSON line split into roughly 1 KiB chunks, explicit buffer copies fell from 798,473 to 104,201 bytes with byte-identical replies. A single complete line still copies nothing in the accumulator.

These counts describe the controlled input only, not real pipe chunk frequency, render time, peak memory or RSS.

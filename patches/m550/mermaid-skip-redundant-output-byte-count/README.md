# Skip an unnecessary UTF-8 length scan for small SVG strings

A primitive string with at most floor(1 MiB / 3) UTF-16 code units
cannot exceed 1 MiB in UTF-8. Return it directly; larger strings and
nonstring inputs retain the exact Node byte-length check. The existing
byte limit and wire behavior are unchanged.

Exact Extensions e13f1fc9b157177945049b260adbab4834f6d539.
13 worker tests and 29 direct boundary/type cases passed in each arm.
Six actual Node worker replies matched byte-for-byte, including with
the packaged worker flags; all four valid SVGs met the shortcut bound.
Tiny and maximum-bound strings skipped the Node byte-length call;
the exact fallback still ran on both above-bound probes.

12 alternating CPU pairs each on 32- and 128-node complete renders
did not establish a speedup (paired medians +0.86% and +1.23%,
respectively, with wide scatter). No app timing or memory claim.

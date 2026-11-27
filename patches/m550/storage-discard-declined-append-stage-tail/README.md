# Stop writing an already-discarded display stage

Skip the final BufWriter flush only when the existing typed guard declines
projection. This does not skip staging earlier bytes or any verification.
Published stages use the same flush and show identical serialized content.

Current Modules `f4bd470def2255f3459b7a42b50e96d0faa0bbf1`. A synthetic direct storage test with
19 inline append records and 3,800 messages caught 47,234 pending bytes at
the discard boundary. The logical temporary-file growth was 47,234→0.
The subsequent canonical pages, decode counts and journal bytes matched.
Both exact arms passed 118 tests (one ignored) and built standalone
optimized Storage libraries.

Earlier #856 covered only the singleton case on an older source, and
should not be stacked with this selector. The new coverage is the current
multi-append decline branch. No device write or product timing claim.

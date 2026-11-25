# Desktop/Core portable: skip manifest resolution for unrelated Cargo artifacts

A nonempty string target name different from the requested binary cannot be accepted. Skip resolving its manifest after the existing field type checks. Potentially matching artifacts still need the exact manifest path, name, binary kind, non-test profile and single existing executable. Cargo arguments, environment, build-finished checks and diagnostic forwarding are unchanged.

This helper is used by the default Desktop-only and Core-only portable paths, not the separate Modules packager changed in #775. Local controls use real fixture paths and simulated Cargo output. The 305-artifact controlled case went from 307 to 6 calls to resolve paths. These checks count path-resolution calls, not disk operations or build time. The new gate no longer surfaces an incidental filesystem error from resolving an unrelated path in an artificial record. Selected manifest checks are unchanged.

Apply `source.patch` to the pinned Desktop file. There is no alternate.

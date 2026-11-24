# Skip serializing a diff that cannot fit

Use input UTF-8 bytes plus the two JSON quotes as a lower bound. Any potentially fitting diff still uses the original exact serializer and the same combined-size limit.

The native sizing gate matched the original decision in 61,502 cases. In the eight-file synthetic window, the same seven fit and the eighth is rejected without 524,296 bytes of work in the serializer. No Git process, timing, memory, or network measurement.

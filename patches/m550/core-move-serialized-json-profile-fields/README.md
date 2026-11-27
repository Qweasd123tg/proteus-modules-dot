# Move serialized JSON fields into the profile document

Move already-owned managed JSON values into the final document instead
of deep-cloning them. Keep whole-config serialization, authored baseline
validation, inherited local settings and atomic replacement in place.

Exact Core `7f86a85b0b45de62c08ca36f21244afc03e6101e`. 58 targeted release tests passed per arm.
The paired save fixture checks exact bytes for component insert, replace
and removal, unmanaged fields and nested JSON nulls. Malformed-source and
non-UTF8 configuration checks leave the original file intact.
The small fixture avoids 55 allocation requests and
6,462 cumulative requested bytes per save; the fixture with
two 64 KiB managed values avoids 57 requests and
137,534 requested bytes. This is not process PSS or I/O time.
Strict apply and reversal pass alongside the preceding config/replay stack.

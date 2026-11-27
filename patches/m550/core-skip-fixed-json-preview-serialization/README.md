# Skip preview serialization for fixed-size JSON

When their known compact encodings fit, return null, booleans and empty
strings, arrays or objects directly. All other input and smaller budgets
keep the previous bounded writer.

Exact Core `7f86a85b0b45de62c08ca36f21244afc03e6101e`. The release probe removed one scratch allocation
(64 requested bytes for null) per eligible value. The retained
background card fixture observed one fewer request each for empty args
and default-null result metadata. Exact bytes and tiny budgets were
checked, and 18 focused tests passed in each arm.

Separate helper-only timing and the strict full-stack binding after
#911–913 are recorded in the receipt. No real tool or app measurements.

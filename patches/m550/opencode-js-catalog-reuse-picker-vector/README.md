# OpenCode JavaScript catalog: reuse the filtered result array

First apply every existing provider and chat eligibility check. Then replace the entries of that fresh, private filtered array with picker entries rather than allocating a second array. Keep native model snapshots unchanged, including the cached provider snapshots. Catalog order, eligibility, labels, visibility, and packaged reasoning overlays are unchanged.

This affects list projection in the OpenCode JavaScript adapter, not network refresh, credentials, provider selection, Rust OpenCode Go, or end-to-end startup. The isolated Node fixture verifies ordinary native catalogue DTOs and a controlled adapter boundary; it does not measure process memory or time.

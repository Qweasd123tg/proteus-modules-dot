# Compare resolved model keys without copying

Source catalogue ownership still uses the same sorted local names, exact
key equality and existing completeness guards. Replace only the temporary
list of resolved aliases with a length check and a borrowed iterator over
the ordered map. Alias precedence, includes and editor decisions are unchanged.

Exact Core `7f86a85b0b45de62c08ca36f21244afc03e6101e`. Both release arms passed 92 targeted config
and editor tests. Prepared native capture with two aliases saved one
16-byte allocation; 1,024 synthetic aliases saved one 8,192-byte
allocation. The already denied and empty controls were unchanged.
The separate predicate-only CPU screen includes sorted, shuffled and
late-swap inputs. This did not measure startup or total process memory.

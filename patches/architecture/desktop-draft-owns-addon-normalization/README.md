# Desktop: keep add-on list normalization in the settings draft

Base: `Proteus-harness/Proteus-desktop@dd51ad4af74756dacf5b2473a758a3109c1fce80`.

Building an editable settings draft no longer imports the add-ons presentation/edit module just to normalize two lists. The draft now owns the same sort/dedup operations for disabled skills and MCP servers. The UI, primitive composition, schema, switch behavior and save format do not change. A list-only MCP entry can return to its baseline without a save payload; a configured server's explicit enabled flag retains the prior behavior.

Verify the packet with `sha256sum -c SHA256SUMS`. In the Desktop checkout, run `git apply --check source.patch`, then apply `source.patch`. The same source patch was verified against main and the established cumulative Desktop test overlay. The receipt identifies the exact trees and four native settings tests per base; these only use in-memory fixtures, no MCP server or plugin processes.

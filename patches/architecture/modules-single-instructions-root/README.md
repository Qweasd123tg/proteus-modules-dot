# Use one workspace root for reading and labeling Codex instructions

Resolve the workspace root once per project-instructions provider entry.
Content and its heading use the same result instead of doing another root
lookup after the read. Discovery, file containment, budgets and rendering
are unchanged for a stable tree.

Use source.patch for pinned Modules and source-after-stack.patch for the
cumulative tree. Four native tests per base use temporary files and a
controlled root resolver, without invoking Git or any tool.

# Keep Git document targets independent of rendering

The Git graph and panel no longer depend on the document renderer for
arguments or widgets. Parse and encode targets in the model, resolve short
commit IDs in history, and keep each shared widget with its graph or panel.
The navigation calls, titles, widget payloads and diff limits stay the same.

Use source.patch with the pinned Extensions revision or source-after-stack.patch
with the cumulative source tree. Verification runs focused synthetic native
fixtures without opening an extension host, Git process or network listener.

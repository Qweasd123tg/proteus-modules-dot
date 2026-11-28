# Keep detached window construction with the Desktop shell

Workspace still owns the retained tab and transfers it in the same
event turn, but it no longer constructs Launcher. The shell opens
the destination before the source is extracted. A failed open leaves
an already-retained document and its source tab in place.

Use source.patch on pinned Desktop, or source-after-stack.patch on the
verified cumulative tree. Headless tests check retained identity, rehost,
caption, pin and recently closed history, without a real backend.

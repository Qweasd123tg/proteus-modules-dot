# Desktop: declarative widgets use a shared color mapping, not their renderer

Move the existing `icon_tone` and `tone_color` functions intact into a private sibling shared by the renderer, badges, cells, graph, lanes and tree rows. Those widgets no longer need the main renderer to look up a visual tone. Active theme reads and literal custom RGB match the original projections; the existing widget-specific choices remain in their own widgets.

No changes to extension installation, process admission, SDK or protocol. Apply to exact Desktop `4015530444740e56fe35f8dfa27b4571cdd2ffcc` or to the cumulative Desktop architecture stack through #973. Native headless GPUI checks cover the six semantic tone mappings plus custom RGB, changing theme and independent windows; other targeted tests protect wire decoding and palette accessibility.

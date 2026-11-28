# Desktop: remove two reciprocal icon-validation dependencies

Base: `Proteus-harness/Proteus-desktop@b93833f5043d1c2f10bb6c40638587f56e591ffc`.

Widget nodes still legitimately embed control and list schemas. Those schemas now obtain the existing icon validator from the same internal module that owns the icon map, rather than importing back from widget. No new abstraction or package dependency. The widget/control/list validation sequence, icon keys, diagnostics, and the separately owned manifest checks are unchanged. No public or plugin protocol changes.

Apply from the exact Desktop root with `git apply --check source.patch`, then `git apply source.patch`. Verify packet files with `sha256sum -c SHA256SUMS`. The same patch was checked strictly in both directions on the exact current main tree and its rebased architecture verification overlay. Overlay replay keeps both its existing render-generation module and upstream's reorder visibility.

Five headless native tests on each tree cover the icon registry, control icons, menus/prompts/split buttons, panel/list icon validation, and content-only manifest admission. No model, live extensions or tools, benchmarks, or deployment.

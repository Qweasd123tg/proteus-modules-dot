# Active-pane document projection

This isolated source-only prototype chooses the narrow contract `active_pane_documents`, explicitly not actual native visibility/occlusion. Reads under Settings, feature compatibility and the dependency on PR146 remain explicit.

## Invariant

One native Host layout sample yields two different values: the unchanged focused document argument, and every active pane's document argument belonging to the same extension in the displayed chat space. Retained inactive tabs and other chat spaces are excluded. The list has pane order but consumers use membership. It is not a path canonicalizer or an operating-system visibility detector.

Every native event carries the whole list, including `[]`; initial per-context announcement does too via PR146. SDK moves the owned list between its current Host and Scope record, never into session-shared state. Newly created contexts start empty; removal of the last context clears the new list. No field is inferred from render arguments or focused document.

Files uses membership only for freshness of an already cached preview. Cache keys (path, mode), session ownership, checked time, existing POLL schedule and sibling sharing are unchanged. Cold missing entries can still load regardless of membership; session_opened/run_settled invalidation can still reload retained entries. No zero-I/O promise for all hidden views.

## Deliberately not actual visibility

Settings replaces the native tab area without changing the logical layout. This prototype does not add Settings open/close events or a settings guard. More than one cached active-pane preview can therefore be eligible under Settings, unlike the old focused-only rule. Occluded/minimized windows are not detected. There is no claim that callback/timer execution is paused when the app is not on screen.

## Compatibility

Add `documents.active_panes.v1` to Desktop features and Files required_features, retaining protocol 4 and focused `event.document`. Feature gating is intended to reject the new Files manifest on hosts lacking the feature rather than silently provide old semantics. Older-host compatibility has not been tested and is not guaranteed, including for other packages; SDK treats an absent list as empty, not as the focused document. Present lists deserialize as arrays of strings before replacing navigation metadata.

## Scope discipline

No native selection, action identity, command behavior, permissions, process policy, sandbox or filesystem operation is changed. Host::active_document's existing lifetime/displayed-space gates become gates for the paired projection. Existing focused metadata cleanup outside this change remains unchanged. The two new-list reset points preserve the existing context-control flow rather than refactoring routing.

## Dependency and qualification

Desktop patch is against pinned Desktop plus PR146 navigation-bootstrap.patch. Applying only the new field to baseline would not seed initial context metadata. That old candidate remains uncompiled, and its generated stub harness is not silently claimed compatible with the renamed native helper. Full qualification must update/run producer bootstrap controls, native Host space/lifetime guards, SDK context lifecycle, real Files polling, Settings and rehost flows. No Rust/native/HTTP test has run here.

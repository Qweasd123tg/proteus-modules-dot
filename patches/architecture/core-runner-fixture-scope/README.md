# Keep Core test fixture preparation scoped

Use named storage and reference fixtures for a single known integration
target with either spaced or equals Cargo syntax. Keep full preparation for
mixed and unrecognized selections. The component_sandbox legacy spaced
command is unchanged; its equals form retains full preparation and PATH.
The Cargo command and explicit fixture precedence are unchanged.

Apply source.patch to pinned Core and source-after-stack.patch to the
cumulative tree. The receipt records isolated Python mock tests and a
direct before/after fixture-selection comparison on each base. No real
Cargo, package build, or worker ran.

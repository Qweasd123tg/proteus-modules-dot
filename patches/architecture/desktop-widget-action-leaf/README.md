# Desktop: make retained widget actions independent of the widget registry

Tree, graph, and row widgets used to import `WidgetAction` from the field registry that owns or builds those widgets. They now import the same binding directly from a private leaf module. `DeclarativeView` still creates the binding through the same weak view reference; replacing current action names, event payloads, admission, and dispatch all retain their existing behavior. No change to independently installable extension packages, SDK, or extension protocol.

The same patch applies to exact Desktop `4015530444740e56fe35f8dfa27b4571cdd2ffcc` and to the cumulative Desktop architecture stack through #965. See `receipt.json` for exact trees and focused native checks.

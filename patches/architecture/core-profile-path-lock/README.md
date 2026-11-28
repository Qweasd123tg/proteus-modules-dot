# Core: the profile/config builder share a path lock, not each other

The config builder publishes profiles. The profile publisher previously imported the shared path lock back through the builder. Move the existing lock registry into a private app-server sibling, `config_path_lock`, and let the builder, profile reload, watcher, and session settings use it directly. There is still one registry. Path identity (including embedded role aliases), acquisition and guard lifetimes, publication order, and the public and process protocol interfaces are unchanged. No changes to the independently installed modules.

This cuts the reverse import through the builder, not every connection in the app server. The same patch applies to Core `024fb944a91382026bb2aa5c7b8da65c284d0305` alone or on the prior verified architecture stack. See `receipt.json` for the trees, strict forward/reverse checks, and native checks on both bases.

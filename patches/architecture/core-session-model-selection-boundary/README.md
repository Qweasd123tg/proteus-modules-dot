# Core: separate model routing from selection persistence

The settings entry point sends typed model choices to the existing same-provider selection path or to the existing cross-provider model path. A private metadata reader owns the same 16 KiB application limit. This removes both dependencies from model code back into selection persistence; selection still delegates scoped persistence to the model implementation.

The provider guard, local acknowledgement, validation, storage mutation order, schemas and limits are unchanged. The patch applies to Proteus-harness/Proteus-core at `024fb944a91382026bb2aa5c7b8da65c284d0305` and the checked cumulative Core tree. See `receipt.json` for selected native checks.

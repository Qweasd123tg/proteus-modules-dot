# Independent exact source review

Verdict: source-acceptable bounded loader fix; no blocking defect found. Tests have not been executed or imported by this reviewer. Baseline Core bcbda4435534a296c707a1daa250813d692f68e1; seven source blobs are coordinator-verified provenance.

Independently hashed exact patch: `d962a709d16499c56ef81eb2edcff6f01c85eb5381f591bc56e9f46870181b0d`.

The local helper implements the reviewed contract: module creation before mutation; identity sentinel for absent versus None; registration before exec; fresh module retained on success; exact previous binding restored or new registration removed for BaseException; original exception re-raised. Both former execution sites delegate with unchanged reserved names and paths. Archive extraction and existing consumer grading assertions remain unchanged. This does not add caching, a shared framework, concurrent import coordination, dependency rollback or general package loading.

The six proposed methods use the real loader functions. runpy loads declarations with only pytest's parametrization decorator stubbed; globals are rebound through the actual entry function's globals dictionary. Other function definitions in that grader share that namespace, including the selected existing consumer body. That body receives a trivial private archive function and private measurements dataclass module, and calls unchanged journal text/message_digest helpers; it does not establish valid archive behavior. The other grader bodies, native CLI calls and full pytest grading remain idle. Existing sampler loading is only a positive registration control; its weaker failure cleanup is not fixed here.

Success-reload fixture changes source length (1 to 22), avoiding same-size timestamp bytecode ambiguity, and execution is planned with -B. Failure fixtures explicitly assert registration during initialization and check original exception identity, absent-entry removal, previous-module restoration and explicit None restoration for both ValueError and SystemExit. patch.dict(sys.modules) and replacement sys.path list restore their previous mappings/list after each context, including error unwinding. They do not promise rollback of mutations to arbitrary preexisting module objects, which these fixtures do not perform.

The two proposed raw-baseline controls are expected to ERROR inside dataclasses on missing module registration, not fail an ordinary comparison assertion. Runtime reporting must inspect that specific AttributeError traceback, rather than treat any nonzero exit as the intended reproduction. Candidate six-test success remains a future observation at this stage.

## Nonblocking isolation caveat

The journal grader inserts /app/examples/performance/history-scale at the front of sys.path during runpy. Therefore inserting the private copied code directory beforehand alone does not guarantee the copied journal wins on every machine. A read-only filesystem check here found /app/examples/performance/history-scale/journal.py absent, so this does not block the planned current isolated-copy run. For a portable control, pre-load the copied journal or assert its resolved __file__ before exercising fixtures. This is a test provenance caveat, not a production helper defect.

## Independent candidate hashes

- grader_loaders_test.py: `e7275609fb3de5e9e5a8ba1d3e72efc59fd4bf63c6b488966643a38bc631de0a`
- grader_loaders.md: `f65c5c565cdb3569e60d63940e333d151cec61a2c7f2d8bad67658d03c373e93`
- journal grader test_outputs.py: `de321c8952d66cdcdb5236747d4ec73631137f0bed82de9a5d35403c278a5c29`

No graded solution, historical result, archive CLI, native process or project test was run in this review. The documentation correctly limits the change to loader fidelity and does not regrade saved benchmark outcomes.

## Final pre-execution revision

Independently re-read the test-only journal import adjustment and hashed final patch `cfddbd8a4917b89e5a10b7617f4f80c997d7d6467649b204fa21a7d2c8b897bd`. It supersedes the initial patch hash above. The private code path is inserted, the previously cleared journal name is explicitly imported, and its __file__ is asserted to equal the private copy before runpy. The grader then reuses that cached exact module, closing the /app precedence caveat. Existing context restoration still applies. No project code was executed by this reviewer.

Final test hash: `611d550f59afd0f77d09c996a9e55c53b91fc80db8a5cf1383749d507ba82f17`. Production grader hash remains `de321c8952d66cdcdb5236747d4ec73631137f0bed82de9a5d35403c278a5c29`. Source verdict unchanged: acceptable for the explicitly bounded planned controls, not a runtime pass claim.

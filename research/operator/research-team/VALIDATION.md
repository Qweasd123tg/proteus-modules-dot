# Validation: historical static controls, no adapted execution

Original R41 executed29 own pure/static Python controls and a five-leaf scaffold check. Source receipt `797dc33695feb8662443d02831ce8d5bb5906ac5073695be343debfe757b71a5`; independent source/static review `fbd6e940f88ff2e6e3842d58bea05ff2dc5595dfda774fff9e317bdbe44efb31`.

The mapped check_recipe.py, test_recipe.py, four TOML files and call-examples.json are byte-identical to those original inputs. The historical result belongs to those exact bytes. This public layout/adapted documentation was **not executed**, and has no new29-control receipt. No test outputs are relabeled as current results.

The checker only reads its five fixed owned leaves. It does not follow provider includes, load Core, validate the actual installed catalog or prove policy/OS confinement. operator-provider.toml remains intentionally absent. A real installation requires separately authorized provider/config/catalog/approval review, three actual children, independent read observations and error/cancel/recovery gates — all unrun here. Static read.recipe_path is not runtime permission.

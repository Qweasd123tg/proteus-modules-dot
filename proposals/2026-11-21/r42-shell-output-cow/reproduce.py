#!/usr/bin/env python3
"""Fresh candidate, real shell-tool unit tests and byte-for-byte production-renderer differential."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess as sp
import tempfile

base = "9469e3b12529d08b1f4a76882693e2065e842c51"
here = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("repository", type=Path)
parser.add_argument("--compiler", type=Path, help="optional rustc wrapper taking ordinary rustc arguments and supplying dependencies")
args = parser.parse_args()
with tempfile.TemporaryDirectory(prefix="render-",dir=os.environ.get("TMPDIR")) as td:
    tree = Path(td)/"source"
    sp.run(["git","clone","-q","--shared","--no-checkout",args.repository.resolve(),tree],check=True)
    def run(*cmd):
        sp.run(cmd, cwd=tree,check=True)
    if args.compiler:
        run("git","sparse-checkout","set","tool/shell-tool")
    run("git","checkout","-q","--detach",base)
    run("git","apply","--check",here/"candidate.patch")
    src=tree/"tool/shell-tool/src"
    output=src/"unified_exec/output.rs"
    old=output.parent/"r42_before"
    old.mkdir()
    shutil.copyfile(output, old/"mod.rs")
    shutil.copyfile(output.parent/"output/tests.rs",old/"tests.rs")
    run("git","apply",here/"candidate.patch")
    run("git","diff","--check")
    shutil.copyfile(here/"probe.rs",output.parent/"render_probe.rs")
    with (src/"unified_exec.rs").open("a") as f:
        f.write('\n#[cfg(test)]\n#[path="unified_exec/r42_before/mod.rs"] mod r42_before;\n#[cfg(test)] mod render_probe;\n')
    if args.compiler:
        exe=Path(td)/"suite"
        run("python3",args.compiler.resolve(),"--test","--crate-name","shell_tool","-O",src/"lib.rs","-o",exe)
        cmd=[exe]
    else:
        cmd=["cargo","test","--locked","--release","-p","shell-tool","--lib","--"]
    for case in ["unified_exec::output::tests::","unified_exec::tests::truncate_head_tail_respects_char_boundaries",
                 "unified_exec::tests::pipe_exec::bounded_buffer_keeps_the_original_head_and_latest_tail",
                 "unified_exec::tests::pipe_exec::long_empty_poll_returns_final_stdout_and_stderr_once",
                 "unified_exec::tests::exec_command_reports_exit_for_quick_command",
                 "unified_exec::tests::exec_command_reports_nonzero_exit_as_data_not_tool_failure",
                 "unified_exec::tests::exec_command_truncates_output_head_and_tail",
                 "unified_exec::render_probe::compare_renderers"]:
        run(*cmd,case,"--nocapture","--test-threads=1")

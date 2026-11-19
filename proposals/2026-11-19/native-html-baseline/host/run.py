"""Compare instrumented release TestAppContext hosts, excluding compilation/startup."""
import argparse
import hashlib
import json
import os
import platform
import statistics
import subprocess
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("bin", "corpus", "output"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--cpu", type=int, default=max(os.sched_getaffinity(0)))
    parser.add_argument("--pairs", type=int, default=6)
    parser.add_argument("--laps", type=int, default=16)
    args = parser.parse_args()

    def pin():
        os.sched_setaffinity(0, {args.cpu})

    out = {"cpu":args.cpu, "kernel":platform.release(), "cases_sha256":sha(args.corpus),
           "timed_laps_per_fresh_process":args.laps,"cases":{}}
    for mode in ("time", "heap"):
        bins = [(args.bin / (side+"-"+mode)).resolve() for side in ("stock","after")]
        out[mode+"_elf_sha256"] = list(map(sha,bins))
        assert len(set(out[mode+"_elf_sha256"])) == 2
        for case in ("typical32","edge32","control32"):
            pairs = [[], []]
            fields = ("first_ns","sync_ns","idle_ns") if mode=="time" else ("alloc_calls","alloc_bytes")
            for r in range(args.pairs):
                for side in ([0,1] if r%2==0 else [1,0]):
                    cmd = [bins[side],args.corpus,"batch",case,str(args.laps)]
                    rows = json.loads(subprocess.check_output(cmd,timeout=90,preexec_fn=pin))
                    for x in rows:
                        x["alloc_calls"],x["alloc_bytes"]=x.pop("alloc_calls_bytes")
                        if case=="control32":
                            assert x["fg"][0]==0 and x["bg"][0]==32
                        else:
                            n=1 if case=="one" else 32
                            assert x["fg"][0]==n and x["bg"][0]==(0 if side else n)
                    pairs[side].append({key: statistics.median(x[key] for x in rows) for key in fields})
            summary={key: [statistics.median(x[key] for x in group) for group in pairs] for key in fields}
            out["cases"].setdefault(case,{})[mode]={"process_medians":pairs,"median":summary}
            print(case,mode,summary,flush=True)
            args.output.write_text(json.dumps(out,indent=2)+"\n")


if __name__=="__main__":
    main()

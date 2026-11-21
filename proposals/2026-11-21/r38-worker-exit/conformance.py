"""Exercise ordinary strict List with the real conformance CLI and a Rust storage worker."""
from pathlib import Path
from subprocess import check_output
from tempfile import TemporaryDirectory
import sys, json
binary, worker = [str(Path(p).resolve()) for p in sys.argv[1:3]]
with TemporaryDirectory(dir=".") as directory:
    root = Path(directory).resolve()
    for backend in ["jsonl", "sqlite"]:
        catalog = root/backend
        catalog.mkdir()
        export = {"slot":"session_storage","module_id":backend,"contract_version":"v2","module_config":{}}
        params = {"operation":"list","config_root":str(catalog),"workspace_path":None,"audit":False}
        args = [binary,"--component-id","session-storage","--export",json.dumps(export),
            "--probe-export","session_storage/"+backend,"--probe-method","execute",
            "--probe-params",json.dumps(params),"--timeout-ms","3000","--", worker]
        report = json.loads(check_output(args,text=True))
        probe=report["probe"]
        assert report["handshake"]=="success" and probe["terminal"]=="success", report
        assert probe["result"] == {"result":"sessions","sessions":[]}, probe["result"]
        print(f"{backend}: strict List = {probe['result']} (wire ID {probe['invocation_id']})")

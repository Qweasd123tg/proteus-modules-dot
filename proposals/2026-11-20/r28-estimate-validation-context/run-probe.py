"""Args: path to exact Core checkout, matching debug/deps, empty/output directory; rustc on PATH."""
import json,sys,subprocess
from pathlib import Path
src,deps,out=(Path(x).resolve() for x in sys.argv[1:4])
reference=Path(sys.argv[4]).resolve() if len(sys.argv)>4 else deps
out.mkdir(exist_ok=True)
p=Path(__file__).with_name('probe.rs.in').read_text()
p=p.replace('MODEL_FILE',json.dumps(str(src/'crates/proteus-core/src/core/model_service.rs'))).replace('ALLOC_FILE',json.dumps(str(src/'crates/proteus-contracts/src/test_alloc.rs')))
rs=out/'main.rs';rs.write_text(p)
cmd=['rustc','--edition=2024','-C','link-arg=-fuse-ld=lld','-L','dependency='+str(deps)]
for lib in ('proteus_contracts','anyhow','async_trait','async_stream','serde_json','futures_util'):
    matches=list(reference.glob(f'lib{lib}-*.'+('so' if lib=='async_trait' else 'rlib')))
    assert len(matches)==1,(lib,matches)
    target=deps/matches[0].name
    assert target.is_file(),target
    cmd+=['--extern',f'{lib}={target}']
exe=out/'probe';subprocess.run(cmd+[str(rs),'-o',str(exe)],check=True);subprocess.run([str(exe)],check=True)

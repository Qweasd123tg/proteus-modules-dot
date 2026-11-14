import csv, hashlib, json, subprocess
from pathlib import Path
root=Path('/workspace/shared/model-adapters-audit')
out=Path(__file__).parent
full='''model/model-pack/src/adapters/anthropic.rs
model/model-pack/src/adapters/anthropic/stream.rs
model/model-pack/src/adapters/anthropic/response.rs
model/model-pack/src/adapters/anthropic/request.rs
model/model-pack/src/adapters/anthropic/sanitize.rs
model/model-pack/src/adapters/anthropic/usage.rs
model/model-pack/src/adapters/openai.rs
model/model-pack/src/adapters/openai/stream.rs
model/model-pack/src/adapters/openai/stream_state.rs
model/model-pack/src/adapters/openai/response.rs
model/model-pack/src/adapters/openai/response/item.rs
model/model-pack/src/adapters/openai/request.rs
model/model-pack/src/adapters/openai/model_profile.rs
model/model-pack/src/adapters/openai/transport.rs
model/model-pack/src/adapters/openai/sse_idle.rs
model/model-pack/src/adapters/http_retry.rs
model/pi-provider/adapter.mjs
components/pi-runtime-js/messages.mjs
tool/pi-tools/adapter.mjs
model/model-pack/src/adapters/anthropic/request_tests.rs
model/model-pack/src/adapters/anthropic/image_tests.rs
model/model-pack/src/adapters/openai/image_tests.rs
model/model-pack/src/adapters/stream_fallback_tests.rs
tool/pi-tools/tests/provider-messages.test.mjs
tool/pi-tools/tests/provider-failure.test.mjs'''.splitlines()
sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
rows=[]
for p in full:
    data=subprocess.check_output(['git','show',f'{sha}:{p}'],cwd=root)
    n=len(data.splitlines())
    rows.append({'repository':'Proteus-modules','revision':sha,'path':p,'lines':n,'reviewed_ranges':f'1-{n}','reviewed_lines':n,'status':'full','sha256':hashlib.sha256(data).hexdigest()})
with (out/'coverage.tsv').open('w') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]),delimiter='\t');w.writeheader();w.writerows(rows)
meta={'note':'Conservative manual reading coverage, not runtime/test coverage. Only fully read baseline files counted; partially read files, Cargo/AGENTS/build scripts and added tests excluded. No claim of complete module repository audit.','repository_revision':sha,'files_fully_read':len(rows),'lines_read':sum(r['reviewed_lines'] for r in rows),'files':rows}
(out/'coverage.json').write_text(json.dumps(meta,indent=2)+'\n')
print(meta['files_fully_read'],meta['lines_read'])

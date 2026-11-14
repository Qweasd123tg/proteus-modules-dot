import sys
from pathlib import Path
bundle=Path(sys.argv[sys.argv.index('--bundle')+1]); (bundle/'bin').mkdir()
module=bundle/'bin/proteus-model-pack-module'; module.write_text('#!/bin/sh\nprintf module-stub\n'); module.chmod(0o755)

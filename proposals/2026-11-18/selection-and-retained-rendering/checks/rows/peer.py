from pathlib import Path
import argparse, subprocess, tempfile
a=argparse.ArgumentParser(); a.add_argument('candidate',type=Path);a.add_argument('--rustc',default='rustc');o=a.parse_args()
src=(o.candidate/'src/ui/extensions/declarative/rows.rs').read_text()
frame=Path(__file__).with_name('peer.rs.in').read_text()
method=src[src.index('    pub fn set_rows'):src.index('    pub fn focus')]
with tempfile.TemporaryDirectory() as tmp:
    t=Path(tmp);(t/'test.rs').write_text(frame.replace('//SET_ROWS',method));subprocess.run([o.rustc,'--edition=2024','-O',t/'test.rs','-o',t/'test'],check=True)
    subprocess.run([t/'test'],check=True)

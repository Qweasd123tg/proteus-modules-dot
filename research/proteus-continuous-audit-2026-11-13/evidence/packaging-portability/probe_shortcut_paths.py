#!/usr/bin/env python3
"""Exercise production shortcut installer and genuine Linux .desktop launcher."""
import argparse,json,os,shutil,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('--desktop',type=Path,default=Path('/workspace/shared/packaging-portability-audit'))
p.add_argument('--output',type=Path,default=Path(__file__).parent/'shortcut-fixtures-repro')
a=p.parse_args(); root=a.output.resolve();root.mkdir(parents=True,exist_ok=False)
source=a.desktop/'scripts/portable/install-shortcut';rows=[]
for case,name in [('plain','Portable'),('spaces','Portable folder'),('unicode','Portable тест'),('percent','Portable 100%'),('doublequote','Portable "test"'),('backslash',r'Portable\test')]:
 portable=root/name;portable.mkdir();(portable/'share/icons').mkdir(parents=True)
 (portable/'share/icons/proteus-native.svg').write_text('<svg/>')
 shutil.copy2(source,portable/'install-shortcut')
 executable=portable/'proteus-native'
 executable.write_text('#!/bin/sh\nprintf launched > "${PROBE_MARKER}"\n');executable.chmod(0o755)
 data=root/('data-'+case);marker=root/('marker-'+case)
 env={**os.environ,'XDG_DATA_HOME':str(data),'PROBE_MARKER':str(marker)}
 direct=subprocess.run([str(executable)],env=env,capture_output=True,text=True)
 assert direct.returncode==0 and marker.read_text()=='launched';marker.unlink()
 install=subprocess.run(['sh',str(portable/'install-shortcut')],env=env,capture_output=True,text=True)
 entry=data/'applications/dev.proteus.native.desktop'
 validate=subprocess.run(['desktop-file-validate',str(entry)],env=env,capture_output=True,text=True)
 launch=subprocess.run(['gio','launch',str(entry)],env=env,capture_output=True,text=True)
 for _ in range(20):
  if marker.exists():break
  time.sleep(.05)
 launched=marker.exists()
 assert install.returncode==0
 assert launched==(case in ('plain','spaces','unicode'))
 rows.append({'case':case,'path':str(portable),'direct_status':direct.returncode,'install_status':install.returncode,'validate_status':validate.returncode,'validate_stdout':validate.stdout,'launch_status':launch.returncode,'launch_stderr':launch.stderr,'launched':launched,'entry':entry.read_text()})
report={'desktop_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=a.desktop,text=True).strip(),'gio_version':subprocess.check_output(['gio','version'],text=True).strip(),'rows':rows,'scope':'Unmodified install-shortcut, real desktop-file-validate and gio launch. Harmless marker executable instead of GPUI application. Isolated XDG data; no desktop GUI or user installation.'}
(root.parent/'shortcut-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2))

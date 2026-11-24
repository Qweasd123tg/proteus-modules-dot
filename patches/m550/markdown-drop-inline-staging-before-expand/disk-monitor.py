from pathlib import Path
import json,os,shutil,signal,subprocess,sys,time
workspace=Path.cwd()
minima={}
required={"workspace":100*2**20,"tmp":200*2**20}
def sample():
    return {"workspace":shutil.disk_usage(workspace).free,"tmp":shutil.disk_usage("/tmp").free}
def observe():
    measured=sample()
    for k in required:minima[k]=min(minima.get(k,measured[k]),measured[k])
    return measured
def low(values):
    return any(values[k]<required[k] for k in required)
before=observe()
last=before
blocked=low(before)
status=None
if not blocked:
    proc=subprocess.Popen(sys.argv[2:],start_new_session=True)
    while True:
        last=observe()
        if low(last):
            blocked=True
            try:
                os.killpg(proc.pid,signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                status=proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid,signal.SIGKILL)
                status=proc.wait()
            break
        status=proc.poll()
        if status is not None:break
        time.sleep(.12)
last=observe()
blocked=blocked or low(last)
receipt={"units":"bytes","required":required,"before":before,"min_sampled":minima,"last":last,
         "floor_stop":blocked,"native_exit_status":status}
Path(sys.argv[1]).write_text(json.dumps(receipt,indent=2)+"\n")
print("disk_watch",json.dumps(receipt),flush=True)
raise SystemExit(126 if blocked else status or 0)

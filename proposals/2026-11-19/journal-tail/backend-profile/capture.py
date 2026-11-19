"""Run the existing R7 Core candidate full-turn harness on a single CPU; preserve host observation timestamps."""
import argparse,os,pathlib,subprocess,time
p=argparse.ArgumentParser()
for arg in ["harness","worker","reference","out"]:p.add_argument(arg,type=pathlib.Path)
p.add_argument('--cpu',type=int,required=True); args=p.parse_args()
env={**os.environ,'PERF7_CASES':'5000,50000','PROTEUS_TEST_REFERENCE_MODULE':str(args.reference.resolve()),'PROTEUS_TEST_SESSION_STORAGE_MODULE':str(args.worker.resolve())}
with args.out.open('x') as log:
 proc=subprocess.Popen(['taskset','-c',str(args.cpu),str(args.harness.resolve()),'perf7_real_turn_fixed_active_history','--nocapture','--test-threads=1'],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 for b in proc.stdout: print(time.time_ns(),b.decode().rstrip(),file=log,flush=True)
 rc=proc.wait()
raise SystemExit(rc)

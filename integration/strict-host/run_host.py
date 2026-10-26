#!/usr/bin/env python3
"""Linux-only owned-descendant controller. No network sandbox is claimed.

Requires ordinary /proc child lists, PR_SET_CHILD_SUBREAPER and pidfds. There is
no privilege escalation or fallback to a broad process-name/group kill. Files,
not pipes, capture child output so inherited descriptors cannot block draining.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import resource
import select
import signal
import shutil
import subprocess
import sys
import time

CASES=("matching","wrong_suite","wrong_config","missing_assertion","omitted","read_denied","approval_denied","default_deny")
MAX_FILE=8*1024*1024
RESERVE=1024**3
STOP_FREE=RESERVE+128*1024**2

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def identities(pid):
    """Only children of this owned process, across all its threads."""
    children=set()
    try:
        tasks=list((Path('/proc')/str(pid)/'task').iterdir())
    except FileNotFoundError:
        if identity(pid) is not None:
            raise RuntimeError('owned task directory unavailable while process remains: ' + str(pid))
        return children
    for task in tasks:
        try:
            children.update(map(int,(task/'children').read_text().split()))
        except FileNotFoundError:
            if task.exists():
                raise RuntimeError('owned task child-list disappeared while task remains: ' + str(task))
    return children

def identity(pid):
    try:
        raw=(Path('/proc')/str(pid)/'stat').read_text()
    except FileNotFoundError:
        return None
    fields=raw[raw.rfind(')')+2:].split()
    return {'pid':pid,'state':fields[0],'ppid':int(fields[1]),'pgid':int(fields[2]),'start_time':int(fields[19])}

def subreaper():
    if sys.platform!='linux' or not hasattr(os,'pidfd_open') or not hasattr(signal,'pidfd_send_signal'):
        raise RuntimeError('Linux /proc, subreaper and pidfds required; no fallback')
    child_lists = list(Path('/proc/self/task').glob('*/children'))
    if not child_lists:
        raise RuntimeError('owned /proc task children lists unavailable; refusing to spawn')
    for child_list in child_lists:
        child_list.read_text()
    if identities(os.getpid()):
        raise RuntimeError('controller already owns children; refusing ambiguous scope')
    fd = os.pidfd_open(os.getpid(), 0)
    try:
        signal.pidfd_send_signal(fd, 0, None, 0)
    finally:
        os.close(fd)
    libc=ctypes.CDLL(None,use_errno=True)
    if libc.prctl(36,1,0,0,0)!=0: # PR_SET_CHILD_SUBREAPER on this authored controller only.
        raise OSError(ctypes.get_errno(),'could not set owned controller subreaper')

class Owned:
    def __init__(self):
        self.handles={}
        self.observed=[]
        self.adopted=[]
        self.direct_pid=None
    def register_root(self, pid):
        # Store the direct child's race-safe fd BEFORE optional /proc reporting.
        self.direct_pid=pid
        fd = os.pidfd_open(pid, 0)
        self.handles[(pid,None)] = fd
        self.observed.append({'pid':pid,'direct_popen_child':True})
        current = identity(pid)
        if current is not None:
            self.handles[(pid,current['start_time'])] = self.handles.pop((pid,None))
            self.observed[-1].update(dict(current,discovered_under=os.getpid()))
    def discover(self):
        me=identity(os.getpid())
        if me is None: raise RuntimeError('controller identity unavailable')
        todo=[(me['pid'],me['start_time'])]
        seen=set()
        def matches(pid,start):
            current=identity(pid)
            return current is not None and current['start_time']==start
        while todo:
            parent,parent_start=todo.pop()
            key_parent=(parent,parent_start)
            if key_parent in seen: continue
            seen.add(key_parent)
            if not matches(parent,parent_start): continue
            child_pids=identities(parent)
            if not matches(parent,parent_start): continue
            for pid in child_pids:
                if not matches(parent,parent_start): break
                before=identity(pid)
                if before is None or before['ppid']!=parent: continue
                key=(pid,before['start_time'])
                if key not in self.handles:
                    try: fd=os.pidfd_open(pid,0)
                    except ProcessLookupError: continue
                    after=identity(pid)
                    if after is None or after['start_time']!=before['start_time'] or after['ppid']!=parent or not matches(parent,parent_start):
                        os.close(fd)
                        continue
                    self.handles[key]=fd
                    self.observed.append(dict(before,discovered_under=parent,parent_start_time=parent_start))
                if parent==os.getpid() and pid!=self.direct_pid and {'pid':pid,'start_time':before['start_time']} not in self.adopted:
                    self.adopted.append({'pid':pid,'start_time':before['start_time']})
                todo.append(key)
    def living(self):
        # Readiness of the already-open pidfd avoids PID reuse and /proc
        # availability races during emergency cleanup of known children.
        found=[]
        for key,fd in self.handles.items():
            poll=select.poll();poll.register(fd,select.POLLIN)
            if not poll.poll(0): found.append((key,fd))
        return found
    def terminate(self, sig):
        errors=[]
        for fd in self.handles.values():
            try: signal.pidfd_send_signal(fd,sig,None,0)
            except ProcessLookupError: pass
            except OSError as error: errors.append(str(error))
        return errors
    def reap(self, root_pid):
        # Popen owns root's wait status; only adopted descendants are reaped here.
        for pid,_ in list(self.handles):
            if pid==root_pid: continue
            try: os.waitpid(pid,os.WNOHANG)
            except (ChildProcessError,ProcessLookupError): pass
    def close(self):
        for fd in self.handles.values(): os.close(fd)

def limits():
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    resource.setrlimit(resource.RLIMIT_CPU,(60,60))
    resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE,(MAX_FILE,MAX_FILE))
    resource.setrlimit(resource.RLIMIT_NOFILE,(256,256))

def capture(command,cwd,environment,stdout,stderr,timeout=60):
    """One bounded owned tree. Caller must call subreaper before the first run."""
    if identities(os.getpid()): raise RuntimeError('unexpected pre-existing owned child')
    owned=Owned()
    started=time.monotonic()
    timed_out=False
    disk_stopped=False
    disk_samples=[shutil.disk_usage(cwd).free]
    process=None
    cleanup_error=None
    capture_error=None
    direct_child_cleanup=False
    inspection_errors=[]
    remaining=None
    def inspect():
        try:
            owned.discover()
            return sorted(identities(os.getpid()))
        except (OSError, RuntimeError) as error:
            inspection_errors.append(str(error))
            return None
    with stdout.open('xb') as out,stderr.open('xb') as err:
        try:
            if disk_samples[0] < STOP_FREE:
                disk_stopped=True
                raise RuntimeError('disk reserve guard before spawn; no files deleted')
            process=subprocess.Popen(command,cwd=cwd,env=environment,stdin=subprocess.DEVNULL,stdout=out,stderr=err,preexec_fn=limits,start_new_session=True)
            owned.register_root(process.pid)
            while process.poll() is None:
                if inspect() is None:
                    break
                disk_samples.append(shutil.disk_usage(cwd).free)
                if disk_samples[-1] < STOP_FREE:
                    disk_stopped=True
                    break
                if time.monotonic()-started>=timeout:
                    timed_out=True
                    break
                time.sleep(0.01)
        except Exception as error:
            capture_error=type(error).__name__+': '+str(error)
        finally:
            if process is not None:
                # Component process groups may differ from the host's group.
                # Subreaper adoption keeps ownership discoverable after exit.
                end=time.monotonic()+5
                while True:
                    remaining=inspect()
                    try:
                        process.poll()
                        owned.reap(process.pid)
                        known_alive=bool(owned.living())
                    except OSError as error:
                        inspection_errors.append(str(error))
                        known_alive=True
                    if not known_alive and process.returncode is not None and remaining == []: break
                    if time.monotonic()>=end:
                        cleanup_error='owned descendants still present after bounded cleanup'
                        break
                    sig=signal.SIGTERM if time.monotonic()<end-3 else signal.SIGKILL
                    inspection_errors.extend(owned.terminate(sig))
                    if process.returncode is None and not any(pid==process.pid for pid,_ in owned.handles):
                        # A failed pidfd_open must not abandon our direct child.
                        # Popen owns its unreaped wait status; no other thread or
                        # helper reaps it. This never discovers/signals descendants.
                        direct_child_cleanup=True
                        try: process.send_signal(sig)
                        except OSError as error: inspection_errors.append(str(error))
                    time.sleep(0.02)
                try: process.wait(timeout=0.2)
                except subprocess.TimeoutExpired: cleanup_error='root still alive after bounded cleanup'
    if inspection_errors:
        cleanup_error='owned descendant state unknown after inspection error'
    evidence={'command':command,'cwd':str(cwd),'returncode':process.returncode if process else None,'timed_out':timed_out,
      'wall_seconds':time.monotonic()-started,'disk_guard_stopped':disk_stopped,'minimum_observed_free_bytes':min(disk_samples),'disk_stop_bytes':STOP_FREE,'disk_reserve_bytes':RESERVE,'cleanup_error':cleanup_error,'capture_error':capture_error,'direct_child_cleanup_fallback':direct_child_cleanup,'owned_processes':owned.observed,'adopted_descendants':owned.adopted,'root_pid':process.pid if process else None,
      'remaining_owned_children':remaining,'inspection_errors':inspection_errors,'stdout_sha256':digest(stdout),'stderr_sha256':digest(stderr),
      'mechanism':'Linux owned-child subreaper + descendant task child lists + pidfd signals; no process-name kill',
      'limits':{'cpu_seconds':60,'address_space_bytes':1024**3,'file_bytes':MAX_FILE,'wall_seconds':timeout,'cleanup_seconds':5.2}}
    owned.close()
    return evidence

def main():
    parser=argparse.ArgumentParser()
    for name in ('host','official','fixture','producer','gate','policy','output'): parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--stage',choices=('matching','all'),default='all')
    args=parser.parse_args()
    for name in ('host','official','fixture','producer','gate','policy'):
        path=getattr(args,name)
        if not path.is_absolute() or not path.is_file() or path.is_symlink(): raise ValueError('absolute regular input required: '+name)
    args.output.mkdir(parents=False,exist_ok=False)
    out=args.output.resolve()
    subreaper()
    before={name:{'path':str(getattr(args,name)),'sha256':digest(getattr(args,name))} for name in ('host','official','fixture','producer','gate','policy')}
    (out/'inputs-before.json').write_text(json.dumps(before,indent=2))
    processes=[]
    failed=False
    for case in CASES if args.stage=='all' else CASES[:1]:
        envroot=out/(case+'-environment');envroot.mkdir()
        for name in ('home','tmp','xdg-config','xdg-cache','xdg-data'): (envroot/name).mkdir()
        environment={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','HOME':str(envroot/'home'),'TMPDIR':str(envroot/'tmp'),
          'XDG_CONFIG_HOME':str(envroot/'xdg-config'),'XDG_CACHE_HOME':str(envroot/'xdg-cache'),'XDG_DATA_HOME':str(envroot/'xdg-data')}
        command=[str(args.host),case,str(out/case),str(args.official),str(args.fixture),str(args.producer),str(args.gate),str(args.policy)]
        result=capture(command,envroot,environment,out/(case+'.stdout'),out/(case+'.stderr'))
        result['scenario']=case
        processes.append(result)
        (out/'processes.json').write_text(json.dumps(processes,indent=2))
        if result['disk_guard_stopped'] or result['capture_error'] or result['returncode']!=0 or result['timed_out'] or result['cleanup_error'] or result['remaining_owned_children']:
            failed=True
            break
    after={name:{'path':str(getattr(args,name)),'sha256':digest(getattr(args,name))} for name in before}
    (out/'inputs-after.json').write_text(json.dumps(after,indent=2))
    if before!=after: raise RuntimeError('input hashes changed')
    if failed: raise RuntimeError('host capture failed; inspect retained processes and logs')
    print(json.dumps({'status':'captured_not_semantically_validated','scenarios':[p['scenario'] for p in processes]}))

if __name__=='__main__': main()

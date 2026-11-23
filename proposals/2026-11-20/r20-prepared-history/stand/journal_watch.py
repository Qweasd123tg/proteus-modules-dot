"""Linux inotify witness for opens of canonical journal files, not bytes read."""
import ctypes, os, struct

class JournalOpens:
    OPEN=0x20
    OVERFLOW=0x4000
    EVENT=struct.Struct('iIII')
    def __init__(self, dirs, filename="journal.jsonl"):
        c=ctypes.CDLL(None,use_errno=True)
        self.fd=c.inotify_init1(os.O_NONBLOCK|os.O_CLOEXEC)
        if self.fd<0:raise OSError(ctypes.get_errno(),'inotify_init1')
        self.ids={}
        try:
            for i,d in enumerate(dirs):
                wd=c.inotify_add_watch(self.fd,os.fsencode(d/filename),self.OPEN)
                if wd<0:raise OSError(ctypes.get_errno(),'inotify_add_watch')
                assert wd not in self.ids,'distinct archives alias one journal'
                self.ids[wd]=i
        except BaseException:self.close();raise
    def observed(self):
        ids=set()
        while True:
            try:block=os.read(self.fd,64*1024)
            except BlockingIOError:break
            pos=0
            while pos<len(block):
                wd,mask,_,length=self.EVENT.unpack_from(block,pos);pos+=self.EVENT.size+length
                if mask & self.OVERFLOW:raise RuntimeError('inotify overflow; cannot prove non-opens')
                if mask & self.OPEN:ids.add(self.ids[wd])
        return sorted(ids)
    def close(self):
        if self.fd>=0:os.close(self.fd);self.fd=-1

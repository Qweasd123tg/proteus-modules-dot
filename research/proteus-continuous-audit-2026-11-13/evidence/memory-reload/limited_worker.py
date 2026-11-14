"""Fault fixture: lower RLIMIT_FSIZE only in this isolated memory worker."""
import os, pathlib, resource, signal, sys

limit = int(pathlib.Path(sys.argv[1]).read_text())
soft, hard = resource.getrlimit(resource.RLIMIT_FSIZE)
resource.setrlimit(resource.RLIMIT_FSIZE, (limit, hard))
signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
os.execv(sys.argv[2], sys.argv[2:])

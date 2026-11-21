"""Build only synthetic valid PNG fixtures in an explicit scratch root."""
from pathlib import Path
import struct
import sys
import zlib

root=Path(sys.argv[1])
root.mkdir(parents=True,exist_ok=True)
def chunk(kind,data):
    return struct.pack(">I",len(data))+kind+data+struct.pack(">I",zlib.crc32(kind+data))
sig=b"\x89PNG\r\n\x1a\n"
def png(size,color):
    header=chunk(b"IHDR",struct.pack(">IIBBBBB",1,1,8,6,0,0,0))
    pixels=chunk(b"IDAT",zlib.compress(b"\0"+bytes(color),level=6))
    end=chunk(b"IEND",b"")
    text=b"Comment\0"+b"x"*(size-len(sig+header+pixels+end)-12-len(b"Comment\0"))
    image=sig+header+pixels+chunk(b"tEXt",text)+end
    assert len(image)==size
    return image
(root/"large.png").write_bytes(png(4*1024*1024,(25,40,85,255)))
(root/"second.png").write_bytes(png(1024*1024,(100,50,20,255)))

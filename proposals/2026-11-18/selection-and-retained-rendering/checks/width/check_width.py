"""Check known ordinary glyphs only, no private input or terminal/UI access."""
import ctypes, locale, pathlib, unicodedata as ud
locale.setlocale(locale.LC_CTYPE,"C.UTF-8")
libc=ctypes.CDLL(None)
wc=libc.wcswidth
wc.argtypes=[ctypes.c_wchar_p,ctypes.c_size_t]
wc.restype=ctypes.c_int
def cells(s):
    n=wc(s,len(s))
    # An independent small-corpus cross-check, not a production wcwidth algorithm.
    m=sum(0 if ud.combining(c) else (2 if ud.east_asian_width(c) in ('F','W') else 1) for c in s)
    assert n == m,(s,n,m)
    return n
f,t=pathlib.Path('width-output.txt').read_text().strip('\n').split('\n--tables--\n')
frame=f.splitlines()
edge=[cells(x[:-1]) for x in frame]
print('frame right border column, 0-based:',edge)
assert edge==[75,75,75,77,75,74,75],edge
rows=t.splitlines()
table=[cells(x[:x.index("target")]) for x in rows if "target" in x]
print('table next-column starts, 0-based:',table,'; header',cells(rows[0][:rows[0].index('slot')]))
assert table==[6,6,8,6,5]
print('Controls: ASCII, Cyrillic, precomposed accent align; Japanese +2, decomposed accent -1.')

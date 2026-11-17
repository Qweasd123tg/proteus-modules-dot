"""Compare three LTR examples on DejaVu 16px. Requires libharfbuzz, Pillow+RAQM, and DejaVu fonts. No Desktop window. Single horizontal run only."""
from ctypes import *
from PIL import ImageFont,Image,ImageDraw
hb=CDLL("libharfbuzz.so.0")
def fn(name,out,*ins):
 a=getattr(hb,name);a.restype=out;a.argtypes=ins;return a
P=c_void_p;U=c_uint;I=c_int;B=c_char_p
blob=fn('hb_blob_create_from_file_or_fail',P,B);face=fn('hb_face_create',P,P,U);font=fn('hb_font_create',P,P);ot=fn('hb_ot_font_set_funcs',None,P);scale=fn('hb_font_set_scale',None,P,I,I)
buf=fn('hb_buffer_create',P);add=fn('hb_buffer_add_utf8',None,P,B,I,U,I);guess=fn('hb_buffer_guess_segment_properties',None,P);do=fn('hb_shape',None,P,P,P,U);destroy=fn('hb_buffer_destroy',None,P)
class Info(Structure):_fields_=[('id',U),('mask',U),('cluster',U),('var1',U),('var2',U)]
class Pos(Structure):_fields_=[('dx',I),('dy',I),('x',I),('y',I),('var',U)]
infos=fn('hb_buffer_get_glyph_infos',POINTER(Info),P,POINTER(U));poss=fn('hb_buffer_get_glyph_positions',POINTER(Pos),P,POINTER(U))
def setup(path,sz): 
 f=font(face(blob(path.encode()),0));ot(f);scale(f,sz*64,sz*64);return f
def shape(f,s):
 b=buf(); u=s.encode(); add(b,u,len(u),0,len(u));guess(b);do(f,b,None,0);n=U();info=infos(b,byref(n));pos=poss(b,byref(n));g=[];pen=0
 for j in range(n.value):g.append((info[j].cluster,(pen+pos[j].x)/64));pen+=pos[j].dx
 destroy(b);return pen/64,g
def index(g,x,w,n):return None if x>=w else next((i for i,at in reversed(g) if at<=x),0)
def witness(f,text,room,start):
 w,g=shape(f,text);mark,_=shape(f,'…');a=max(0,room-mark);b=text.encode()
 i=index(g,w-a if start else a,w,len(b))
 if i is None:i=len(b) if start else 0
 cand='…'+b[i:].decode() if start else b[:i].decode()+'…'
 return w,mark,i,cand,shape(f,cand)[0]

if __name__ == '__main__':
    from pathlib import Path
    from PIL import features
    assert features.check_feature("raqm"), "Pillow RAQM required"
    fonts = Path("/usr/share/fonts/truetype/dejavu")
    for filename,label,room,left,expected,advance in [
        ("DejaVuSansMono.ttf","photos/2026.png",35,True,"…png",38.5625),
        ("DejaVuSansMono.ttf","src/components",62,True,"…onents",67.484375),
        ("DejaVuSans.ttf","Toolbox",24,False,"T…",25.78125),
    ]:
        path=str(fonts/filename)
        original,marker,offset,candidate,width=witness(setup(path,16),label,room,left)
        assert candidate==expected and abs(width-advance)<1e-5
        assert marker <= room < width
        raster_font=ImageFont.truetype(path,16,layout_engine=ImageFont.Layout.RAQM)
        image=Image.new("L",(int(width)+10,40))
        ImageDraw.Draw(image).text((0,0),candidate,font=raster_font,fill=255)
        outside=image.crop((room,0,image.width,image.height)); pixels=outside.tobytes()
        n=sum(coverage>0 for coverage in pixels); assert n>0
        print(f"{label} / {room}px -> {candidate} / {width}px; {n} nonzero pixels outside right edge")

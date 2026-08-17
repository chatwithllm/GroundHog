from PIL import Image, ImageDraw, ImageFont
import math, random, os, shutil
random.seed(5)
W,Hd=1280,720; FPS=20
def font(sz,hand=True):
    hs=["/System/Library/Fonts/Supplemental/Comic Sans MS Bold.ttf","/System/Library/Fonts/Supplemental/Comic Sans MS.ttf"]
    ss=["/System/Library/Fonts/Supplemental/Arial.ttf"]
    for p in (hs if hand else ss):
        try: return ImageFont.truetype(p,sz)
        except: pass
    return ImageFont.load_default()
LB=font(19);CAP=font(27,False)
INK=(45,45,55);BLUE=(47,91,208);RED=(192,57,43);GRN=(46,139,87);ORG=(207,138,28);PUR=(142,95,176);TEAL=(31,143,143);YEL=(224,178,30)
def jit(v=1.4): return random.uniform(-v,v)
def seg(a,b,n=None):
    d=math.hypot(b[0]-a[0],b[1]-a[1]); n=n or max(1,int(d//24)); o=[]
    for k in range(n+1):
        t=k/n; o.append((a[0]+(b[0]-a[0])*t+(0 if k==0 else jit()),a[1]+(b[1]-a[1])*t+(0 if k==0 else jit())))
    return o
def poly(pts,close=False):
    o=[];P=list(pts)+([pts[0]] if close else [])
    for i in range(len(P)-1): o+= (seg(P[i],P[i+1]) if i==0 else seg(P[i],P[i+1])[1:])
    return o
def arc(cx,cy,r,a0,a1,steps=16,j=1.2):
    o=[]
    for i in range(steps+1):
        a=math.radians(a0+(a1-a0)*i/steps); o.append((cx+r*math.cos(a)+random.uniform(-j,j),cy+r*math.sin(a)+random.uniform(-j,j)))
    return o
def circle(cx,cy,r): return arc(cx,cy,r,0,360,22)
def clen(p):
    s=0
    for i in range(len(p)-1): s+=math.hypot(p[i+1][0]-p[i][0],p[i+1][1]-p[i][1])
    return s
def reveal(dr,pts,f,c,w):
    if f<=0:return
    if f>=1: dr.line(pts,fill=c,width=w,joint="curve");return
    tot=clen(pts);tg=tot*f;acc=0;dw=[pts[0]]
    for i in range(len(pts)-1):
        s=math.hypot(pts[i+1][0]-pts[i][0],pts[i+1][1]-pts[i][1])
        if acc+s<=tg: dw.append(pts[i+1]);acc+=s
        else:
            r=(tg-acc)/s if s else 0;dw.append((pts[i][0]+(pts[i+1][0]-pts[i][0])*r,pts[i][1]+(pts[i+1][1]-pts[i][1])*r));break
    if len(dw)>1: dr.line(dw,fill=c,width=w,joint="curve")
def point_at(pts,f):
    if f<=0:return pts[0]
    if f>=1:return pts[-1]
    tot=clen(pts);tg=tot*f;acc=0
    for i in range(len(pts)-1):
        s=math.hypot(pts[i+1][0]-pts[i][0],pts[i+1][1]-pts[i][1])
        if acc+s>=tg:
            r=(tg-acc)/s if s else 0;return (pts[i][0]+(pts[i+1][0]-pts[i][0])*r,pts[i][1]+(pts[i+1][1]-pts[i][1])*r)
        acc+=s
    return pts[-1]
def draw_pen(dr,x,y,ink):
    dx,dy=32,-50
    dr.line([(x+3,y+4),(x+dx+3,y+dy+4)],fill=(0,0,0,60),width=16)
    dr.line([(x,y),(x+dx,y+dy)],fill=(55,58,66),width=14)
    cx,cy=x+int(dx*0.6),y+int(dy*0.6); dr.line([(cx,cy),(x+dx+7,y+dy-9)],fill=(200,70,60),width=11)
    a=math.atan2(-dy,-dx); dr.polygon([(x,y),(x+12*math.cos(a+0.5),y+12*math.sin(a+0.5)),(x+12*math.cos(a-0.5),y+12*math.sin(a-0.5))],fill=(30,30,36))
    dr.ellipse([x-4,y-4,x+4,y+4],fill=ink)
els=[]
def S(pts,c,w,t0,dur=0.6): els.append(dict(k='s',pts=pts,c=c,w=w,t0=t0,dur=dur))
def T(x,y,s,c,t0,anc="ma",f=LB): els.append(dict(k='t',x=x,y=y,s=s,c=c,f=f,t0=t0,anchor=anc))
def strokes(list_pts,c,w,t0,step=0.22,dur=0.5):
    for i,p in enumerate(list_pts): S(p,c,w,t0+i*step,dur)
    return t0+len(list_pts)*step
def ahead(a,b,c,t0):
    ang=math.atan2(b[1]-a[1],b[0]-a[0]);L=13
    S([(b[0]-L*math.cos(ang-0.5),b[1]-L*math.sin(ang-0.5)),b,(b[0]-L*math.cos(ang+0.5),b[1]-L*math.sin(ang+0.5))],c,3,t0,0.25)
def arrow(a,b,c,t0,dash=False):
    S(poly([a,b]),c,3,t0,0.5); ahead(a,b,c,t0+0.4)
# ---------- doodle icons ----------
def satellite(cx,cy,t0,c=INK):
    b=[poly([(cx-16,cy-12),(cx+16,cy-12),(cx+16,cy+12),(cx-16,cy+12)],True),
       poly([(cx-16,cy-8),(cx-46,cy-8),(cx-46,cy+8),(cx-16,cy+8)]),
       poly([(cx+16,cy-8),(cx+46,cy-8),(cx+46,cy+8),(cx+16,cy+8)]),
       seg((cx,cy-12),(cx,cy-26))]
    return strokes(b,c,3,t0,0.18)
def waves(cx,cy,t0,c,down=True,n=3):
    ps=[]
    for i in range(n):
        r=14+i*12
        ps.append(arc(cx,cy,r,55,125) if down else arc(cx,cy,r,235,305))
    return strokes(ps,c,3,t0,0.16,0.4)
def cloud(cx,cy,t0,c):
    ps=[arc(cx-24,cy,20,150,390),arc(cx,cy-10,24,150,390),arc(cx+26,cy,20,180,420),seg((cx-44,cy+16),(cx+46,cy+16))]
    return strokes(ps,c,3,t0,0.18)
def tripod(cx,cy,t0,c):
    ps=[arc(cx,cy,20,180,360),poly([(cx-20,cy),(cx+20,cy)]),seg((cx,cy),(cx-26,cy+70)),seg((cx,cy),(cx+26,cy+70)),seg((cx,cy),(cx,cy+72)),seg((cx,cy-20),(cx,cy-38))]
    return strokes(ps,c,3,t0,0.14)
def chip(cx,cy,w,h,t0,c):
    ps=[poly([(cx-w/2,cy-h/2),(cx+w/2,cy-h/2),(cx+w/2,cy+h/2),(cx-w/2,cy+h/2)],True)]
    for i in range(3):
        yy=cy-h/4+i*h/4; ps.append(seg((cx-w/2,yy),(cx-w/2-10,yy))); ps.append(seg((cx+w/2,yy),(cx+w/2+10,yy)))
    return strokes(ps,c,3,t0,0.1,0.35)
def battery(cx,cy,t0,c):
    ps=[poly([(cx-38,cy-22),(cx+38,cy-22),(cx+38,cy+22),(cx-38,cy+22)],True),poly([(cx+38,cy-9),(cx+48,cy-9),(cx+48,cy+9),(cx+38,cy+9)]),
        poly([(cx-6,cy-14),(cx-16,cy+2),(cx-2,cy+2),(cx-12,cy+18)])]  # bolt
    return strokes(ps,c,3,t0,0.16)
def wheel(cx,cy,r,t0,c):
    ps=[circle(cx,cy,r),circle(cx,cy,r*0.33)]
    for a in (0,60,120):
        ps.append(seg((cx+r*0.33*math.cos(math.radians(a)),cy+r*0.33*math.sin(math.radians(a))),(cx+r*math.cos(math.radians(a)),cy+r*math.sin(math.radians(a)))))
    return strokes(ps,c,3,t0,0.1,0.4)
def rover(t0):
    # body
    body=[poly([(500,320),(760,320),(775,360),(760,400),(500,400),(485,360)],True)]
    tt=strokes(body,INK,4,t0,0.25,0.7)
    S(seg((640,320),(640,272)),INK,3,tt,0.4); S(circle(640,266,9),GRN,3,tt+0.3,0.4)  # antenna
    w1=wheel(560,420,40,tt+0.4,INK); w2=wheel(710,420,40,tt+0.7,INK)
    T(630,360,"ROVER",(250,250,255),tt+1.0,"mm")
    return tt+1.1
# ---------- timeline ----------
b1=0.5
tt=rover(b1)
T(630,470,"(pool-cleaner reborn)",INK,tt+0.1,"ma")
b2=8.0
satellite(470,80,b2); satellite(770,70,b2+0.6)
waves(470,100,b2+0.9,ORG); waves(770,90,b2+0.9,ORG)
arrow((520,120),(632,258),ORG,b2+1.5,True); arrow((760,110),(650,258),ORG,b2+1.5,True)
T(620,45,"GNSS satellites",ORG,b2+0.3,"ma")
b3=15.0
tripod(150,190,b3,TEAL); T(150,290,"BASE",TEAL,b3+0.8,"ma")
cloud(150,360,b3+1.2,PUR); T(150,405,"NTRIP",PUR,b3+1.8,"ma")
chip(150,480,120,60,b3+2.2,RED); T(150,483,"Pi",RED,b3+2.8,"mm")
arrow((150,215),(150,335),TEAL,b3+1.0); arrow((150,388),(150,450),PUR,b3+2.0)
arrow((215,480),(490,375),RED,b3+3.2,True); T(340,435,"corrections",RED,b3+3.0,"ma")
b4=23.0
chip(1060,250,150,90,b4,BLUE); T(1060,240,"F405",BLUE,b4+0.7,"mm"); T(1060,268,"ArduRover",BLUE,b4+0.8,"mm")
arrow((980,290),(778,350),BLUE,b4+1.2)
T(900,300,"brain",BLUE,b4+1.0,"ma")
b5=31.0
chip(1060,430,150,80,b5,ORG); T(1060,423,"BLDC drv",ORG,b5+0.7,"mm")
arrow((985,440),(740,410),ORG,b5+1.2); T(880,405,"PWM+DIR",ORG,b5+1.0,"ma")
b6=38.0
battery(320,610-... if False else 560,b6,YEL) if False else battery(330,560,b6,YEL)
T(330,600,"24V pack",YEL,b6+0.7,"ma"); arrow((400,560),(495,405),YEL,b6+1.2)
b7=45.0
arrow((790,395),(940,395),GRN,b7); 
for i,x in enumerate((980,1040,1100)): S(circle(x,395,4),GRN,3,b7+0.4+i*0.2,0.3)
T(1030,360,"waypoints!",GRN,b7+0.6,"ma")
caps=[(0.5,8.0,"Meet the rover: a salvaged pool-cleaner, rebuilt to drive itself."),
 (8.0,15.0,"Overhead, GNSS satellites give it a rough position fix."),
 (15.0,23.0,"A base station + NTRIP caster stream cm-accurate corrections to its Pi."),
 (23.0,31.0,"A Radiolink F405 flight controller is the real-time brain."),
 (31.0,38.0,"It sends PWM + DIR straight to the BLDC wheel motors (built-in drivers)."),
 (38.0,45.0,"All powered by the salvaged 24-volt battery pack."),
 (45.0,52.0,"And off it goes - following GPS waypoints on its own!")]
DUR=52.0
base=Image.new("RGB",(W,Hd),(253,251,242)); bd=ImageDraw.Draw(base)
for x in range(0,W,44): bd.line([x,0,x,Hd],fill=(245,242,231))
for y in range(0,Hd,44): bd.line([0,y,W,y],fill=(245,242,231))
bd.rectangle([0,612,W,Hd],fill=(37,48,58))
def wrap(dr,s,f,mw):
    out=[];cur=""
    for w in s.split():
        if dr.textlength((cur+" "+w).strip(),font=f)<=mw: cur=(cur+" "+w).strip()
        else: out.append(cur);cur=w
    if cur:out.append(cur)
    return out
outdir="dframes";shutil.rmtree(outdir,ignore_errors=True);os.makedirs(outdir)
nf=int(DUR*FPS)
for fi in range(nf):
    t=fi/FPS; im=base.copy(); dr=ImageDraw.Draw(im,"RGBA")
    for e in els:
        if t<e['t0']:continue
        if e['k']=='s': reveal(dr,e['pts'],min(1,(t-e['t0'])/e['dur']),e['c'],e['w'])
        else:
            a=min(1,(t-e['t0'])/0.3); dr.text((e['x'],e['y']),e['s'],font=e['f'],fill=e['c']+(int(255*a),),anchor=e['anchor'])
    act=None
    for e in els:
        if e['k']=='s' and e['t0']<=t<e['t0']+e['dur']:
            if act is None or e['t0']>act['t0']: act=e
    if act and os.environ.get("PEN","1")!="0": px,py=point_at(act['pts'],(t-act['t0'])/act['dur']); draw_pen(dr,px,py,act['c'])
    for (c0,c1,s) in caps:
        if c0<=t<c1:
            fade=min(1,(t-c0)/0.4)*min(1,(c1-t)/0.4);a=int(255*max(0,fade))
            ls=wrap(dr,s,CAP,W-120);yy=636 if len(ls)>1 else 652
            for ln in ls: dr.text((W/2,yy),ln,font=CAP,fill=(240,238,230,a),anchor="ma");yy+=33
            break
    im.save(f"{outdir}/f{fi:04d}.png")
print("frames",nf)

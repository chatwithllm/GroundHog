from PIL import Image, ImageDraw, ImageFont
import math, random, os, shutil
random.seed(9)
W,Hd=1280,720; FPS=20
def font(sz,hand=True):
    hs=["/System/Library/Fonts/Supplemental/Comic Sans MS Bold.ttf","/System/Library/Fonts/Supplemental/Comic Sans MS.ttf"]
    ss=["/System/Library/Fonts/Supplemental/Arial.ttf"];sb=["/System/Library/Fonts/Supplemental/Arial Bold.ttf"]
    for p in (hs if hand else ss):
        try: return ImageFont.truetype(p,sz)
        except: pass
    return ImageFont.load_default()
BIG=font(58);SUB=font(26);LB=font(20);H2=font(40);STEPT=font(24);STEPD=font(18,False);CAP=font(26,False);NUM=font(22)
INK=(45,45,55);BLUE=(47,91,208);RED=(192,57,43);GRN=(46,139,87);ORG=(207,138,28);PUR=(142,95,176);TEAL=(31,143,143);YEL=(214,168,26)
def jit(v=1.4): return random.uniform(-v,v)
def seg(a,b,n=None):
    d=math.hypot(b[0]-a[0],b[1]-a[1]); n=n or max(1,int(d//24)); o=[]
    for k in range(n+1):
        t=k/n; o.append((a[0]+(b[0]-a[0])*t+(0 if k==0 else jit()),a[1]+(b[1]-a[1])*t+(0 if k==0 else jit())))
    return o
def poly(pts,close=False):
    o=[];P=list(pts)+([pts[0]] if close else [])
    for i in range(len(P)-1): o+=(seg(P[i],P[i+1]) if i==0 else seg(P[i],P[i+1])[1:])
    return o
def arc(cx,cy,r,a0,a1,steps=16,j=1.1):
    return [(cx+r*math.cos(math.radians(a0+(a1-a0)*i/steps))+random.uniform(-j,j),cy+r*math.sin(math.radians(a0+(a1-a0)*i/steps))+random.uniform(-j,j)) for i in range(steps+1)]
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
def draw_hand(dr,x,y,ink):
    dx,dy=42,-66; L=math.hypot(dx,dy); ux,uy=dx/L,dy/L; px,py=-uy,ux
    farx,fary=x+ux*175,y+uy*175
    dr.line([(x+4,y+5),(farx+4,fary+5)],fill=(0,0,0,55),width=19)
    dr.line([(x,y),(farx,fary)],fill=(60,63,72),width=15)
    cx,cy=x+ux*152,y+uy*152; dr.line([(cx,cy),(farx,fary)],fill=(200,70,60),width=15)
    a=math.atan2(-dy,-dx); dr.polygon([(x,y),(x+13*math.cos(a+0.5),y+13*math.sin(a+0.5)),(x+13*math.cos(a-0.5),y+13*math.sin(a-0.5))],fill=(30,30,36))
    dr.ellipse([x-4,y-4,x+4,y+4],fill=ink)
    skin=(240,203,168); sl=(182,141,108); sleeve=(54,108,186)
    sx,sy=x+ux*128,y+uy*128; dr.ellipse([sx-36,sy-32,sx+36,sy+32],fill=sleeve,outline=(40,80,150),width=3)
    hcx,hcy=x+ux*78,y+uy*78; dr.ellipse([hcx-48,hcy-42,hcx+48,hcy+46],fill=skin,outline=sl,width=3)
    thx,thy=hcx+px*32+ux*4,hcy+py*32+uy*4; dr.ellipse([thx-17,thy-14,thx+17,thy+14],fill=skin,outline=sl,width=2)
    for i in range(4):
        fx=hcx-ux*14+px*(-27+i*18); fy=hcy-uy*14+py*(-27+i*18); dr.line([(fx-ux*18,fy-uy*18),(fx+ux*10,fy+uy*10)],fill=sl,width=3)
els=[]; CUR=[1e9]
def scene(end): CUR[0]=end
def S(pts,c,w,t0,dur=0.6): els.append(dict(k='s',pts=pts,c=c,w=w,t0=t0,dur=dur,te=CUR[0]))
def T(x,y,s,c,t0,anc="ma",f=LB): els.append(dict(k='t',x=x,y=y,s=s,c=c,f=f,t0=t0,anchor=anc,te=CUR[0]))
def strokes(lp,c,w,t0,step=0.2,dur=0.5):
    for i,p in enumerate(lp): S(p,c,w,t0+i*step,dur)
    return t0+len(lp)*step
def ahead(a,b,c,t0):
    ang=math.atan2(b[1]-a[1],b[0]-a[0]);L=13
    S([(b[0]-L*math.cos(ang-0.5),b[1]-L*math.sin(ang-0.5)),b,(b[0]-L*math.cos(ang+0.5),b[1]-L*math.sin(ang+0.5))],c,3,t0,0.25)
def arrow(a,b,c,t0):
    S(poly([a,b]),c,3,t0,0.5); ahead(a,b,c,t0+0.4)
def under(x1,x2,y,c,t0): S(poly([(x1,y),(x2,y)]),c,4,t0,0.5)
# icons
def wheel(cx,cy,r,t0,c):
    ps=[circle(cx,cy,r),circle(cx,cy,r*0.33)]
    for a in (0,60,120): ps.append(seg((cx+r*0.33*math.cos(math.radians(a)),cy+r*0.33*math.sin(math.radians(a))),(cx+r*math.cos(math.radians(a)),cy+r*math.sin(math.radians(a)))))
    return strokes(ps,c,3,t0,0.1,0.4)
def rover(cx,cy,scale,t0,label=True):
    s=scale
    body=[poly([(cx-130*s,cy-40*s),(cx+130*s,cy-40*s),(cx+145*s,cy),(cx+130*s,cy+40*s),(cx-130*s,cy+40*s),(cx-145*s,cy)],True)]
    tt=strokes(body,INK,4,t0,0.25,0.7)
    S(seg((cx+10*s,cy-40*s),(cx+10*s,cy-88*s)),INK,3,tt,0.4); S(circle(cx+10*s,cy-96*s,9*s),GRN,3,tt+0.3,0.4)
    wheel(cx-70*s,cy+58*s,40*s,tt+0.4,INK); wheel(cx+80*s,cy+58*s,40*s,tt+0.7,INK)
    if label: T(cx,cy,"ROVER",(250,250,255),tt+1.0,"mm")
    return tt+1.1
def satellite(cx,cy,t0,c=INK):
    b=[poly([(cx-16,cy-12),(cx+16,cy-12),(cx+16,cy+12),(cx-16,cy+12)],True),poly([(cx-16,cy-8),(cx-46,cy-8),(cx-46,cy+8),(cx-16,cy+8)]),poly([(cx+16,cy-8),(cx+46,cy-8),(cx+46,cy+8),(cx+16,cy+8)]),seg((cx,cy-12),(cx,cy-26))]
    return strokes(b,c,3,t0,0.16)
def waves(cx,cy,t0,c,n=3):
    return strokes([arc(cx,cy,14+i*12,55,125) for i in range(n)],c,3,t0,0.15,0.4)
def cloud(cx,cy,t0,c):
    return strokes([arc(cx-24,cy,20,150,390),arc(cx,cy-10,24,150,390),arc(cx+26,cy,20,180,420),seg((cx-44,cy+16),(cx+46,cy+16))],c,3,t0,0.18)
def tripod(cx,cy,t0,c):
    return strokes([arc(cx,cy,20,180,360),poly([(cx-20,cy),(cx+20,cy)]),seg((cx,cy),(cx-26,cy+70)),seg((cx,cy),(cx+26,cy+70)),seg((cx,cy),(cx,cy+72)),seg((cx,cy-20),(cx,cy-38))],c,3,t0,0.14)
def chip(cx,cy,w,h,t0,c):
    ps=[poly([(cx-w/2,cy-h/2),(cx+w/2,cy-h/2),(cx+w/2,cy+h/2),(cx-w/2,cy+h/2)],True)]
    for i in range(3):
        yy=cy-h/4+i*h/4; ps+=[seg((cx-w/2,yy),(cx-w/2-10,yy)),seg((cx+w/2,yy),(cx+w/2+10,yy))]
    return strokes(ps,c,3,t0,0.1,0.35)
def battery(cx,cy,t0,c):
    return strokes([poly([(cx-38,cy-22),(cx+38,cy-22),(cx+38,cy+22),(cx-38,cy+22)],True),poly([(cx+38,cy-9),(cx+48,cy-9),(cx+48,cy+9),(cx+38,cy+9)]),poly([(cx-6,cy-14),(cx-16,cy+2),(cx-2,cy+2),(cx-12,cy+18)])],c,3,t0,0.16)
def check(cx,cy,t0,c=GRN):
    S(poly([(cx-10,cy),(cx-3,cy+9),(cx+12,cy-12)]),c,4,t0,0.35)
# ================= CHAPTERS =================
caps=[]
def cap(t0,t1,s): caps.append((t0,t1,s))
# --- S0 title ---
scene(5.0)
T(640,150,"POOL-ROBO  RTK",INK,0.4,"ma",BIG)
under(360,920,215,RED,1.4)
T(640,250,"how it works  -  a quick onboarding",TEAL,1.8,"ma",SUB)
rover(640,430,0.9,2.3,label=False)
cap(0.3,5.0,"A torn-down pool cleaner, rebuilt into an autonomous RTK-GPS rover.")
# --- S1 what it is ---
scene(18.0)
T(640,70,"THE  GOAL",INK,5.2,"ma",H2); under(500,780,92,ORG,5.7)
rover(640,300,1.0,6.0)
T(640,470,"drive itself to cm-accurate GPS waypoints",INK,8.2,"ma",SUB)
T(640,520,"(and later: mow the lawn)",PUR,9.2,"ma",LB)
cap(5.2,11.0,"The goal: a self-driving rover guided by centimeter-accurate RTK GPS.")
cap(11.0,18.0,"Reuse the robot's BLDC motors and 24V battery - add a brain and GPS.")
# --- S2 the build story ---
scene(33.0)
T(640,66,"WHAT  WE  CRACKED",INK,18.4,"ma",H2); under(430,850,88,BLUE,18.9)
story=[("Unlocked the read-protected MCU",GRN,19.5),("Ran our own firmware on it",GRN,21.0),
 ("Confirmed 24V is live on the board",GRN,22.5),("Internal motor bridges were gated shut",RED,24.0),
 ("So: BLDC motors (built-in drivers) + F405",BLUE,25.5)]
for i,(s,c,t0) in enumerate(story):
    y=150+i*72; 
    if c==RED: S(poly([(360,y),(378,y+16)]),RED,4,t0,0.2); S(poly([(378,y),(360,y+16)]),RED,4,t0+0.15,0.2)
    else: check(370,y+8,t0,c if c!=BLUE else BLUE)
    T(405,y-6,s,INK,t0+0.3,"la",STEPT)
cap(18.4,26.0,"We proved we could own the hardware - but its motor stage stayed locked.")
cap(26.0,33.0,"Decision: leave those bridges - command the BLDC motors from our own F405.")
# --- S3 how it works (architecture) ---
scene(73.0); A=33.5
T(640,60,"HOW  IT  WORKS",INK,A,"ma",H2); under(470,810,84,GRN,A+0.4)
ry=rover(560,430,0.85,A+0.8)
satellite(470,150,A+4.0); satellite(770,140,A+4.6); waves(470,170,A+4.9,ORG); waves(770,160,A+4.9,ORG)
arrow((520,190),(555,340),ORG,A+5.4); arrow((760,180),(600,340),ORG,A+5.4)
tripod(150,210,A+8.0,TEAL); T(150,305,"BASE",TEAL,A+8.8,"ma")
cloud(150,375,A+9.4,PUR); T(150,420,"NTRIP",PUR,A+10.0,"ma")
chip(150,500,120,58,A+10.6,RED); T(150,503,"Pi",RED,A+11.2,"mm")
arrow((150,232),(150,352),TEAL,A+9.2); arrow((150,402),(150,472),PUR,A+10.4); arrow((215,500),(435,430),RED,A+11.8)
chip(1070,250,150,86,A+14.5,BLUE); T(1070,242,"F405",BLUE,A+15.2,"mm"); T(1070,268,"ArduRover",BLUE,A+15.3,"mm")
arrow((992,290),(700,400),BLUE,A+16.0)
chip(1070,430,150,78,A+18.5,ORG); T(1070,424,"BLDC drv",ORG,A+19.2,"mm")
arrow((995,440),(660,470),ORG,A+19.8)
battery(300,560,A+22.0,YEL); T(300,600,"24V pack",YEL,A+22.7,"ma"); arrow((360,548),(470,470),YEL,A+23.2)
cap(A,A+8.0,"Overhead satellites + a base station give the rover a rough fix...")
cap(A+8.0,A+14.5,"...corrections flow through NTRIP to the onboard Raspberry Pi.")
cap(A+14.5,A+18.5,"An F405 flight controller (ArduRover) is the real-time brain.")
cap(A+18.5,A+22.0,"It sends PWM + DIR straight to the BLDC wheel motors.")
cap(A+22.0,73.0,"All powered by the salvaged 24-volt pack. FG feeds wheel speed back.")
# --- S4 getting started ---
scene(93.0)
T(640,60,"GETTING  STARTED",INK,73.4,"ma",H2); under(450,830,84,RED,73.9)
steps=[("1","Flash ArduRover","RadiolinkF405 target, via Mission Planner",74.5),
 ("2","Set Brushed-W-Relay","MOT_PWM_TYPE=3, assign DIR relay pins",76.2),
 ("3","Wire it up","24V->motor Red/Blk, F405 PWM+DIR->motor, FG back, common GND",77.9),
 ("4","Bench test (ESP32)","one motor: PWM D25, DIR D26, FG D27, wheels up",79.6),
 ("5","Add RTK + waypoints","LC29H + NTRIP -> autonomous missions",81.3)]
for (n,tt,dd,t0) in steps:
    i=int(n)-1; y=155+i*88
    S(circle(370,y,22),BLUE,3,t0,0.4); T(370,y,n,BLUE,t0+0.3,"mm",NUM)
    T(410,y-16,tt,INK,t0+0.5,"la",STEPT); T(410,y+8,dd,(90,90,100),t0+0.7,"la",STEPD)
cap(73.4,84.0,"Onboarding: five steps from parts on the bench to a rover that drives.")
cap(84.0,93.0,"Everything runs on gear already on hand - no new brain to buy.")
# --- S5 end ---
scene(1e9)
T(640,250,"READY  TO  ROLL",INK,93.4,"ma",BIG); under(400,880,315,GRN,94.4)
T(640,350,"diagrams, videos & docs  ->  /media  and  /docs",TEAL,95.0,"ma",SUB)
rover(640,500,0.8,95.6,label=False)
cap(93.4,99.0,"That's the build. Flash, wire, test - and send it down the yard.")
DUR=99.0
# base
base=Image.new("RGB",(W,Hd),(253,251,242)); bd=ImageDraw.Draw(base)
for x in range(0,W,44): bd.line([x,0,x,Hd],fill=(245,242,231))
for y in range(0,Hd,44): bd.line([0,y,W,y],fill=(245,242,231))
bd.rectangle([0,614,W,Hd],fill=(37,48,58))
def wrap(dr,s,f,mw):
    out=[];cur=""
    for w in s.split():
        if dr.textlength((cur+" "+w).strip(),font=f)<=mw: cur=(cur+" "+w).strip()
        else: out.append(cur);cur=w
    if cur:out.append(cur)
    return out
outdir="oframes";shutil.rmtree(outdir,ignore_errors=True);os.makedirs(outdir)
nf=int(DUR*FPS)
for fi in range(nf):
    t=fi/FPS; im=base.copy(); dr=ImageDraw.Draw(im,"RGBA")
    for e in els:
        if t<e['t0'] or t>=e['te']: continue
        # fade near scene end
        fade=1.0
        if e['te']<1e8 and e['te']-t<0.5: fade=max(0,(e['te']-t)/0.5)
        if e['k']=='s':
            reveal(dr,e['pts'],min(1,(t-e['t0'])/e['dur']),e['c']+((int(255*fade),) if fade<1 else ()),e['w']) if fade<1 else reveal(dr,e['pts'],min(1,(t-e['t0'])/e['dur']),e['c'],e['w'])
        else:
            a=min(1,(t-e['t0'])/0.3)*fade; dr.text((e['x'],e['y']),e['s'],font=e['f'],fill=e['c']+(int(255*a),),anchor=e['anchor'])
    act=None
    for e in els:
        if e['k']=='s' and e['t0']<=t<e['t0']+e['dur'] and t<e['te']:
            if act is None or e['t0']>act['t0']: act=e
    if act: hx,hy=point_at(act['pts'],(t-act['t0'])/act['dur']); draw_hand(dr,hx,hy,act['c'])
    for (c0,c1,s) in caps:
        if c0<=t<c1:
            fd=min(1,(t-c0)/0.4)*min(1,(c1-t)/0.4);a=int(255*max(0,fd))
            ls=wrap(dr,s,CAP,W-120);yy=636 if len(ls)>1 else 652
            for ln in ls: dr.text((W/2,yy),ln,font=CAP,fill=(240,238,230,a),anchor="ma");yy+=33
            break
    im.save(f"{outdir}/f{fi:04d}.png")
print("frames",nf)

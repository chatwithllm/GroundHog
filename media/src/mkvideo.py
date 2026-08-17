from PIL import Image, ImageDraw, ImageFont
import math, random, os, shutil
random.seed(11)
W,Hd=1280,720
FPS=20
def font(sz,hand=True):
    hs=["/System/Library/Fonts/Supplemental/Comic Sans MS Bold.ttf","/System/Library/Fonts/Supplemental/Comic Sans MS.ttf","/System/Library/Fonts/Chalkboard.ttc"]
    ss=["/System/Library/Fonts/Supplemental/Arial.ttf","/System/Library/Fonts/Helvetica.ttc"]
    for p in (hs if hand else ss):
        try: return ImageFont.truetype(p,sz)
        except: pass
    return ImageFont.load_default()
HD=font(30);TF=font(21);BF=font(15);LF=font(15);CAP=font(27,False);CAPb=font(27,False)
INK=(45,45,55);BLUE=(47,91,208);RED=(192,57,43);GRN=(46,139,87);ORG=(207,138,28);PUR=(142,95,176);TEAL=(31,143,143)
# --- geometry helpers (computed once) ---
def wobpts(pts,close=False,jit=1.5):
    o=list(pts)+([pts[0]] if close else []); out=[]
    for i in range(len(o)-1):
        a=o[i];b=o[i+1];dist=math.hypot(b[0]-a[0],b[1]-a[1]);n=max(1,int(dist//26))
        for k in range(n+1):
            t=k/n;x=a[0]+(b[0]-a[0])*t;y=a[1]+(b[1]-a[1])*t
            if not(i==0 and k==0): x+=random.uniform(-jit,jit);y+=random.uniform(-jit,jit)
            out.append((x,y))
    return out
def rectpts(x,y,w,h): return wobpts([(x,y),(x+w,y),(x+w,y+h),(x,y+h)],True)
def clen(pts):
    s=0
    for i in range(len(pts)-1): s+=math.hypot(pts[i+1][0]-pts[i][0],pts[i+1][1]-pts[i][1])
    return s
def reveal(dr,pts,f,color,w):
    if f<=0: return
    if f>=1: dr.line(pts,fill=color,width=w,joint="curve"); return
    total=clen(pts); target=total*f; acc=0; draw=[pts[0]]
    for i in range(len(pts)-1):
        seg=math.hypot(pts[i+1][0]-pts[i][0],pts[i+1][1]-pts[i][1])
        if acc+seg<=target: draw.append(pts[i+1]); acc+=seg
        else:
            r=(target-acc)/seg if seg else 0
            draw.append((pts[i][0]+(pts[i+1][0]-pts[i][0])*r,pts[i][1]+(pts[i+1][1]-pts[i][1])*r)); break
    if len(draw)>1: dr.line(draw,fill=color,width=w,joint="curve")
def point_at(pts,f):
    if f<=0: return pts[0]
    if f>=1: return pts[-1]
    total=clen(pts); target=total*f; acc=0
    for i in range(len(pts)-1):
        seg=math.hypot(pts[i+1][0]-pts[i][0],pts[i+1][1]-pts[i][1])
        if acc+seg>=target:
            r=(target-acc)/seg if seg else 0
            return (pts[i][0]+(pts[i+1][0]-pts[i][0])*r,pts[i][1]+(pts[i+1][1]-pts[i][1])*r)
        acc+=seg
    return pts[-1]
def draw_pen(dr,x,y,inkcol):
    # marker tip at (x,y); barrel goes up-right. shadow, barrel, cap, nib.
    dx,dy=34,-52
    dr.line([(x+3,y+4),(x+dx+3,y+dy+4)],fill=(0,0,0,60),width=17)      # shadow
    dr.line([(x,y),(x+dx,y+dy)],fill=(55,58,66),width=15)             # barrel
    dr.line([(x+int(dx*0.62),y+int(dy*0.62)),(x+dx,y+dy)],fill=(70,74,84),width=15)
    cx,cy=x+int(dx*0.62),y+int(dy*0.62)
    dr.line([(cx,cy),(x+dx+8,y+dy-10)],fill=(200,70,60),width=12)     # red cap
    # nib triangle pointing to tip
    ang=math.atan2(-dy,-dx)
    n=[(x,y),(x+13*math.cos(ang+0.5),y+13*math.sin(ang+0.5)),(x+13*math.cos(ang-0.5),y+13*math.sin(ang-0.5))]
    dr.polygon(n,fill=(30,30,36))
    dr.ellipse([x-4,y-4,x+4,y+4],fill=inkcol)                         # ink dot at tip
els=[]  # dict: kind, t0, dur, ...
def stroke(pts,color,w,t0,dur=0.7): els.append(dict(k='s',pts=pts,c=color,w=w,t0=t0,dur=dur))
def arrowhead(a,b,color,t0):
    ang=math.atan2(b[1]-a[1],b[0]-a[0]);L=13
    p=[(b[0]-L*math.cos(ang-0.5),b[1]-L*math.sin(ang-0.5)),b,(b[0]-L*math.cos(ang+0.5),b[1]-L*math.sin(ang+0.5))]
    els.append(dict(k='p',pts=p,c=color,w=3,t0=t0))
def txt(x,y,s,color,fnt,t0,anchor="la"):
    els.append(dict(k='t',x=x,y=y,s=s,c=color,f=fnt,t0=t0,anchor=anchor))
def box(x,y,w,h,color,title,lines,t0):
    stroke(rectpts(x,y,w,h),color,3,t0,0.8)
    txt(x+13,y+8,title,color,TF,t0+0.5)
    yy=y+40
    for ln in lines: txt(x+15,yy,ln,INK,BF,t0+0.6); yy+=19
def arrow(a,b,color,t0,label="",lcol=None,dash=False):
    pts=wobpts([a,b]); 
    if dash:
        # split into dashes as separate strokes revealed together
        stroke(pts,color,3,t0,0.6)
    else:
        stroke(pts,color,3,t0,0.6)
    arrowhead(a,b,color,t0+0.5)
    if label: 
        mx,my=(a[0]+b[0])/2,(a[1]+b[1])/2
        txt(mx,my-16,label,lcol or color,LF,t0+0.4,"ma")
# ---- timeline / layout ----
txt(40,20,"RTK Rover  ~  Architecture",INK,HD,0.2)
# enclosure
stroke(rectpts(300,120,965,455),(185,178,162),2,0.6,1.0)
txt(315,126,"~ ON THE ROBOT ~",(165,157,140),LF,1.2)
B=6.0  # base station beat
box(30,150,250,56,GRN,"GNSS BASE (LC29H)",["fixed, open sky"],B)
arrow((150,206),(150,240),INK,B+1.0,"RTCM3",RED)
box(30,240,250,52,TEAL,"NTRIP CASTER",["rtk2go / local"],B+1.6)
P=12.0
arrow((280,266),(320,210),INK,P+0.6,"internet",RED)
box(320,150,255,92,INK,"RASPBERRY Pi 4",["NTRIP client - RTCM","missions, logging"],P)
F=18.0
box(620,150,300,170,BLUE,"RADIOLINK F405 (ArduRover)",["EKF: IMU+RTK+FG","waypoint nav (L1)","skid-steer mixing","failsafe / e-stop"],F)
arrow((575,200),(620,210),BLUE,F+1.2,"MAVLink",BLUE)
G=25.0
box(30,330,250,60,GRN,"GNSS ROVER (LC29H)",["on vehicle - cm fix"],G)
arrow((280,360),(620,300),BLUE,G+1.2,"position (cm)",BLUE)
M=31.0
box(980,150,270,80,ORG,"BLDC DRIVE x2",["integrated driver","PWM+DIR in, FG out"],M)
arrow((920,235),(980,195),INK,M+1.0,"PWM+DIR",INK)
MO=37.0
box(980,265,270,48,INK,"LEFT BLDC motor",[],MO)
box(980,325,270,48,INK,"RIGHT BLDC motor",[],MO)
arrow((1050,230),(1060,265),RED,MO+0.8,"24V",RED)
arrow((1150,230),(1160,325),RED,MO+0.8,"",RED)
arrow((980,289),(920,280),GRN,MO+1.4,"FG (tacho)",GRN,True)
arrow((980,349),(920,300),GRN,MO+1.4,"",GRN,True)
PW=43.0
box(430,470,470,80,RED,"POWER  6S 24V + BMS",["24V->BLDC motors  24V-5V->F405/Pi","COMMON GROUND"],PW)
arrow((760,470),(760,320),RED,PW+1.0,"5V",RED)
arrow((880,470),(1050,230),RED,PW+1.0,"24V",RED)
arrow((560,470),(430,320),RED,PW+1.0,"5V",RED)
LP=49.0
arrow((1115,373),(1115,430),PUR,LP+0.4,"",PUR)
arrow((1115,430),(430,430),PUR,LP+0.8,"vehicle moves - new GPS pos",PUR,True)
arrow((430,430),(155,392),PUR,LP+1.2,"",PUR,True)
# captions (t0,t1,text)
caps=[(0.2,6.0,"A salvaged pool-cleaner robot, rebuilt into an autonomous RTK-GPS rover."),
 (6.0,12.0,"A fixed GNSS base station streams RTK correction data to an NTRIP caster."),
 (12.0,18.0,"On the robot, a Raspberry Pi pulls those corrections over the internet."),
 (18.0,25.0,"It relays them to a Radiolink F405 running ArduRover - the real-time brain."),
 (25.0,31.0,"The rover's GNSS locks a centimeter fix; the F405 fuses GPS, IMU and wheel-speed (FG)."),
 (31.0,37.0,"ArduRover mixes skid-steering and sends PWM + DIR to each motor."),
 (37.0,43.0,"BLDC motors with built-in drivers spin the wheels - FG feeds speed back."),
 (43.0,49.0,"Everything runs off the salvaged 6-cell 24-volt battery pack."),
 (49.0,56.0,"As it drives, position updates - closing the loop for autonomous waypoints.")]
DUR=56.0
# base paper
base=Image.new("RGB",(W,Hd),(253,251,242))
bd=ImageDraw.Draw(base)
for x in range(0,W,44): bd.line([x,0,x,Hd],fill=(245,242,231))
for y in range(0,Hd,44): bd.line([0,y,W,y],fill=(245,242,231))
bd.rectangle([0,610,W,Hd],fill=(37,48,58))
def wrap(dr,s,fnt,maxw):
    words=s.split();lines=[];cur=""
    for w in words:
        test=(cur+" "+w).strip()
        if dr.textlength(test,font=fnt)<=maxw: cur=test
        else: lines.append(cur);cur=w
    if cur:lines.append(cur)
    return lines
outdir="frames";shutil.rmtree(outdir,ignore_errors=True);os.makedirs(outdir)
nf=int(DUR*FPS)
for fi in range(nf):
    t=fi/FPS
    im=base.copy();dr=ImageDraw.Draw(im,"RGBA")
    for e in els:
        if t<e['t0']:continue
        if e['k']=='s':
            f=min(1,(t-e['t0'])/e['dur']); reveal(dr,e['pts'],f,e['c'],e['w'])
        elif e['k']=='p':
            a=min(1,(t-e['t0'])/0.3); col=e['c']+(int(255*a),); dr.line(e['pts'],fill=col,width=e['w'],joint="curve")
        elif e['k']=='t':
            a=min(1,(t-e['t0'])/0.3); col=e['c']+(int(255*a),)
            dr.text((e['x'],e['y']),e['s'],font=e['f'],fill=col,anchor=e['anchor'])
    # pen following the active stroke
    active=None
    for e in els:
        if e['k']=='s' and e['t0']<=t<e['t0']+e['dur']:
            if active is None or e['t0']>active['t0']: active=e
    if active is not None and os.environ.get("PEN","1")!="0":
        f=(t-active['t0'])/active['dur']
        px,py=point_at(active['pts'],f)
        draw_pen(dr,px,py,active['c'])
    # caption
    for (c0,c1,s) in caps:
        if c0<=t<c1:
            fade=min(1,(t-c0)/0.4)*min(1,(c1-t)/0.4);a=int(255*max(0,fade))
            lines=wrap(dr,s,CAP,W-120);yy=635 if len(lines)>1 else 650
            for ln in lines:
                dr.text((W/2,yy),ln,font=CAP,fill=(240,238,230,a),anchor="ma");yy+=34
            break
    im.save(f"{outdir}/f{fi:04d}.png")
print("frames",nf)

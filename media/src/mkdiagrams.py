#!/usr/bin/env python3
"""Generate the 3 static architecture PNGs for Pool-Robo RTK (BLDC direct-drive).
Outputs: media/diagrams/architecture.png, complete_flow.png, arch_handdrawn.png
Run: python3 mkdiagrams.py
"""
import os, math, random
from PIL import Image, ImageDraw, ImageFont

random.seed(7)
OUT = os.path.join(os.path.dirname(__file__), "..", "diagrams")
os.makedirs(OUT, exist_ok=True)

BG   = (15, 20, 27)
PANEL= (22, 29, 39)
LINE = (38, 49, 63)
INK  = (231, 237, 243)
MUT  = (142, 161, 180)
ACC  = (76, 196, 224)     # cyan
# net colors
C24  = (230, 25, 75)      # 24V
C5   = (245, 130, 49)     # 5V
CGND = (122, 135, 151)    # GND
CPWM = (67, 99, 216)      # PWM
CDIR = (240, 50, 230)     # DIR
CFG  = (15, 138, 138)     # FG
CGPS = (47, 158, 68)      # GPS/RTK
CUSB = (11, 165, 196)     # MAVLink

def font(sz, bold=False):
    paths = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, sz)
    return ImageFont.load_default()

def mono(sz):
    for p in ["/System/Library/Fonts/Menlo.ttc","/System/Library/Fonts/Monaco.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"]:
        if os.path.exists(p):
            return ImageFont.truetype(p, sz)
    return font(sz)

F_T  = font(24, True)
F_B  = font(19, True)
F_P  = mono(15)
F_S  = mono(13)
F_H  = font(34, True)

def tsize(d, t, f):
    b = d.textbbox((0,0), t, font=f); return b[2]-b[0], b[3]-b[1]

def box(d, x, y, w, h, title, lines, border=ACC, dashed=False, hand=False):
    if hand:
        rrect_hand(d, x, y, w, h, PANEL, border, 2)
    else:
        d.rounded_rectangle([x, y, x+w, y+h], 12, fill=PANEL, outline=border, width=2)
    d.text((x+14, y+10), title, font=F_B, fill=INK)
    yy = y+40
    for ln in lines:
        d.text((x+14, yy), ln, font=F_P, fill=MUT); yy += 20
    return (x, y, w, h)

def jitter_line(d, p1, p2, color, w=3, seg=14, amp=1.8):
    (x1,y1),(x2,y2)=p1,p2
    dist=math.hypot(x2-x1,y2-y1); n=max(2,int(dist/seg))
    pts=[]
    for i in range(n+1):
        t=i/n; x=x1+(x2-x1)*t; y=y1+(y2-y1)*t
        if 0<i<n: x+=random.uniform(-amp,amp); y+=random.uniform(-amp,amp)
        pts.append((x,y))
    d.line(pts, fill=color, width=w, joint="curve")

def rrect_hand(d, x, y, w, h, fill, outline, wdt):
    d.rounded_rectangle([x,y,x+w,y+h], 12, fill=fill)
    corners=[(x,y),(x+w,y),(x+w,y+h),(x,y+h),(x,y)]
    for i in range(4):
        jitter_line(d, corners[i], corners[i+1], outline, wdt, 16, 1.6)

def arrow(d, p1, p2, color, w=3, label=None, lf=F_S, hand=False, dash=False):
    (x1,y1),(x2,y2)=p1,p2
    if hand:
        jitter_line(d, p1, p2, color, w)
    elif dash:
        dash_line(d, p1, p2, color, w)
    else:
        d.line([p1,p2], fill=color, width=w)
    ang=math.atan2(y2-y1, x2-x1); a=10
    d.polygon([(x2,y2),
               (x2-a*math.cos(ang-0.5), y2-a*math.sin(ang-0.5)),
               (x2-a*math.cos(ang+0.5), y2-a*math.sin(ang+0.5))], fill=color)
    if label:
        mx,my=(x1+x2)/2,(y1+y2)/2
        tw,th=tsize(d,label,lf)
        d.rectangle([mx-tw/2-4,my-th/2-3,mx+tw/2+4,my+th/2+3], fill=BG)
        d.text((mx-tw/2,my-th/2-1), label, font=lf, fill=color)

def dash_line(d, p1, p2, color, w=3, on=9, off=6):
    (x1,y1),(x2,y2)=p1,p2; dist=math.hypot(x2-x1,y2-y1);
    if dist==0: return
    ux,uy=(x2-x1)/dist,(y2-y1)/dist; s=0
    while s<dist:
        e=min(s+on,dist)
        d.line([(x1+ux*s,y1+uy*s),(x1+ux*e,y1+uy*e)], fill=color, width=w); s=e+off

def header(d, W, title, sub):
    d.text((40, 26), title, font=F_H, fill=INK)
    d.text((42, 70), sub, font=F_P, fill=ACC)

def legend(d, x, y, items):
    d.text((x, y-24), "LEGEND", font=F_S, fill=MUT)
    for i,(c,t) in enumerate(items):
        yy=y+i*22
        d.line([(x,yy+7),(x+26,yy+7)], fill=c, width=4)
        d.text((x+34, yy), t, font=F_S, fill=INK)

# ---------- architecture.png : clean block diagram ----------
def build_architecture(hand=False, path="architecture.png", title="Pool-Robo RTK — Architecture"):
    W,H=1400,880
    img=Image.new("RGB",(W,H),BG); d=ImageDraw.Draw(img)
    header(d, W, title, "salvaged pool-cleaner → autonomous RTK ground rover  ·  BLDC direct-drive")
    # nodes
    base = box(d, 40, 150, 210, 70, "GNSS BASE", ["RTCM3 corrections"], CGPS, hand=hand)
    ntrip= box(d, 40, 270, 210, 70, "NTRIP CASTER", ["over internet"], CGPS, hand=hand)
    pi   = box(d, 300, 210, 250, 120, "RASPBERRY Pi 4", ["+ LC29H RTK HAT (GPS)","NTRIP client → RTCM","fix → F405 (MAVLink)"], ACC, dashed=True, hand=hand)
    fc   = box(d, 620, 200, 260, 150, "RADIOLINK F405", ["ArduPilot ArduRover","brushed-with-relay ×2","fuse GPS+IMU+FG","skid-steer + waypoints"], ACC, hand=hand)
    lm   = box(d, 960, 108, 240, 80, "LEFT MOTOR (BLDC)", ["drive","24V·GND·PWM·DIR·FG"], C24, hand=hand)
    rm   = box(d, 960, 202, 240, 80, "RIGHT MOTOR (BLDC)", ["drive","24V·GND·PWM·DIR·FG"], C24, hand=hand)
    bl   = box(d, 960, 296, 240, 82, "BLADE MOTOR (BLDC)", ["mower cutter","24V(relay+e-stop)·PWM·FG"], CDIR, hand=hand)
    pack = box(d, 300, 480, 250, 110, "6S 24V PACK", ["salvaged board (whole)","charges via board","= power + motor mounts"], C24, hand=hand)
    ubec = box(d, 620, 490, 240, 88, "UBEC 24V→5V", ["5V → F405","5V → Pi"], C5, hand=hand)
    esp  = box(d, 620, 618, 300, 74, "ESP32 (bench spin test)", ["PWM D25 · DIR D26 · FG D27"], MUT, dashed=True, hand=hand)

    # data/control flow
    arrow(d, (250,185),(300,240), CGPS, 3, "RTCM", hand=hand)
    arrow(d, (250,305),(300,290), CGPS, 3, "internet", hand=hand)
    arrow(d, (550,320),(620,336), CUSB, 3, "USB / MAVLink", hand=hand)
    arrow(d, (884,232),(960,148), CPWM, 3, None, hand=hand)          # PWM+DIR L
    arrow(d, (884,255),(960,240), CPWM, 3, "PWM+DIR", hand=hand)     # PWM+DIR R (label)
    arrow(d, (884,320),(960,332), CDIR, 3, "PWM (blade)", hand=hand) # blade speed/on-off
    arrow(d, (960,172),(884,242), CFG, 3, None, hand=hand)           # FG L
    arrow(d, (960,268),(884,300), CFG, 3, "FG", hand=hand)           # FG R
    # power
    arrow(d, (545,530),(620,530), C24, 4, "24V", hand=hand)          # pack->ubec
    arrow(d, (740,490),(740,350), C5, 3, "5V", hand=hand)            # ubec->fc
    arrow(d, (620,540),(430,300), C5, 3, "5V→Pi", hand=hand, dash=True)
    arrow(d, (505,480),(1080,198), C24, 3, "24V → drive motors", hand=hand, dash=True)
    arrow(d, (525,490),(1080,338), C24, 3, "24V → blade (relay+e-stop)", hand=hand, dash=True)

    legend(d, 40, 470, [(C24,"24V power"),(C5,"5V power"),(CPWM,"PWM+DIR (drive)"),
                        (CDIR,"blade control"),(CFG,"FG (speed feedback)"),(CUSB,"MAVLink"),(CGPS,"RTK / NTRIP")])
    d.text((40, H-34), "3 BLDC motors, each with its own driver: 2 drive + 1 blade. FG replaces wheel encoders. Blade on independent relay/e-stop.", font=F_P, fill=MUT)
    img.save(os.path.join(OUT, path)); print("wrote", path)

# ---------- complete_flow.png : layered flow ----------
def build_flow():
    W,H=1400,900
    img=Image.new("RGB",(W,H),BG); d=ImageDraw.Draw(img)
    header(d, W, "Pool-Robo RTK — Complete Flow", "corrections → navigation loop → drive → feedback")
    lanes=[("CORRECTIONS",120),("POSITIONING",300),("BRAIN",480),("DRIVE",660)]
    for name,y in lanes:
        d.line([(30,y-30),(W-30,y-30)], fill=LINE, width=1)
        d.text((36,y-24), name, font=F_S, fill=MUT)
    base = box(d, 40, 120, 200, 66, "GNSS BASE", ["RTCM3"], CGPS)
    ntrip= box(d, 300, 120, 200, 66, "NTRIP CASTER", ["internet"], CGPS)
    pi   = box(d, 560, 300, 260, 110, "Pi 4 + LC29H HAT", ["NTRIP client","cm RTK fix","→ MAVLink GPS_INPUT"], ACC, dashed=True)
    fc   = box(d, 560, 480, 260, 120, "F405 · ArduRover", ["EKF: GPS+IMU+FG","skid-steer mix","waypoint nav"], ACC)
    lm   = box(d, 720, 640, 190, 88, "LEFT BLDC", ["drive","24V·PWM·DIR·FG"], C24)
    rm   = box(d, 955, 640, 190, 88, "RIGHT BLDC", ["drive","24V·PWM·DIR·FG"], C24)
    bl   = box(d, 1190, 640, 185, 88, "BLADE BLDC", ["cutter · relay","24V·PWM·FG"], CDIR)
    pack = box(d, 40, 640, 200, 88, "6S 24V PACK", ["+ board charge","24V rail"], C24)
    ubec = box(d, 270, 640, 190, 88, "UBEC 5V", ["→ F405, Pi"], C5)
    arrow(d, (240,153),(300,153), CGPS, 3, "RTCM")
    arrow(d, (400,186),(650,300), CGPS, 3, "corrections")
    arrow(d, (690,410),(690,480), CUSB, 3, "fix (MAVLink)")
    arrow(d, (690,600),(800,640), CPWM, 3, "PWM+DIR")
    arrow(d, (810,560),(1040,640), CPWM, 3, None)
    arrow(d, (815,585),(1270,640), CDIR, 3, "blade PWM")
    arrow(d, (880,640),(760,600), CFG, 3, "FG")
    arrow(d, (240,684),(270,684), C24, 4, "24V")
    arrow(d, (400,640),(560,600), C5, 3, "5V")
    arrow(d, (250,705),(720,695), C24, 3, "24V → drive", dash=True)
    arrow(d, (300,715),(1190,700), C24, 3, "24V → blade (relay)", dash=True)
    legend(d, 900, 300, [(C24,"24V"),(C5,"5V"),(CPWM,"PWM+DIR"),(CDIR,"blade"),(CFG,"FG"),(CUSB,"MAVLink"),(CGPS,"RTK/NTRIP")])
    img.save(os.path.join(OUT,"complete_flow.png")); print("wrote complete_flow.png")

if __name__=="__main__":
    build_architecture(hand=False, path="architecture.png")
    build_flow()
    build_architecture(hand=True, path="arch_handdrawn.png", title="RTK Rover — Architecture (sketch)")
    print("done")

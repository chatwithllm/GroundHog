#!/usr/bin/env python3
"""Clean 3-motor C6 wiring: 3 BLDC + BSS138 8-ch + XIAO ESP32-C6 + 24V. Parallel FG/DIR buses.
-> media/diagrams/c6_wiring.png"""
import os
from PIL import Image, ImageDraw, ImageFont
OUT=os.path.join(os.path.dirname(__file__),"..","diagrams")
BG=(15,20,27); PANEL=(24,32,43); INK=(233,239,245); MUT=(150,168,184); ACC=(76,196,224)
RED=(230,60,60); BLK=(92,97,107); BLUE=(70,135,230); YEL=(232,200,45); GRN=(45,195,120); PUR=(180,120,235); WARN=(240,175,60)
def font(s,b=False):
    for p in [("/System/Library/Fonts/Supplemental/Arial Bold.ttf" if b else "/System/Library/Fonts/Supplemental/Arial.ttf"),
              ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if b else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")]:
        if os.path.exists(p): return ImageFont.truetype(p,s)
    return ImageFont.load_default()
def mono(s):
    for p in ["/System/Library/Fonts/Menlo.ttc","/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"]:
        if os.path.exists(p): return ImageFont.truetype(p,s)
    return font(s)
FT=font(26,True); FB=font(16,True); FP=mono(14); FS=mono(12)
W,H=1720,1160
img=Image.new("RGB",(W,H),BG); d=ImageDraw.Draw(img)
d.text((34,20),"3-Motor Wiring — XIAO ESP32-C6 + BSS138 (8-ch)   ·  3× FG green + 3× DIR yellow through the shifter, parallel",font=FT,fill=INK)
d.text((36,54),"PWM (blue) = 3.3V direct. DIR (yellow) = C6→shifter→motor. FG (green) = motor→shifter→C6. Reds=24V, blacks=common GND.",font=FP,fill=MUT)

def box(x,y,w,h,title,color=ACC):
    d.rounded_rectangle([x,y,x+w,y+h],11,fill=PANEL,outline=color,width=2); d.text((x+11,y+8),title,font=FB,fill=INK)
def dot(p,c): d.ellipse([p[0]-5,p[1]-5,p[0]+5,p[1]+5],fill=c,outline=(230,230,230))
def wire(p1,p2,c,w=4): d.line([p1,p2],fill=c,width=w)
def elbow(p1,p2,c,w=4):  # 2-seg orthogonal (horizontal then vertical)
    d.line([p1,(p2[0],p1[1])],fill=c,width=w); d.line([(p2[0],p1[1]),p2],fill=c,width=w)
def tag(x,y,t,c):
    d.rectangle([x-1,y-1,x+len(t)*7,y+12],fill=BG); d.text((x,y),t,font=FS,fill=c)

# ---- ESP32-C6 (right) ----
ex=1300; box(ex,110,240,780,"XIAO ESP32-C6")
# C6 pins (left edge) with the used mapping
C6=[('D0',150,'L-PWM'),('D3',185,'R-PWM'),('D8',220,'B-PWM'),
    ('D1',300,'L-DIR'),('D4',335,'R-DIR'),('D9',370,'B-DIR'),
    ('D2',450,'L-FG'),('D5',485,'R-FG'),('D10',520,'B-FG'),
    ('3V3',640,'→LV'),('5V',675,'→HV'),('GND',760,'common')]
C6P={}
for name,yy,lbl in C6:
    dot((ex,yy),ACC); d.text((ex+14,yy-8),name,font=FP,fill=INK); d.text((ex+70,yy-7),lbl,font=FS,fill=MUT); C6P[name]=(ex,yy)

# ---- BSS138 shifter (middle) ----
sx=760; box(sx,110,220,780,"BSS138  8-channel")
# HV pins (left) / LV pins (right); 6 channels + refs + GND
ch=[('1',210,'L-DIR',YEL),('2',260,'L-FG',GRN),('3',360,'R-DIR',YEL),('4',410,'R-FG',GRN),('5',510,'B-DIR',YEL),('6',560,'B-FG',GRN)]
HV={}; LV={}
dot((sx,160),PUR); d.text((sx+8,152),'HV←5V',font=FS,fill=MUT)
dot((sx+220,160),PUR); d.text((sx+220-46,152),'LV←3V3',font=FS,fill=MUT)
for c,yy,sig,col in ch:
    dot((sx,yy),col); d.text((sx+8,yy-8),'HV'+c,font=FS,fill=col); HV[c]=(sx,yy)
    dot((sx+220,yy),col); d.text((sx+220-32,yy-8),'LV'+c,font=FS,fill=col); LV[c]=(sx+220,yy)
    d.text((sx+52,yy-8),sig,font=FS,fill=MUT)
dot((sx,700),MUT); d.text((sx+8,692),'GND',font=FS,fill=MUT)

# ---- 3 motors (left) ----
def motor(y,name):
    box(40,y,210,150,name)
    st={'PWM':(BLUE,y+40),'CW/CCW':(YEL,y+70),'FG':(GRN,y+100),'VCC':(RED,y+125),'GND':(BLK,y+143)}
    for k,(c,yy) in st.items():
        dot((250,yy),c); d.text((120,yy-8),k,font=FS,fill=c if c!=BLK else MUT)
    return {k:(250,v[1]) for k,v in st.items()}
LM=motor(120,'LEFT MOTOR'); RM=motor(470,'RIGHT MOTOR'); BM=motor(830,'BLADE MOTOR')
motors=[('L',LM,'1','2','D0','D1','D2'),('R',RM,'3','4','D3','D4','D5'),('B',BM,'5','6','D8','D9','D10')]

# ---- wires ----
for pre,M,cd,cf,pwm,dpin,fpin in motors:
    # PWM direct: motor -> C6 pin (route above shifter via top lane)
    lane={'L':96,'R':100,'B':104}[pre]
    wire(M['PWM'],(lane, M['PWM'][1]),BLUE); wire((lane,M['PWM'][1]),(lane,138),BLUE); wire((lane,138),(1290,138),BLUE)
    wire((1290,138),(1290,C6P[pwm][1]),BLUE); wire((1290,C6P[pwm][1]),C6P[pwm],BLUE)
    tag(300,M['PWM'][1]-16,pre+'-PWM→'+pwm,BLUE)
    # DIR: motor CW/CCW -> HV(ch) ; LV(ch) -> C6
    elbow(M['CW/CCW'],HV[cd],YEL); tag(300,M['CW/CCW'][1]-16,pre+'-DIR→HV'+cd,YEL)
    elbow(LV[cd],C6P[dpin],YEL); tag(1000,LV[cd][1]-16,'LV'+cd+'→'+dpin,YEL)
    # FG: motor FG -> HV(ch) ; LV(ch) -> C6
    elbow(M['FG'],HV[cf],GRN); tag(300,M['FG'][1]+4,pre+'-FG→HV'+cf,GRN)
    elbow(LV[cf],C6P[fpin],GRN); tag(1000,LV[cf][1]+4,'LV'+cf+'→'+fpin,GRN)

# shifter refs
elbow(C6P['3V3'],(sx+220,160),PUR); tag(1010,150,'3V3→LV',PUR)
elbow(C6P['5V'],(sx,160),PUR)

# power rail
gy=980
d.line([(90,gy),(1560,gy)],fill=MUT,width=4); d.text((94,gy+8),"COMMON GROUND  ·  pack −  ·  3 motor blacks  ·  C6 GND  ·  shifter GND",font=FS,fill=MUT)
box(40,1010,210,120,"6S 24V PACK",RED); d.text((60,1052),"+24V",font=FP,fill=RED); d.text((60,1078),"GND (−)",font=FP,fill=MUT)
for pre,M,cd,cf,pwm,dpin,fpin in motors:
    wire(M['VCC'],(300+({'L':0,'R':16,'B':32}[pre]),M['VCC'][1]),RED)
    xr=300+({'L':0,'R':16,'B':32}[pre]); wire((xr,M['VCC'][1]),(xr,1050),RED); wire((xr,1050),(170,1050),RED)
    wire(M['GND'],(280,M['GND'][1]),BLK); wire((280,M['GND'][1]),(280,gy),BLK)
wire(C6P['GND'],(1270,C6P['GND'][1]),ACC); wire((1270,C6P['GND'][1]),(1270,gy),ACC)
wire((sx,700),(sx,gy),MUT)
wire((150,1122),(150,gy),MUT)
d.text((40,1140),"Left=ch1/ch2 · Right=ch3/ch4 · Blade=ch5/ch6.  Each motor's DIR+FG run parallel into adjacent shifter channels.",font=FS,fill=WARN)
img.save(os.path.join(OUT,"c6_wiring.png")); print("wrote",img.size)

#!/usr/bin/env python3
"""Clean 2-motor C6 test wiring: L+R BLDC + BSS138 (4-ch) + XIAO ESP32-C6 + 24V. Spacious/crisp.
-> media/diagrams/c6_2motor_wiring.png"""
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
FT=font(26,True); FB=font(17,True); FP=mono(15); FS=mono(14)
W,H=1560,820
img=Image.new("RGB",(W,H),BG); d=ImageDraw.Draw(img)
d.text((34,20),"2-Motor Test — XIAO ESP32-C6 + BSS138 (4-ch)",font=FT,fill=INK)
d.text((36,54),"PWM (blue)=3.3V direct. DIR (yellow) & FG (green) via shifter. Reds=24V, blacks=common GND. Blade waits for 8-ch.",font=FP,fill=MUT)

def box(x,y,w,h,title,color=ACC): d.rounded_rectangle([x,y,x+w,y+h],11,fill=PANEL,outline=color,width=2); d.text((x+12,y+9),title,font=FB,fill=INK)
def dot(p,c): d.ellipse([p[0]-6,p[1]-6,p[0]+6,p[1]+6],fill=c,outline=(230,230,230))
def wire(p1,p2,c,w=5): d.line([p1,p2],fill=c,width=w)
def elbow(p1,p2,c,w=5): d.line([p1,(p2[0],p1[1])],fill=c,width=w); d.line([(p2[0],p1[1]),p2],fill=c,width=w)
def tag(x,y,t,c): d.rectangle([x-2,y-2,x+len(t)*8,y+15],fill=BG); d.text((x,y),t,font=FS,fill=c)

# C6 (right)
ex=1250; box(ex,110,250,560,"XIAO ESP32-C6")
C6=[('D0',160,'L-PWM'),('D3',210,'R-PWM'),('D1',300,'L-DIR'),('D4',350,'R-DIR'),
    ('D2',440,'L-FG'),('D5',490,'R-FG'),('3V3',580,'→LV'),('5V',620,'→HV'),('GND',655,'common')]
C6P={}
for n,yy,lb in C6: dot((ex,yy),ACC); d.text((ex+16,yy-8),n,font=FP,fill=INK); d.text((ex+74,yy-7),lb,font=FS,fill=MUT); C6P[n]=(ex,yy)

# Shifter (middle)
sx=680; box(sx,150,230,420,"BSS138  (4-ch used)")
chs=[('1',230,'L-DIR',YEL),('2',300,'L-FG',GRN),('3',400,'R-DIR',YEL),('4',470,'R-FG',GRN)]
HV={}; LV={}
dot((sx,200),PUR); d.text((sx+10,192),'HV←5V',font=FS,fill=MUT)
dot((sx+230,200),PUR); d.text((sx+230-48,192),'LV←3V3',font=FS,fill=MUT)
for c,yy,sig,col in chs:
    dot((sx,yy),col); d.text((sx+10,yy-8),'HV'+c,font=FS,fill=col); HV[c]=(sx,yy)
    dot((sx+230,yy),col); d.text((sx+230-34,yy-8),'LV'+c,font=FS,fill=col); LV[c]=(sx+230,yy)
    d.text((sx+58,yy-8),sig,font=FS,fill=MUT)
dot((sx,540),MUT); d.text((sx+10,532),'GND',font=FS,fill=MUT)

# Motors (left)
def motor(y,name):
    box(40,y,230,170,name)
    st={'PWM':(BLUE,y+45),'CW/CCW':(YEL,y+80),'FG':(GRN,y+115),'VCC':(RED,y+145),'GND':(BLK,y+163)}
    for k,(c,yy) in st.items(): dot((270,yy),c); d.text((130,yy-8),k,font=FS,fill=c if c!=BLK else MUT)
    return {k:(270,v[1]) for k,v in st.items()}
LM=motor(120,'LEFT MOTOR'); RM=motor(480,'RIGHT MOTOR')
motors=[('L',LM,'1','2','D0','D1','D2',108),('R',RM,'3','4','D3','D4','D5',115)]

for pre,M,cd,cf,pwm,dpin,fpin,lane in motors:
    # PWM direct: motor -> C6 (top lane, over the shifter)
    wire(M['PWM'],(lane,M['PWM'][1]),BLUE); wire((lane,M['PWM'][1]),(lane,135),BLUE); wire((lane,135),(1235,135),BLUE); wire((1235,135),(1235,C6P[pwm][1]),BLUE); wire((1235,C6P[pwm][1]),C6P[pwm],BLUE)
    tag(320,M['PWM'][1]-18,pre+'-PWM → '+pwm,BLUE)
    # DIR: motor -> HV(ch) ; LV(ch) -> C6
    elbow(M['CW/CCW'],HV[cd],YEL); tag(320,M['CW/CCW'][1]-18,pre+'-DIR → HV'+cd,YEL)
    elbow(LV[cd],C6P[dpin],YEL); tag(960,LV[cd][1]-18,'LV'+cd+' → '+dpin,YEL)
    # FG: motor -> HV(ch) ; LV(ch) -> C6
    elbow(M['FG'],HV[cf],GRN); tag(320,M['FG'][1]+4,pre+'-FG → HV'+cf,GRN)
    elbow(LV[cf],C6P[fpin],GRN); tag(960,LV[cf][1]+4,'LV'+cf+' → '+fpin,GRN)

# refs
elbow(C6P['3V3'],(sx+230,200),PUR); tag(965,588,'3V3→LV',PUR)
elbow(C6P['5V'],(sx,200),PUR)

# ground rail + power
gy=720
d.line([(90,gy),(1420,gy)],fill=MUT,width=4); d.text((94,gy+8),"COMMON GROUND  ·  pack −  ·  both motor blacks  ·  C6 GND  ·  shifter GND",font=FS,fill=MUT)
box(40,760,230,55,"6S 24V PACK",RED); d.text((300,772),"+24V → both motor reds",font=FS,fill=RED)
for pre,M,cd,cf,pwm,dpin,fpin,lane in motors:
    xr=300+({'L':0,'R':18}[pre]); wire(M['VCC'],(xr,M['VCC'][1]),RED); wire((xr,M['VCC'][1]),(xr,785),RED); wire((xr,785),(175,785),RED)
    wire(M['GND'],(295,M['GND'][1]),BLK); wire((295,M['GND'][1]),(295,gy),BLK)
wire(C6P['GND'],(1225,C6P['GND'][1]),ACC); wire((1225,C6P['GND'][1]),(1225,gy),ACC)
wire((sx,540),(sx,gy),MUT)
d.text((40,gy+34) if False else (300,748),"",font=FS,fill=MUT)
img.save(os.path.join(OUT,"c6_2motor_wiring.png")); print("wrote",img.size)

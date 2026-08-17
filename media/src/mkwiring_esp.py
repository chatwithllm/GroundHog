#!/usr/bin/env python3
"""Complete bench wiring: ESP8266 + BSS138 level shifter + 2 BLDC motors + 24V pack.
-> media/diagrams/esp8266_wiring.png"""
import os
from PIL import Image, ImageDraw, ImageFont
OUT=os.path.join(os.path.dirname(__file__),"..","diagrams")
BG=(15,20,27); PANEL=(24,32,43); INK=(233,239,245); MUT=(150,168,184); ACC=(76,196,224)
RED=(230,60,60); BLK=(90,95,105); BLUE=(70,135,230); YEL=(232,200,45); GRN=(45,195,120)
WARN=(240,175,60); OR3=(245,160,70); PUR=(180,120,235)
def font(s,b=False):
    for p in [("/System/Library/Fonts/Supplemental/Arial Bold.ttf" if b else "/System/Library/Fonts/Supplemental/Arial.ttf"),
              ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if b else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")]:
        if os.path.exists(p): return ImageFont.truetype(p,s)
    return ImageFont.load_default()
def mono(s):
    for p in ["/System/Library/Fonts/Menlo.ttc","/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"]:
        if os.path.exists(p): return ImageFont.truetype(p,s)
    return font(s)
FT=font(25,True); FB=font(16,True); FP=mono(14); FS=mono(12)
W,H=1680,1090
img=Image.new("RGB",(W,H),BG); d=ImageDraw.Draw(img)
d.text((34,20),"Bench wiring:  ESP8266 + BSS138 level-shifter + 2 BLDC motors + 24V pack",font=FT,fill=INK)
d.text((36,54),"5V motor signals (FG, CW/CCW) cross the shifter; PWM (3.3V, works direct) bypasses it. All grounds common.",font=FP,fill=MUT)

def box(x,y,w,h,title,color=ACC,sub=None):
    d.rounded_rectangle([x,y,x+w,y+h],11,fill=PANEL,outline=color,width=2)
    d.text((x+11,y+8),title,font=FB,fill=INK)
    if sub: d.text((x+11,y+27),sub,font=FS,fill=MUT)
def wire(p1,p2,c,w=4): d.line([p1,p2],fill=c,width=w)
def L(p1,p2,c,w=4): d.line([p1,p2],fill=c,width=w)   # straight
def dot(p,c): d.ellipse([p[0]-5,p[1]-5,p[0]+5,p[1]+5],fill=c,outline=(230,230,230))
def tag(x,y,t,c):
    tw=len(t)*7; d.rectangle([x-2,y-2,x+tw,y+13],fill=BG); d.text((x,y-1),t,font=FS,fill=c)

# ---- LEFT MOTOR ----
box(34,110,175,215,"LEFT MOTOR")
LM={'PWM':(BLUE,155),'CW/CCW':(YEL,195),'FG':(GRN,235),'VCC':(RED,278),'GND':(BLK,308)}
for k,(c,yy) in LM.items():
    dot((209,yy),c); d.text((96,yy-8),k,font=FS,fill=c if c!=BLK else MUT)

# ---- RIGHT MOTOR ----
box(34,420,175,215,"RIGHT MOTOR")
RM={'PWM':(BLUE,465),'CW/CCW':(YEL,505),'FG':(GRN,545),'VCC':(RED,588),'GND':(BLK,618)}
for k,(c,yy) in RM.items():
    dot((209,yy),c); d.text((96,yy-8),k,font=FS,fill=c if c!=BLK else MUT)

# ---- LEVEL SHIFTER ----
sx=600; box(sx,210,200,430,"BSS138 LEVEL SHIFTER","#b478eb","HV = motor 5V side   LV = ESP 3.3V side")
# HV pins (left) / LV pins (right)
rows=[('ref','HV','LV',255),('1','HV1','LV1',320),('2','HV2','LV2',385),('3','HV3','LV3',450)]
HV={}; LV={}
for key,hl,ll,yy in rows:
    dot((sx,yy),PUR); d.text((sx+10,yy-8),hl,font=FS,fill=MUT); HV[key]=(sx,yy)
    dot((sx+200,yy),PUR); d.text((sx+200-34,yy-8),ll,font=FS,fill=MUT); LV[key]=(sx+200,yy)
dot((sx,600),MUT); d.text((sx+10,592),"GND",font=FS,fill=MUT)
dot((sx+200,600),MUT); d.text((sx+200-40,592),"GND",font=FS,fill=MUT)

# ---- ESP8266 ----
ex=1250; box(ex,150,240,560,"NodeMCU ESP8266")
EP={'D5':190,'D6':240,'D7':290,'D1':370,'D2':420,'3V3':520,'5V':560,'GND':650}
for k,yy in EP.items():
    dot((ex,yy),ACC); d.text((ex+14,yy-8),k,font=FP,fill=INK)
d.text((ex+14,700),"(USB powers 5V pin)",font=FS,fill=MUT)

# ===== SIGNAL WIRES =====
# PWM direct (bypass shifter)
L((209,155),(ex,190),BLUE); tag(400,150,"L-PWM (direct)",BLUE)
L((209,465),(ex,370),BLUE); tag(360,455,"R-PWM (direct)",BLUE)
# L-FG : motor green -> HV1 ; LV1 -> D7
L((209,235),HV['1'],GRN); tag(300,300,"L-FG",GRN)
L(LV['1'],(ex,290),GRN)
# L-DIR: motor yellow -> HV2 ; LV2 -> D6
L((209,195),HV['2'],YEL); tag(300,360,"L-DIR",YEL)
L(LV['2'],(ex,240),YEL)
# R-DIR: motor yellow -> HV3 ; LV3 -> D2
L((209,505),HV['3'],YEL); tag(300,470,"R-DIR",YEL)
L(LV['3'],(ex,420),YEL)
# R-FG not connected
d.line([(215,545-7),(231,545+7)],fill=WARN,width=3); d.line([(215,545+7),(231,545-7)],fill=WARN,width=3)
d.text((238,545-7),"R-FG not used (no free pin)",font=FS,fill=WARN)

# ===== SHIFTER REFERENCES =====
# LV ref <- ESP 3V3 ; HV ref <- ESP 5V
L(LV['ref'],(ex,520),OR3); tag(1000,250,"LV ← 3V3",OR3)
L(HV['ref'],(1000,255),OR3); L((1000,255),(1000,120),OR3); L((1000,120),(1245,120),OR3); L((1245,120),(ex,560),OR3)
tag(760,110,"HV ← 5V (ESP 5V pin)",OR3)

# ===== GROUND RAIL =====
gy=780
d.line([(90,gy),(1400,gy)],fill=MUT,width=4)
d.text((94,gy+8),"COMMON GROUND  ·  pack −  ·  both motor blacks  ·  ESP GND  ·  shifter GND (both sides)",font=FS,fill=MUT)
L((209,308),(300,308),BLK); L((300,308),(300,gy),BLK)      # L black
L((209,618),(330,618),BLK); L((330,618),(330,gy),BLK)      # R black
L(HV['ref'][0:1]+(0,),(0,0),BLK,1)  # noop guard
L((sx,600),(sx,gy),MUT)                                    # shifter HV GND
L((sx+200,600),(sx+200,gy),MUT)                            # shifter LV GND
L((ex,650),(ex-70,650),ACC); L((ex-70,650),(ex-70,gy),ACC)  # ESP GND

# ===== 24V PACK =====
box(34,820,175,110,"6S 24V PACK",RED)
d.text((52,860),"+24V",font=FP,fill=RED); d.text((52,886),"GND (−)",font=FP,fill=MUT)
# reds to +24V
L((209,278),(360,278),RED); L((360,278),(360,860),RED); L((360,860),(165,860),RED)
L((209,588),(390,588),RED); L((390,588),(390,865),RED); L((390,865),(209,865),RED)
tag(240,270,"→ +24V",RED)
L((150,902),(150,gy),MUT)                                  # pack - to rail

# notes
ny=955
d.text((470,ny),"Shifter: LV pin→ESP 3V3, HV pin→ESP 5V, GND→common. Channels: HV1/LV1=L-FG, HV2/LV2=L-DIR, HV3/LV3=R-DIR.",font=FS,fill=INK)
d.text((470,ny+20),"PWM stays direct (proven at 3.3V). Reds→24V, blacks→common GND. ESP on USB. Wheels up. Blade NOT on this board.",font=FS,fill=WARN)
img.save(os.path.join(OUT,"esp8266_wiring.png")); print("wrote",img.size)

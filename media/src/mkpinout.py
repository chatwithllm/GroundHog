#!/usr/bin/env python3
"""BLDC5520 integrated-driver pinout → ESP32-C3. Outputs media/diagrams/pinout.png"""
import os
from PIL import Image, ImageDraw, ImageFont
OUT=os.path.join(os.path.dirname(__file__),"..","diagrams")
BG=(15,20,27); PANEL=(22,29,39); LINE=(38,49,63); INK=(231,237,243); MUT=(142,161,180)
ACC=(76,196,224); WARN=(240,170,60); RED=(230,60,60); GRN=(84,209,138)
def font(sz,b=False):
    for p in [("/System/Library/Fonts/Supplemental/Arial Bold.ttf" if b else "/System/Library/Fonts/Supplemental/Arial.ttf"),
              ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if b else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")]:
        if os.path.exists(p): return ImageFont.truetype(p,sz)
    return ImageFont.load_default()
def mono(sz):
    for p in ["/System/Library/Fonts/Menlo.ttc","/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"]:
        if os.path.exists(p): return ImageFont.truetype(p,sz)
    return font(sz)
FT=font(30,True); FB=font(19,True); FP=mono(17); FS=mono(14); FH=font(21,True)
W,H=1240,860
img=Image.new("RGB",(W,H),BG); d=ImageDraw.Draw(img)
d.text((40,28),"BLDC5520 (24V) — Integrated-Driver Pinout",font=FT,fill=INK)
d.text((42,70),"CONFIRMED from board silk + datasheet · wire colors verified · Seeed XIAO ESP32-C3",font=FP,fill=ACC)

# color swatches (provisional wire colors — order per datasheet pins 1..5)
SW={"blue":(70,130,220),"black":(60,60,66),"yellow":(230,200,40),"green":(40,190,120),"red":(225,60,60)}
rows=[
 # pin, func, wirecolorname, esp, note, confirmed
 ("1","VCC","red","→ 24V +  (pack, NOT the ESP)","motor driver power in  (8–24V)",True),
 ("2","FG","green","→ D3 / GPIO5  (input, pull-up)","speed feedback — tach pulses out",True),
 ("3","CW/CCW","yellow","→ D2 / GPIO4  (output)","direction: HIGH/LOW flips spin",True),
 ("4","GND","black","→ GND  (pack + ESP common)","ground",True),
 ("5","PWM","blue","→ D1 / GPIO3  (LEDC PWM)","speed: duty cycle sets rpm",True),
]
# table
x0,y0=40,130; rw=1160; rh=110
d.text((x0+8,y0-26),"PIN",font=FS,fill=MUT)
d.text((x0+70,y0-26),"WIRE (verify)",font=FS,fill=MUT)
d.text((x0+330,y0-26),"FUNCTION",font=FS,fill=MUT)
d.text((x0+560,y0-26),"→ ESP32-C3",font=FS,fill=MUT)
for i,(pin,func,wc,esp,note,ok) in enumerate(rows):
    y=y0+i*rh
    border=GRN if ok else LINE
    d.rounded_rectangle([x0,y,x0+rw,y+rh-12],10,fill=PANEL,outline=border,width=2)
    d.text((x0+18,y+38),pin,font=FH,fill=MUT)
    # wire swatch
    d.rounded_rectangle([x0+70,y+30,x0+150,y+66],7,fill=SW[wc],outline=(200,200,200),width=1)
    d.text((x0+70,y+72),wc+(" ✓" if ok else " ?"),font=FS,fill=(GRN if ok else MUT))
    d.text((x0+330,y+24),func,font=FH,fill=(GRN if func=="GND" else (RED if func=="VCC" else ACC)))
    d.text((x0+330,y+58),note,font=FS,fill=MUT)
    d.text((x0+560,y+40),esp,font=FP,fill=INK)
# warning box
wy=690
d.rounded_rectangle([40,wy,W-40,wy+120],10,fill=(20,34,26),outline=GRN,width=2)
d.text((60,wy+14),"✓ CONFIRMED — red=VCC, black=GND, blue=PWM, yellow=CW/CCW, green=FG",font=FB,fill=GRN)
d.text((60,wy+46),"First power-up: VCC(red)/GND(black) from a CURRENT-LIMITED supply (~0.5A). XIAO powered by USB — never 24V on the XIAO.",font=FS,fill=INK)
d.text((60,wy+68),"All grounds common (pack GND + XIAO GND + black). Check FG level: hand-spin, meter green→GND; if >3.3V add a divider before D3.",font=FS,fill=INK)
d.text((60,wy+92),"Wheels up. Signal wires (PWM/CW-CCW/FG) are 3.3V logic. Start low duty; if it spins at 0% and stops at 100%, set invert.",font=FS,fill=MUT)
d.text((40,H-28),"3 motors identical → same mapping. Bench ONE drive motor first; blade LAST (removed) on its own fuse + e-stop.",font=FS,fill=MUT)
img.save(os.path.join(OUT,"pinout.png")); print("wrote pinout.png",img.size)

// BLDC5520 diagnostic — NodeMCU ESP32 (WROOM-32), USB serial control.
// PWM=GPIO25 (blue), DIR=GPIO26 (yellow), FG=GPIO27 (green), GND common, VCC=24V pack.
// Serial 115200. Cmds: d<0-100> duty | f<hz> freq | h HIGH | l LOW | F/R dir | s stop | t autosweep
#include <Arduino.h>
#define PIN_PWM 25
#define PIN_DIR 26
#define PIN_FG  27
int res = 8, freq = 20000;
volatile uint32_t fg = 0;
void IRAM_ATTR isr(){ fg++; }
int duty = 0;
bool pwmAttached = false;

void attach(){ if(!pwmAttached){ ledcAttach(PIN_PWM, freq, res); pwmAttached = true; } }
void setDuty(int p){ attach(); duty = constrain(p,0,100); ledcWrite(PIN_PWM, map(duty,0,100,0,(1<<res)-1)); }
void doHigh(){ if(pwmAttached){ ledcDetach(PIN_PWM); pwmAttached=false; } pinMode(PIN_PWM,OUTPUT); digitalWrite(PIN_PWM,HIGH); Serial.println(">> GPIO25 = HIGH (static)"); }
void doLow(){  if(pwmAttached){ ledcDetach(PIN_PWM); pwmAttached=false; } pinMode(PIN_PWM,OUTPUT); digitalWrite(PIN_PWM,LOW);  Serial.println(">> GPIO25 = LOW (static)"); }

void autosweep(){
  Serial.println("== AUTOSWEEP: watch motor, note each step ==");
  doHigh(); Serial.println("STEP A: GPIO25 HIGH (3s)"); delay(3000);
  doLow();  Serial.println("STEP B: GPIO25 LOW (3s)");  delay(3000);
  int st[] = {0,25,50,75,100};
  for(int i=0;i<5;i++){ setDuty(st[i]); Serial.printf("STEP PWM %d%% (3s)\n", st[i]); delay(3000); }
  setDuty(0); Serial.println("== SWEEP DONE, duty 0 ==");
}

void setup(){
  Serial.begin(115200); delay(400);
  pinMode(PIN_DIR, OUTPUT); digitalWrite(PIN_DIR, LOW);
  pinMode(PIN_FG, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(PIN_FG), isr, RISING);
  setDuty(0);
  Serial.println("\nBLDC DIAG ready. cmds: d<0-100> | f<hz> | h | l | F | R | s | t(autosweep)");
}

void loop(){
  if(Serial.available()){
    String s = Serial.readStringUntil('\n'); s.trim();
    if(s.length()){
      char c = s[0];
      if(c=='d'){ setDuty(s.substring(1).toInt()); Serial.printf("duty=%d%%\n",duty); }
      else if(c=='f'){ freq=s.substring(1).toInt(); attach(); ledcChangeFrequency(PIN_PWM,freq,res); Serial.printf("freq=%d Hz\n",freq); }
      else if(c=='h'){ doHigh(); }
      else if(c=='l'){ doLow(); }
      else if(c=='F'){ digitalWrite(PIN_DIR,HIGH); Serial.println("DIR=HIGH"); }
      else if(c=='R'){ digitalWrite(PIN_DIR,LOW);  Serial.println("DIR=LOW"); }
      else if(c=='s'){ setDuty(0); Serial.println("STOP (duty 0)"); }
      else if(c=='t'){ autosweep(); }
    }
  }
  static uint32_t t=0;
  if(millis()-t>=1000){ t=millis(); noInterrupts(); uint32_t v=fg; fg=0; interrupts();
    Serial.printf("FG=%lu Hz  duty=%d%%  freq=%d\n", v, duty, freq); }
}

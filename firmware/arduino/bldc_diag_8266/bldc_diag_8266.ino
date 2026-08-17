// BLDC5520 diagnostic — NodeMCU ESP8266, USB serial control.
// PWM=D5(GPIO14) blue, DIR=D6(GPIO12) yellow, FG=D7(GPIO13) green, GND common, VCC=24V pack.
// ESP8266 GPIOs are 3.3V and NOT 5V-tolerant. Measure FG<=3.3V before wiring green!
// Serial 115200. cmds: d<0-100> duty | f<hz> freq | h HIGH | l LOW | F/R dir | s stop | t autosweep
#include <Arduino.h>
#define PIN_PWM D5   // GPIO14
#define PIN_DIR D6   // GPIO12
#define PIN_FG  D7   // GPIO13
volatile uint32_t fg = 0;
void IRAM_ATTR isr(){ fg++; }
int duty = 0, freq = 20000;

void setDuty(int p){ duty = constrain(p,0,100); analogWrite(PIN_PWM, duty); }  // range set to 100 below

void autosweep(){
  Serial.println("== AUTOSWEEP: watch motor, note each step ==");
  setDuty(100); Serial.println("STEP A: PWM 100% (const HIGH) 3s"); delay(3000);
  setDuty(0);   Serial.println("STEP B: PWM 0% (const LOW) 3s");   delay(3000);
  int st[] = {0,25,50,75,100};
  for(int i=0;i<5;i++){ setDuty(st[i]); Serial.printf("STEP PWM %d%% 3s\n", st[i]); delay(3000); }
  setDuty(0); Serial.println("== DONE, duty 0 ==");
}

void setup(){
  Serial.begin(115200); delay(300);
  pinMode(PIN_DIR, OUTPUT); digitalWrite(PIN_DIR, LOW);
  pinMode(PIN_FG, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(PIN_FG), isr, RISING);
  analogWriteRange(100);        // duty 0..100 = percent
  analogWriteFreq(freq);        // 20 kHz
  setDuty(0);
  Serial.println("\nBLDC DIAG (ESP8266) ready. cmds: d<0-100>|f<hz>|h|l|F|R|s|t(autosweep)");
}

void loop(){
  if(Serial.available()){
    String s = Serial.readStringUntil('\n'); s.trim();
    if(s.length()){
      char c = s[0];
      if(c=='d'){ setDuty(s.substring(1).toInt()); Serial.printf("duty=%d%%\n",duty); }
      else if(c=='f'){ freq=s.substring(1).toInt(); analogWriteFreq(freq); Serial.printf("freq=%d Hz\n",freq); }
      else if(c=='h'){ setDuty(100); Serial.println("PWM const HIGH"); }
      else if(c=='l'){ setDuty(0);   Serial.println("PWM const LOW"); }
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

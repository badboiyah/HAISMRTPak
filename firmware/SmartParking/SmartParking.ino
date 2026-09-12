/* ESP32 DevKit V1, Arduino-ESP32 3.x; bench prototype, see docs/HARDWARE.md. */
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include "config.h"

const int TRIG[4] = {13, 14, 25, 26};
const int ECHO[4] = {34, 35, 36, 39};
const int ENTRY_IR = 18, EXIT_IR = 19, BEAM_IR = 23;
const int SERVO_PIN = 27, GREEN_LED = 32, RED_LED = 33;
const char* SLOT_NAMES[4] = {"A1", "A2", "A3", "A4"};
const float OCCUPIED_CM = 12, FREE_CM = 16;
Adafruit_SSD1306 oled(128, 64, &Wire, -1);
bool displayReady = false, gateOpen = false, lastEntry = false, lastExit = false;
int stable[4] = {-1, -1, -1, -1}, candidate[4] = {-1, -1, -1, -1}, repetitions[4] = {0,0,0,0};
unsigned long lastSample=0, lastSend=0, lastWifi=0, openedAt=0, clearSince=0, lastServer=0;
unsigned long entrySince=0, exitSince=0;
uint32_t sequence=0;
String bootId, acknowledged, handled;

bool beamBlocked() { return digitalRead(BEAM_IR) == LOW; }
int freeCount() { int count=0; for (int i=0;i<4;i++) if(stable[i]==0) count++; return count; }
bool known() { for(int i=0;i<4;i++) if(stable[i]<0) return false; return true; }
void servoAngle(int angle) {
  // 50 Hz period = 20000 us; calibrate 1000–2000 us for your servo.
  uint32_t pulse=map(angle,0,90,1000,2000);
  ledcWrite(SERVO_PIN, pulse * 65535UL / 20000UL);
}
void openGate() { servoAngle(90); gateOpen=true; openedAt=millis(); clearSince=0; }
void closeGate() { if(!beamBlocked()) { servoAngle(0); gateOpen=false; } }
void safetyLoop() {
  if(!gateOpen) return;
  if(beamBlocked()) clearSince=0;
  else {
    if(clearSince==0) clearSince=millis();
    if(millis()-openedAt>=5000 && millis()-clearSince>=2000) closeGate();
  }
}
float distanceCm(int index) {
  digitalWrite(TRIG[index],LOW);delayMicroseconds(3);
  digitalWrite(TRIG[index],HIGH);delayMicroseconds(10);digitalWrite(TRIG[index],LOW);
  unsigned long pulse=pulseIn(ECHO[index],HIGH,20000);
  return pulse ? pulse*0.0343f/2 : -1;
}
void sampleSlots() {
  for(int i=0;i<4;i++) {
    float cm=distanceCm(i);
    int next=cm<0 ? -1 : cm<OCCUPIED_CM ? 1 : cm>FREE_CM ? 0 : stable[i];
    if(candidate[i]!=next) { candidate[i]=next; repetitions[i]=1; }
    else if(repetitions[i]<3) repetitions[i]++;
    // Sensor failure becomes unknown immediately; occupancy needs three samples.
    if(next<0 || repetitions[i]>=3) stable[i]=next;
    safetyLoop();
    delay(25); // Separate acoustic pulses to reduce cross-talk.
  }
}
void updateDisplay() {
  bool available=known() && freeCount()>0;
  digitalWrite(GREEN_LED, available?HIGH:LOW);digitalWrite(RED_LED,available?LOW:HIGH);
  if(!displayReady) return;
  oled.clearDisplay();oled.setTextColor(SSD1306_WHITE);oled.setTextSize(1);oled.setCursor(0,0);oled.print("HAISMRTPak / KHU A");
  oled.setCursor(0,18);oled.setTextSize(2);
  if(!known()) oled.print("CAM BIEN ?"); else {oled.print("TRONG ");oled.print(freeCount());oled.print("/4");}
  oled.setTextSize(1);oled.setCursor(0,43);oled.print(gateOpen?"THANH CHAN: MO":"THANH CHAN: DONG");
  oled.setCursor(0,55);oled.print(lastServer && millis()-lastServer<15000?"MAY CHU: KET NOI":"MAY CHU: MAT MANG");oled.display();
}
bool post(const char* route, JsonDocument& data, JsonDocument& result) {
  if(WiFi.status()!=WL_CONNECTED) return false;
  HTTPClient http;http.setConnectTimeout(500);http.setTimeout(500);
  http.begin(String(SERVER_URL)+route);http.addHeader("Content-Type","application/json");http.addHeader("X-Device-Key",DEVICE_KEY);
  String payload;serializeJson(data,payload);int code=http.POST(payload);
  bool ok=false;
  if(code==200) {ok=!deserializeJson(result,http.getString());if(ok) lastServer=millis();}
  http.end();safetyLoop();return ok;
}
void applyCommand(JsonVariant command, double serverTime) {
  if(command.isNull()) return;
  String id=command["id"].as<String>(), action=command["action"].as<String>();
  if(id.length()==0 || id==handled || command["expires_at"].as<double>()<=serverTime) return;
  if(action=="entry") {if(gateOpen || !known() || freeCount()==0) return;openGate();}
  else if(action=="exit") openGate();
  else if(action=="close") {if(beamBlocked()) return;closeGate();}
  else return;
  handled=id;acknowledged=id;
}
void telemetry() {
  JsonDocument data,result;
  data["boot_id"]=bootId;data["sequence"]=sequence++;
  for(int i=0;i<4;i++){ if(stable[i]<0) data["slots"][SLOT_NAMES[i]]=nullptr;else data["slots"][SLOT_NAMES[i]]=stable[i]==1; }
  data["barrier"]=gateOpen?"open":"closed";data["beam"]=beamBlocked();
  data["entry_present"]=lastEntry;
  data["exit_present"]=lastExit;
  if(acknowledged.length()) data["ack"]=acknowledged;
  if(post("/api/device/telemetry",data,result)) applyCommand(result["command"],result["server_time"].as<double>());
}
void requestGate(const char* action) {
  if(!lastServer || millis()-lastServer>=15000) return;
  JsonDocument data,result;data["action"]=action;
  // The command is delivered in the next telemetry response with server time.
  post("/api/device/gate",data,result);
  lastSend=0;
}
bool debouncedRequest(int pin, unsigned long& since, bool& latched) {
  if(digitalRead(pin)!=LOW){since=0;latched=false;return false;}
  if(!since) since=millis();
  if(!latched && millis()-since>=150){latched=true;return true;}
  return false;
}
void setup() {
  Serial.begin(115200);
  for(int i=0;i<4;i++){pinMode(TRIG[i],OUTPUT);digitalWrite(TRIG[i],LOW);pinMode(ECHO[i],INPUT);}
  pinMode(ENTRY_IR,INPUT_PULLUP);pinMode(EXIT_IR,INPUT_PULLUP);pinMode(BEAM_IR,INPUT_PULLUP);
  pinMode(GREEN_LED,OUTPUT);pinMode(RED_LED,OUTPUT);
  ledcAttach(SERVO_PIN,50,16);
  // On startup, an obstructed gate remains open.
  if(beamBlocked()) openGate(); else closeGate();
  Wire.begin(21,22);displayReady=oled.begin(SSD1306_SWITCHCAPVCC,0x3C);
  bootId=String((uint32_t)(ESP.getEfuseMac()>>32),HEX)+String((uint32_t)esp_random(),HEX);
  WiFi.mode(WIFI_STA);WiFi.begin(WIFI_SSID,WIFI_PASSWORD);
  Serial.println("HAISMRTPak da khoi dong");
}
void loop() {
  safetyLoop();
  // Entry detection only announces the car. The driver's QR confirmation
  // creates the entry command, which arrives in the telemetry response.
  debouncedRequest(ENTRY_IR,entrySince,lastEntry);
  if(millis()-lastSample>=250){lastSample=millis();sampleSlots();updateDisplay();}
  if(WiFi.status()!=WL_CONNECTED && millis()-lastWifi>=10000){lastWifi=millis();WiFi.reconnect();}
  if(millis()-lastSend>=2000){lastSend=millis();telemetry();}
  debouncedRequest(EXIT_IR,exitSince,lastExit);
  delay(5);
}

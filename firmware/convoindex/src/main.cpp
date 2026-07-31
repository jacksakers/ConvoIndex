// ConvoIndex — Phase 1 firmware
// LAFVIN AI Chatbot board: ESP32-S3 DevKit + ES8311 (DAC/mic) + ES7210 (mic ADC) shield.
//
// Goal (PRD Phase 1 - "The Dumb Pipe"): capture I2S mic audio and stream it
// raw over a WebSocket to local-backend/capture_server.py so audio quality
// can be verified before adding VAD/STT/LLM/TTS in later phases.
//
// Pin mapping reused verbatim from:
//   xiaozhi-esp32-main/main/boards/lafvin-aichatbot/config.h
//   xiaozhi-esp32-main/main/boards/lafvin-aichatbot/lafvin-aichatbot.cc

#include <Arduino.h>
#include <WiFi.h>
#include <WebSocketsClient.h>
#include <driver/i2s_std.h>
#include <driver/gpio.h>

#include "AudioBoard.h"

#include "secrets.h"

using namespace audio_driver;

// ---- Pins (LAFVIN AI Chatbot shield) ----
#define I2S_MCLK_PIN 38
#define I2S_BCLK_PIN 14
#define I2S_WS_PIN   13
#define I2S_DOUT_PIN 45  // codec DAC data in (speaker) — unused in phase 1
#define I2S_DIN_PIN  12  // codec ADC data out (mic)

#define I2C_SDA_PIN 1
#define I2C_SCL_PIN 2

#define PA_ENABLE_PIN GPIO_NUM_48  // keep speaker amp disabled during capture-only phase
#define BOOT_BUTTON_PIN GPIO_NUM_0

// ---- Audio format (must match local-backend/config.py SAMPLE_RATE/CHANNELS) ----
static constexpr uint32_t SAMPLE_RATE = 16000;
static constexpr int READ_FRAMES = 512;  // stereo frames per I2S read

// The ES7210/ES8311 combo on this board is wired for 2 I2S slots
// (mic + AEC reference channel); we only forward the mic channel (slot 0).
static int16_t i2s_stereo_buf[READ_FRAMES * 2];
static int16_t mono_buf[READ_FRAMES];

static DriverDeviceInfo codecPins;
static AudioBoard codecBoard{AudioDriverES8311_ES7210, codecPins};

static i2s_chan_handle_t rx_handle = nullptr;
static WebSocketsClient webSocket;
static bool streaming = false;
static bool wsConnected = false;

static void setupCodecPins() {
  codecPins.addI2C(PinFunction::CODEC, I2C_SCL_PIN, I2C_SDA_PIN, 0, 400000);
  // mclk, bck, ws, data_out(to codec DAC), data_in(from codec ADC)
  codecPins.addI2S(PinFunction::CODEC, I2S_MCLK_PIN, I2S_BCLK_PIN, I2S_WS_PIN,
                    I2S_DOUT_PIN, I2S_DIN_PIN);
  codecPins.addPin(PinFunction::PA, PA_ENABLE_PIN, PinLogic::Output);
}

static bool setupCodec() {
  setupCodecPins();

  CodecConfig cfg;
  cfg.input_device = ADC_INPUT_ALL;
  cfg.output_device = DAC_OUTPUT_NONE;
  cfg.i2s.mode = MODE_SLAVE;  // ESP32 is the I2S bus master, codec is slave
  cfg.i2s.fmt = I2S_NORMAL;
  cfg.i2s.rate = RATE_16K;
  cfg.i2s.bits = BIT_LENGTH_16BITS;
  cfg.i2s.channels = CHANNELS2;

  if (!codecBoard.begin(cfg)) {
    Serial.println("Codec init failed!");
    return false;
  }
  codecBoard.setPAPower(false);  // amp stays muted, we only capture in phase 1
  return true;
}

static bool setupI2SRx() {
  i2s_chan_config_t chan_cfg =
      I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
  if (i2s_new_channel(&chan_cfg, nullptr, &rx_handle) != ESP_OK) {
    return false;
  }

  i2s_std_config_t std_cfg = {
      .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(SAMPLE_RATE),
      .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(
          I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_STEREO),
      .gpio_cfg =
          {
              .mclk = static_cast<gpio_num_t>(I2S_MCLK_PIN),
              .bclk = static_cast<gpio_num_t>(I2S_BCLK_PIN),
              .ws = static_cast<gpio_num_t>(I2S_WS_PIN),
              .dout = I2S_GPIO_UNUSED,
              .din = static_cast<gpio_num_t>(I2S_DIN_PIN),
              .invert_flags = {.mclk_inv = false, .bclk_inv = false, .ws_inv = false},
          },
  };

  if (i2s_channel_init_std_mode(rx_handle, &std_cfg) != ESP_OK) {
    return false;
  }
  return i2s_channel_enable(rx_handle) == ESP_OK;
}

static void webSocketEvent(WStype_t type, uint8_t* payload, size_t length) {
  switch (type) {
    case WStype_CONNECTED:
      Serial.println("WebSocket connected to capture server");
      wsConnected = true;
      break;
    case WStype_DISCONNECTED:
      Serial.println("WebSocket disconnected");
      wsConnected = false;
      break;
    default:
      break;
  }
}

static void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.printf("Connecting to WiFi \"%s\"", WIFI_SSID);
  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
    Serial.print(".");
  }
  Serial.printf("\nWiFi connected, IP: %s\n", WiFi.localIP().toString().c_str());
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("\nConvoIndex Phase 1 — I2S capture -> WebSocket");

  pinMode(BOOT_BUTTON_PIN, INPUT_PULLUP);

  if (!setupCodec()) {
    Serial.println("FATAL: codec bring-up failed, halting.");
    while (true) delay(1000);
  }
  if (!setupI2SRx()) {
    Serial.println("FATAL: I2S RX channel init failed, halting.");
    while (true) delay(1000);
  }

  connectWifi();

  webSocket.begin(CAPTURE_SERVER_HOST, CAPTURE_SERVER_PORT, "/capture");
  webSocket.onEvent(webSocketEvent);
  webSocket.setReconnectInterval(3000);

  // Streaming starts automatically; hold BOOT to pause/resume for testing.
  streaming = true;
  Serial.println("Streaming mic audio. Hold BOOT button to pause/resume.");
}

static void handleBootButton() {
  static bool lastPressed = false;
  static uint32_t lastChangeMs = 0;
  bool pressed = digitalRead(BOOT_BUTTON_PIN) == LOW;
  if (pressed != lastPressed && millis() - lastChangeMs > 200) {
    lastChangeMs = millis();
    lastPressed = pressed;
    if (pressed) {
      streaming = !streaming;
      Serial.printf("Streaming %s\n", streaming ? "resumed" : "paused");
    }
  }
}

void loop() {
  webSocket.loop();
  handleBootButton();

  size_t bytes_read = 0;
  esp_err_t err = i2s_channel_read(rx_handle, i2s_stereo_buf,
                                    sizeof(i2s_stereo_buf), &bytes_read,
                                    /*timeout_ms=*/100);
  if (err != ESP_OK || bytes_read == 0) {
    return;
  }

  size_t stereo_frames = bytes_read / (2 * sizeof(int16_t));
  for (size_t i = 0; i < stereo_frames; i++) {
    mono_buf[i] = i2s_stereo_buf[i * 2];  // slot 0 = mic channel
  }

  if (streaming && wsConnected) {
    webSocket.sendBIN(reinterpret_cast<uint8_t*>(mono_buf),
                       stereo_frames * sizeof(int16_t));
  }
}

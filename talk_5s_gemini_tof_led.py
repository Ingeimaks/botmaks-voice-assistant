# file: talk_5s_gemini_tof_led.py
import os, re, sys, time, json, base64, tempfile, subprocess, requests, threading

# --- ToF VL53L0X (CircuitPython) ---
import board, busio
import adafruit_vl53l0x

# --- LED ring WS2812 (GPIO13 / PWM1) ---
from rpi_ws281x import PixelStrip, Color

# ========== GEMINI ==========
API_KEY = os.environ.get("GEMINI_API_KEY")
assert API_KEY, "Imposta GEMINI_API_KEY (es: export GEMINI_API_KEY=...)"
GEN_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
TTS_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent"

# ========== ToF ==========
TRIGGER_MM = 100         # 10 cm
DEBOUNCE_HITS = 3
POLL_INTERVAL = 0.05
COOLDOWN_S = 5

# ========== AUDIO ==========
REC_SECONDS = 5
MIC_DEVICE_ENV = os.environ.get("MIC_DEVICE")  # es. "hw:0,0"

def run(cmd, quiet=False):
    if not quiet:
        print("$", " ".join(cmd))
    return subprocess.run(
        cmd, check=True,
        stdout=(subprocess.DEVNULL if quiet else None),
        stderr=(subprocess.DEVNULL if quiet else None)
    )

def detect_capture_device():
    try:
        out = subprocess.check_output(["arecord","-l"], text=True, stderr=subprocess.STDOUT)
        for line in out.splitlines():
            m = re.search(r"card\s+(\d+).+device\s+(\d+)", line)
            if m:
                return f"hw:{m.group(1)},{m.group(2)}"
    except Exception as e:
        print("Detect device fallita:", e)
    return "hw:0,0"

def record_i2s_stereo(wav_path="in_48k.wav", seconds=REC_SECONDS, device=None):
    dev = device or MIC_DEVICE_ENV or detect_capture_device()
    run(["arecord","-D",dev,"-f","S32_LE","-r","48000","-c","2","-d",str(seconds), wav_path])

def to_16k_mono(src="in_48k.wav", dst="in_16k.wav"):
    run(["ffmpeg","-y","-i",src,"-ac","1","-ar","16000","-sample_fmt","s16",dst], quiet=True)
    return dst

# --- alza volume sistema (Master o PCM) ---
def set_system_volume(percent=95):
    p = str(max(0, min(100, percent))) + "%"
    try:
        run(["amixer", "-q", "sset", "Master", p], quiet=True)
    except Exception:
        try:
            run(["amixer", "-q", "sset", "PCM", p], quiet=True)
        except Exception:
            pass  # se non esistono controlli mixer, proseguiamo comunque

# --- sanitizer per evitare eco della domanda ---
def clean_reply(text: str) -> str:
    if not text:
        return text
    t = text.strip()
    t = re.sub(r'^(>+\s*)+', '', t, flags=re.M)
    kill_prefixes = (
        r'^trascriz',
        r'^hai detto',
        r'^you said',
        r'^utente[:\-]',
        r'^io[:\-]',
    )
    lines = t.splitlines()
    out = []
    skipping = True
    for line in lines:
        s = line.strip().lower()
        if skipping and (
            any(re.match(p, s) for p in kill_prefixes) or
            re.match(r'^["“][^"”]{1,200}["”]\s*$', s)
        ):
            continue
        else:
            skipping = False
            out.append(line)
    t = "\n".join(out).lstrip()
    t = re.sub(r'^\s*["“](.{1,400}?)["”]\s*(\n+|$)', '', t, flags=re.S)
    t = re.sub(r'\n{3,}', '\n\n', t).strip()
    return t

def ask_gemini_with_audio(wav_path: str,
                          sys_prompt=("Ascolta l'audio e COMPRENDI il contenuto. "
                                      "NON includere trascrizione né citazioni di ciò che ho detto. "
                                      "Rispondi SOLO con la tua risposta, in italiano, breve e utile.")):
    with open(wav_path,"rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    payload = {
        "contents": [{
            "role": "user",
            "parts": [
                {"text": sys_prompt},
                {"inlineData": {"mimeType": "audio/wav", "data": b64}}
            ]
        }]}
    r = requests.post(GEN_URL, headers={"x-goog-api-key": API_KEY}, json=payload, timeout=180)
    if r.status_code != 200:
        print("❌ Gemini STT/LLM error", r.status_code); print(r.text); r.raise_for_status()
    raw = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    return clean_reply(raw)

def tts_to_wav(text: str, voice="Kore"):
    payload = {
        "model": "gemini-2.5-flash-preview-tts",
        "contents": [{"parts":[{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}
        }
    }
    r = requests.post(TTS_URL, headers={"x-goog-api-key": API_KEY}, json=payload, timeout=180)
    if r.status_code != 200:
        print("❌ Gemini TTS error", r.status_code); print(r.text); r.raise_for_status()
    data = r.json()
    b64 = data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
    pcm = base64.b64decode(b64)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pcm") as fpcm:
        fpcm.write(pcm); pcm_path = fpcm.name
    wav_out = pcm_path.replace(".pcm", "_stereo.wav")
    run(["ffmpeg","-y","-f","s16le","-ar","24000","-ac","1","-i",pcm_path,
         "-ac","2","-ar","48000",wav_out], quiet=True)
    return wav_out

# ========== LED (GPIO13 / PWM1) ==========
LED_COUNT   = 35
LED_PIN     = 13
LED_FREQ_HZ = 800000
LED_DMA     = 10
LED_BRIGHT  = 64
LED_INVERT  = False
LED_CHAN    = 1
LED_ORDER   = 0x00100800  # GRB

COL_LISTEN  = (0, 200, 255)  # ciano brillante (blink)
COL_LOAD    = (90, 0, 255)   # blu/violetto (più violetto del parlato)
COL_SPEAK   = (0, 80, 255)   # blu/violetto (parlato)

class LedRing:
    def __init__(self):
        self.strip = PixelStrip(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA,
                                LED_INVERT, LED_BRIGHT, LED_CHAN, LED_ORDER)
        self.strip.begin()
        self._stop = threading.Event()
        self._th = None

    def _color(self, rgb): return Color(rgb[0], rgb[1], rgb[2])

    def off(self):
        self._stop.set()
        th = self._th
        if th and th.is_alive() and threading.current_thread() is not th:
            th.join(timeout=0.5)
        for i in range(self.strip.numPixels()):
            self.strip.setPixelColor(i, 0)
        self.strip.show()
        self._stop.clear()
        self._th = None

    def _run_anim(self, target):
        th = self._th
        self._stop.set()
        if th and th.is_alive() and threading.current_thread() is not th:
            th.join(timeout=0.5)
        self._stop.clear()
        t = threading.Thread(target=target, daemon=True)
        t.start()
        self._th = t

    def listening(self, blinks=2, on_ms=120, off_ms=90, color=COL_LISTEN):
        def anim():
            c = self._color(color)
            for _ in range(blinks):
                if self._stop.is_set(): break
                for i in range(LED_COUNT): self.strip.setPixelColor(i, c)
                self.strip.show(); time.sleep(on_ms/1000)
                for i in range(LED_COUNT): self.strip.setPixelColor(i, 0)
                self.strip.show(); time.sleep(off_ms/1000)
        self._run_anim(anim)

    def loading(self, width=8, delay=0.04, color=COL_LOAD):
        def anim():
            head = 0
            while not self._stop.is_set():
                for i in range(LED_COUNT): self.strip.setPixelColor(i, 0)
                for t in range(width):
                    k = (head + t) % LED_COUNT
                    scale = 0.4 + 0.6 * (1 - t/max(1,width-1))
                    r,g,b = color
                    self.strip.setPixelColor(k, Color(int(r*scale), int(g*scale), int(b*scale)))
                self.strip.show()
                head = (head + 1) % LED_COUNT
                time.sleep(delay)
        self._run_anim(anim)

    def speaking(self, step=6, minv=20, maxv=200, period=0.02, base=COL_SPEAK):
        def anim():
            v = minv; d = 1
            while not self._stop.is_set():
                r = (base[0]*v)//255
                g = (base[1]*v)//255
                b = (base[2]*v)//255
                c = Color(r,g,b)
                for i in range(LED_COUNT): self.strip.setPixelColor(i, c)
                self.strip.show()
                v += step*d
                if v >= maxv: v = maxv; d = -1
                if v <= minv: v = minv; d = 1
                time.sleep(period)
        self._run_anim(anim)

# ========== PIPELINE ==========
def interaction(led: LedRing, seconds=REC_SECONDS):
    # Blink “in ascolto”
    led.listening()
    time.sleep(0.25)

    print(f"🎙️  Registro {seconds}s…")
    record_i2s_stereo("in_48k.wav", seconds=seconds)

    # Loading (blu/violetto)
    led.loading()
    print("🔄 Converto a 16 kHz mono…")
    wav_16k = to_16k_mono("in_48k.wav","in_16k.wav")

    print("🚀 Invio a Gemini (STT + risposta)…")
    reply = ask_gemini_with_audio(wav_16k)
    print("\n=== RISPOSTA ===\n", reply, "\n")

    print("🗣️  TTS e riproduzione…")
    # volume alto prima di parlare
    set_system_volume(95)
    led.speaking()
    out_wav = tts_to_wav(reply)
    run(["aplay", out_wav])

    led.off()
    print("✅ Fatto.")

# ========== MAIN ==========
def main():
    led = LedRing()
    led.off()

    i2c = busio.I2C(board.SCL, board.SDA)
    tof = adafruit_vl53l0x.VL53L0X(i2c)

    hits = 0
    last_trigger = 0.0

    print(f"👀 ToF pronto. Trigger a ≤ {TRIGGER_MM} mm (debounce {DEBOUNCE_HITS}, cooldown {COOLDOWN_S}s). Ctrl+C per uscire.")
    try:
        while True:
            try:
                dist = tof.range
            except Exception as e:
                print("ToF warn:", e); time.sleep(0.2); continue

            if dist is not None and 0 < dist < 8190 and dist <= TRIGGER_MM:
                hits += 1
            else:
                hits = 0

            now = time.time()
            if hits >= DEBOUNCE_HITS and (now - last_trigger) > COOLDOWN_S:
                print(f"🟢 Trigger! Distanza: {dist} mm")
                last_trigger = now
                hits = 0
                interaction(led, seconds=REC_SECONDS)

            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print("\n👋 Uscita.")
    finally:
        led.off()

if __name__ == "__main__":
    main()

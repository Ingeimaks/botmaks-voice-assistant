# BOTMAKS – Assistente Vocale Intelligente per Raspberry Pi

> **Un assistente vocale hands-free potenziato da Google Gemini con sensori avanzati e feedback visivo**

## 🚀 Caratteristiche Principali

BOTMAKS è un assistente vocale **completamente hands-free** progettato per Raspberry Pi Zero/Zero W che combina:

- 🎯 **Attivazione automatica** tramite sensore di prossimità ToF VL53L0X (≤10 cm)
- 🎤 **Audio I²S professionale** con microfono INMP441 e amplificatore MAX98357A
- 🤖 **Intelligenza artificiale** powered by Google Gemini (STT + conversazione + TTS)
- 💡 **Feedback visivo** con anello LED WS2812 (35-36 LED) per indicare lo stato
- ⚡ **Plug & Play** - script principale `talk_5s_gemini_tof_led.py` già funzionante

### 🎭 Come Funziona
1. **Avvicinati** al dispositivo (≤10 cm) → il sensore ToF rileva la presenza
2. **Parla** per 5 secondi → il microfono I²S registra audio di qualità
3. **Attendi** → Gemini elabora la richiesta e genera una risposta intelligente
4. **Ascolta** → la risposta viene riprodotta tramite TTS sulla cassa I²S
5. **Osserva** → i LED mostrano lo stato in tempo reale con animazioni colorate

---

## 🎨 Comportamento LED
- **Standby:** spento  
- **Ascolto (trigger ToF):** 2 lampeggi **ciano**  
- **Caricamento/Elaborazione:** effetto scorrimento **blu/violetto**  
- **Parlato (TTS):** “breathing” **blu/violetto**  

---

## 🔧 Hardware Richiesto
- Raspberry Pi Zero / Zero W (o simili)
- **INMP441** (microfono I²S)
- **MAX98357A** (amplificatore/cassa I²S)
- **VL53L0X** (Time-of-Flight ToF su I²C)
- **Anello WS2812** (35-36 LED consigliati)
- Alimentazione 5 V adeguata (i LED possono richiedere corrente)

### 🔌 Collegamenti (pin Raspberry)

![Schema Collegamenti Hardware](Collegamenti.png)
*Schema visuale dei collegamenti hardware per BOTMAKS*

**I²S (comune a mic + cassa):**
- **GPIO18 / BCLK** (pin 12) → BCLK di INMP441 e MAX98357A  
- **GPIO19 / LRCLK/WS** (pin 35) → LRC/WS di INMP441 e MAX98357A  

**Dati:**
- **GPIO21 / PCM_DOUT** (pin 40) → **DIN** (MAX98357A)  
- **DOUT (INMP441)** → il microfono espone SD/DOUT verso la Pi (lettura I²S)

**Alimentazioni:**
- **INMP441:** 3.3 V & GND  
- **MAX98357A:** 5 V & GND  

**ToF (I²C):**
- **SDA:** GPIO2 (pin 3)  
- **SCL:** GPIO3 (pin 5)  
- **VIN:** 3.3 V (o 5 V se il breakout lo consente), **GND**  
- **XSHUT:** consigliato pull-up a 3.3 V (10 k)

**LED WS2812 (via PWM):**
- **DIN:** **GPIO13** (pin 33, PWM1)  
- **5 V** e **GND** comuni alla Pi

---

## ⚙️ Sistema & Abilitazioni
Raspberry Pi OS (Lite consigliato). Abilita:
```bash
sudo raspi-config
# Interface Options → I2C → Enable
# Interface Options → Audio I2S abilitato (a seconda dell'immagine)
```

Config **/boot/firmware/config.txt** (esempio):
```ini
dtparam=i2c_arm=on
dtparam=i2s=on
dtoverlay=max98357a
# overlay microfono I²S (varia per immagine):
# dtoverlay=i2s-mic      # se presente
# (in alternativa: dtoverlay=googlevoicehat-soundcard)
```
> Non attivare più overlay audio in conflitto.

Riavvia:
```bash
sudo reboot
```

---

## 📦 Installazione Dipendenze
```bash
sudo apt update
sudo apt install -y python3-venv python3-pip ffmpeg alsa-utils i2c-tools
python3 -m venv ~/assistente
source ~/assistente/bin/activate
pip install -U pip
pip install requests adafruit-blinka adafruit-circuitpython-vl53l0x rpi-ws281x
```

---

## 🔑 Configurazione API Key Gemini
1. Accedi a **Google AI Studio** (Gemini API) con il tuo account Google.  
2. Crea una **API key**.  
3. **Non** committarla su GitHub. Salvala come variabile d’ambiente sul device.

Esempi:
```bash
# sessione corrente
export GEMINI_API_KEY="la_tua_chiave"
export MIC_DEVICE="hw:0,0"   # se il device ALSA è diverso, cambialo

# avvio manuale (serve root per i LED via /dev/mem)
sudo --preserve-env=GEMINI_API_KEY,MIC_DEVICE /home/botmaks/assistente/bin/python /home/botmaks/talk_5s_gemini_tof_led.py
```

---

## 🚀 Avvio Automatico come Servizio (systemd)
**1) Variabili in /etc/default**
```bash
sudo tee /etc/default/botmaks-assistant >/dev/null <<'EOF'
GEMINI_API_KEY=INSERISCI_LA_TUA_CHIAVE
MIC_DEVICE=hw:0,0
EOF
```

**2) Unità systemd**
```bash
sudo tee /etc/systemd/system/botmaks-assistant.service >/dev/null <<'EOF'
[Unit]
Description=Botmaks Assistant (ToF + LEDs + Gemini)
Wants=network-online.target
After=network-online.target sound.target

[Service]
Type=simple
User=root
WorkingDirectory=/home/botmaks
EnvironmentFile=/etc/default/botmaks-assistant
ExecStart=/home/botmaks/assistente/bin/python /home/botmaks/talk_5s_gemini_tof_led.py
Restart=on-failure
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
```

**3) Abilita & avvia**
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now botmaks-assistant
```

**4) Log & gestione**
```bash
sudo systemctl status botmaks-assistant
sudo journalctl -u botmaks-assistant -f
sudo systemctl restart botmaks-assistant
sudo systemctl stop botmaks-assistant
```

---

## 🎮 Uso Manuale
```bash
# con LED WS2812 su GPIO13 serve root
sudo --preserve-env=GEMINI_API_KEY,MIC_DEVICE /home/botmaks/assistente/bin/python /home/botmaks/talk_5s_gemini_tof_led.py
```
- Avvicina la mano a **≤10 cm** → 2 blink ciano → registrazione 5 s  
- LED **violetto** durante l’elaborazione → LED “respiro” blu/violetto mentre parla  
- Fine → LED spenti

---

## 🔍 Test e Diagnostica
**ToF:**
```bash
ls /dev/i2c*                 # deve esserci /dev/i2c-1
sudo i2cdetect -y 1          # dovrebbe mostrare 0x29
```

**Audio:**
```bash
arecord -l                   # vedi device capture
aplay -l                     # vedi device playback
# il tuo I²S spesso usa S32_LE; prova:
aplay -D hw:0,0 file_s32le.wav
# o conversione automatica:
aplay -D plughw:0,0 qualsiasi.wav
amixer sset Master 95% || amixer sset PCM 95%
```

**LED:**
- DIN → **GPIO13** (pin 33), 5 V, GND comune  
- Esegui script come **root** (rpi_ws281x usa /dev/mem)  
- Se errore `mmap()`/`ws2811_init`: riavvia e verifica che GPIO13 sia libero (noi usiamo **PWM1**, non confligge con I²S)

---

## 📁 Struttura Progetto
```
.
├── talk_5s_gemini_tof_led.py   # script principale
├── README.md
└── .gitignore                  # aggiungi qui file con segreti (mai la chiave!)
```

**Suggerimento .gitignore**
```
# segreti/ambiente
.env
*.key
*.pem
/etc/default/botmaks-assistant
```

---

## ⚠️ Note Importanti & Sicurezza
- Non committare **API key**.  
- GND **comune** tra tutti i moduli.  
- Per stabilità I²C su PCB: pull-up 4.7 k su SDA/SCL e condensatori di bypass vicino ai moduli.  
- Se l’audio accetta solo **S32_LE**, converti i WAV in S32_LE 48 kHz stereo o usa `plughw`.

---

## 📄 Licenza
Scegli la licenza che preferisci (es. MIT). Esempio:

```
MIT License — vedi LICENSE
```

---

## 🌟 Caratteristiche Tecniche

| Componente | Specifica | Note |
|------------|-----------|------|
| **Piattaforma** | Raspberry Pi Zero/Zero W | Compatibile con Pi 3/4 |
| **Sensore Prossimità** | VL53L0X ToF | Attivazione ≤10cm |
| **Audio Input** | INMP441 I²S | Qualità professionale |
| **Audio Output** | MAX98357A I²S | Amplificatore integrato |
| **Feedback Visivo** | WS2812 LED Ring | 35-36 LED programmabili |
| **AI Engine** | Google Gemini | STT + Conversazione + TTS |
| **Linguaggio** | Python 3 | Librerie ottimizzate |

## 🤝 Contributi

I contributi sono benvenuti! Per favore:
1. Fai un fork del progetto
2. Crea un branch per la tua feature (`git checkout -b feature/AmazingFeature`)
3. Committa le tue modifiche (`git commit -m 'Add some AmazingFeature'`)
4. Pusha sul branch (`git push origin feature/AmazingFeature`)
5. Apri una Pull Request

## 📞 Supporto

Se hai problemi o domande:
- Apri un **Issue** su GitHub
- Controlla la sezione **🔍 Test e Diagnostica** per problemi comuni
- Verifica che tutti i collegamenti hardware siano corretti

---

## 📺 Seguici per Altri Progetti

✍️ **Follow the Ingeimaks channel for new ESP32 projects and other electronics, Arduino and 3D printing content!**

🔗 [**Ingeimaks Channel**](https://github.com/Ingeimaks) - Scopri altri progetti innovativi!

---

<div align="center">

**⭐ Se questo progetto ti è stato utile, lascia una stella su GitHub! ⭐**

*Realizzato con ❤️ per la comunità Raspberry Pi*

</div>

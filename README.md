# KlipperLCD (for Elegoo Neptune 3 Pro / Plus / Max LCD screens)

Want to run Klipper on your Elegoo Neptune 3 Pro / Plus / Max and still use the native touchscreen?

**KlipperLCD** is a Python service connecting the Elegoo Neptune 3 DWIN/DGUS LCD touchscreen directly to [Klipper](https://www.klipper3d.org/) and [Moonraker](https://moonraker.readthedocs.io/).

---

## Features
* **Full Touchscreen Control**: Axis jogging, homing, temperatures, baby-stepping (Z-offset), fan & LED control, bed mesh calibration.
* **G-Code Console & Macros**: Send commands, run macros from a dropdown menu, and see Klipper output in real time.
* **Network & Wi-Fi Management (NEW)**:
  * View host IP addresses directly on the screen (`GET_IP`).
  * Display Wi-Fi signal strength and connection status (`WIFI_STATUS`).
  * Scan nearby Wi-Fi networks with signal level in dBm (`WIFI_SCAN`).
  * Connect to Wi-Fi by network index (`WIFI_CONNECT ID=1 PASS="secret"`) or by SSID (`WIFI_CONNECT SSID="MyHome" PASS="secret"`).
  * Auto-reconnect & fallback to the previous network if connection fails.
* **G-code Thumbnail Support**: Renders sliced model thumbnails during printing.
* **Configurable via CLI & Environment**: Set serial port, baud rate, Moonraker URL, and API key via command-line flags or environment variables without editing code.

<p float="left">
    <img src="img/boot_screen.PNG" height="300">
    <img src="img/main_screen.PNG" height="300">
    <img src="img/about_screen.PNG" height="300">
</p>

---

## Hardware Requirements
1. **Elegoo Neptune 3 LCD Touchscreen** (Pro, Plus, or Max).
2. **Host SBC / Single Board Computer**: Raspberry Pi, Orange Pi, TV-box (Rockchip/Amlogic), or any Linux PC running Klipper.
3. **Serial Connection**:
   * Direct wiring to an available SBC UART (e.g., `/dev/ttyAMA0`, `/dev/ttyS2`).
   * **OR** via a USB-to-UART converter (CH340, CP2102, FTDI) showing up as `/dev/ttyUSB0`.

---

## 1. Wiring the LCD

Remove the back-cover of the LCD by unscrewing the four screws.

### Option A: Direct UART on Raspberry Pi / SBC
| SBC Pin | LCD Wire Color | LCD Signal |
| :--- | :--- | :--- |
| **Pin 4 (5V)** | Black | 5V |
| **Pin 6 (GND)** | Red | GND |
| **GPIO 14 (TXD)** | Green | RX |
| **GPIO 15 (RXD)** | Yellow | TX |

<p float="left">
    <img src="img/rpi_conn.png" height="300">
    <img src="img/LCD_conn.png" height="300">
</p>

### Option B: USB-to-UART Converter
Cross RX and TX between the converter and the LCD:
| USB-UART Adapter | LCD Wire Color | LCD Signal |
| :--- | :--- | :--- |
| **5V** | Black | 5V |
| **GND** | Red | GND |
| **TXD** | Green | RX |
| **RXD** | Yellow | TX |

<p float="left">
    <img src="img/USB_conn.png" height="300">
    <img src="img/LCD_conn.png" height="300">
</p>

---

## 2. Flash LCD Screen Firmware

1. Format a micro-SD card (<= 32GB) as **FAT32** with 4096-byte allocation size.
2. Copy the firmware file `LCD/20240125.tft` (or `20240129.tft`) to the root of the micro-SD card.
3. Turn off power to the LCD.
4. Insert the micro-SD card into the slot located on the back of the LCD board.
5. Power on the LCD. Wait until the screen displays **`Update Successed!`**.
6. Power off, remove the micro-SD card, and reinstall the back cover.

---

## 3. Configure Klipper Host

### A. Enable Klipper Unix Domain Socket
Verify that Klipper provides the API socket `/home/<user>/printer_data/comms/klippy.sock`:

```bash
cat ~/printer_data/systemd/klipper.env
```
Ensure `KLIPPER_ARGS` contains `-a /home/<user>/printer_data/comms/klippy.sock`. If missing, add it and restart Klipper (`sudo systemctl restart klipper`).

### B. Add Network Macros to Klipper
Copy `network_macros.cfg` to your Klipper configuration folder:
```bash
cp network_macros.cfg ~/printer_data/config/
```
In your `printer.cfg`, add:
```gcode
[include network_macros.cfg]
```
Also ensure `[respond]` is present in your config (included automatically if you use `mainsail.cfg` or `fluidd.cfg`).

Restart Klipper to load the macros:
```bash
curl -X POST http://127.0.0.1:7125/printer/restart
```

---

## 4. Install KlipperLCD on Another Printer / SBC

### A. Clone Repository & Install Dependencies
```bash
cd ~
git clone https://github.com/1nt/KlipperLCD.git
cd KlipperLCD

# Install Python requirements (using system Python or your Klipper virtualenv)
pip install pyserial requests
```

### B. Find your Moonraker API Key
In **Mainsail** or **Fluidd**:
1. Click the **Settings (Gear icon)**.
2. Open the **Security** tab.
3. Copy your **API Key**.

*(Alternatively, ensure `127.0.0.1` is in `trusted_clients` inside `moonraker.conf`).*

---

## 5. Test Run

Launch KlipperLCD from the terminal:

```bash
# Using CLI arguments:
python3 main.py --port /dev/ttyUSB0 --api-key YOUR_MOONRAKER_KEY

# Or using environment variables:
export KLIPPER_LCD_PORT="/dev/ttyS2"
export MOONRAKER_API_KEY="YOUR_MOONRAKER_KEY"
python3 main.py
```

### Command Line Options
| Flag | Environment Variable | Default | Description |
| :--- | :--- | :--- | :--- |
| `--port` | `KLIPPER_LCD_PORT` | `/dev/ttyS2` | Serial port connected to LCD |
| `--baud` | `KLIPPER_LCD_BAUD` | `115200` | Baud rate |
| `--api-key` | `MOONRAKER_API_KEY` | *(empty)* | Moonraker API Key |
| `--url` | `MOONRAKER_URL` | `127.0.0.1` | Moonraker host URL |
| `--wifi-iface`| `KLIPPER_LCD_WIFI` | *(auto)* | Wireless interface name |

---

## 6. Install as a System Service (Auto-start on Boot)

1. Open `KlipperLCD.service` and adjust `User` and paths to match your system:
```ini
[Unit]
Description=KlipperLCD Service for Elegoo Neptune LCD
After=moonraker.service
Wants=moonraker.service

[Service]
Type=simple
User=pi
Restart=always
RestartSec=2
# Optional overrides:
# Environment="KLIPPER_LCD_PORT=/dev/ttyUSB0"
# Environment="MOONRAKER_API_KEY=YOUR_KEY"
ExecStart=/bin/sh -c 'exec /home/pi/klippy-env/bin/python /home/pi/KlipperLCD/main.py --port /dev/ttyUSB0 --api-key YOUR_KEY > /tmp/KlipperLCD.log 2>&1'

[Install]
WantedBy=multi-user.target
```

2. Install and enable the service:
```bash
sudo cp KlipperLCD.service /etc/systemd/system/KlipperLCD.service
sudo systemctl daemon-reload
sudo systemctl enable --now KlipperLCD.service
```

3. Check logs:
```bash
tail -f /tmp/KlipperLCD.log
```

---

## 7. Using Network & Wi-Fi Features

All network commands can be executed from the **Console** page on the touchscreen, selected from the **Macros dropdown**, or triggered from Mainsail/Fluidd.

### Display IP Addresses
Command: `GET_IP` (or `IP`)
```text
--- Network IP ---
wlan0: 192.168.1.104 (OpenWrt, -42dBm)
end0: Disconnected
Host: sb214
```

### Check Wi-Fi Status
Command: `WIFI_STATUS`
```text
--- WiFi Status ---
SSID: OpenWrt
IP: 192.168.1.104
State: COMPLETED (-41dBm)
MAC: e0:76:d0:3b:6a:7d
```

### Scan Wi-Fi Networks
Command: `WIFI_SCAN`
```text
Scanning WiFi networks...
--- WiFi Networks ---
1: Keenetic (-34dBm)
2: OpenWrt (-39dBm)
3: MyOffice (-45dBm)
4: HomeRouter (-64dBm)
Use: WIFI_CONNECT ID=1 PASS=...
```

### Connect to Wi-Fi
You can connect easily using the numbered ID from the scan (no need to type a long SSID on the touchscreen!):
```text
WIFI_CONNECT ID=1 PASS="secret_password"
```
Or by network name:
```text
WIFI_CONNECT SSID="Keenetic" PASS="secret_password"
```
*(For open networks without a password, omit the `PASS` parameter).*

* If connection succeeds, the IP is printed and saved to `/etc/netplan/30-wifis-dhcp.yaml` to persist across reboots.
* If connection fails (wrong password / timeout), KlipperLCD automatically reverts to the previous network so the printer never loses connection.

---

## License
Apache-2.0 License. Based on [joakimtoe/KlipperLCD](https://github.com/joakimtoe/KlipperLCD).

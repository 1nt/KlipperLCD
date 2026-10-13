import argparse
import sys
import time
import base64
import os
from threading import Thread
from datetime import timedelta

from printer import PrinterData
from lcd import LCD, _printerData
from network_helper import NetworkHelper, parse_connect_args

def parse_args():
    parser = argparse.ArgumentParser(description="KlipperLCD Service for Elegoo Neptune LCD")
    parser.add_argument(
        "--port",
        default=os.environ.get("KLIPPER_LCD_PORT", "/dev/ttyS2"),
        help="Serial port connected to the LCD (default: /dev/ttyS2 or $KLIPPER_LCD_PORT)"
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=int(os.environ.get("KLIPPER_LCD_BAUD", 115200)),
        help="Serial baud rate (default: 115200 or $KLIPPER_LCD_BAUD)"
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("MOONRAKER_API_KEY", ""),
        help="Moonraker API key (default: $MOONRAKER_API_KEY)"
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("MOONRAKER_URL", "127.0.0.1"),
        help="Moonraker host URL (default: 127.0.0.1 or $MOONRAKER_URL)"
    )
    parser.add_argument(
        "--wifi-iface",
        default=os.environ.get("KLIPPER_LCD_WIFI", None),
        help="WiFi network interface name (default: auto-detected or $KLIPPER_LCD_WIFI)"
    )
    return parser.parse_args()

class KlipperLCD ():
    def __init__(self, port="/dev/ttyS2", baud=115200, api_key="", url="127.0.0.1", wifi_iface=None):
        self.lcd = LCD(port, baud=baud, callback=self.lcd_callback)
        self.lcd.start()
        self.printer = PrinterData(api_key, URL=url, callback=self.printer_callback)
        self.running = False
        self.wait_probe = False
        self.thumbnail_inprogress = False
        self.net_helper = NetworkHelper(iface=wifi_iface)

        progress_bar = 1
        while self.printer.update_variable() == False:
            progress_bar += 5
            self.lcd.boot_progress(progress_bar)
            time.sleep(1)

        self.printer.init_Webservices()
        gcode_store = self.printer.get_gcode_store()
        self.lcd.write_gcode_store(gcode_store)

        macros = self.printer.get_macros()
        for net_macro in ["GET_IP", "WIFI_STATUS", "WIFI_SCAN", "WIFI_CONNECT"]:
            if net_macro not in macros:
                macros.append(net_macro)
        self.lcd.write_macros(macros)

        primary_ip = self.net_helper.get_primary_ip()
        print(self.printer.MACHINE_SIZE)
        print(self.printer.SHORT_BUILD_VERSION)
        self.lcd.write("information.size.txt=\"%s\"" % self.printer.MACHINE_SIZE)
        self.lcd.write("information.sversion.txt=\"%s (%s)\"" % (self.printer.SHORT_BUILD_VERSION, primary_ip))
        self.lcd.write("page main")

        # Display greeting with network IP in LCD console
        self.write_console_lines(f"KlipperLCD ready\nIP: {primary_ip}")

    def start(self):
        print("KlipperLCD start")
        self.running = True
        Thread(target=self.periodic_update).start()

    def update(self):
        if self.wait_probe:
            print("Zpos=%f, Zoff=%f" % (self.printer.current_position.z, self.printer.BABY_Z_VAR))
            if self.printer.ishomed():
                    self.wait_probe = False
                    print("IsHomed")
                    self.lcd.probe_mode_start()

        self.printer.update_variable()
        data = _printerData()
        data.hotend_target = self.printer.thermalManager['temp_hotend'][0]['target']
        data.hotend        = self.printer.thermalManager['temp_hotend'][0]['celsius']
        data.bed_target    = self.printer.thermalManager['temp_bed']['target']
        data.bed           = self.printer.thermalManager['temp_bed']['celsius']
        data.state         = self.printer.getState()
        data.percent       = self.printer.getPercent()
        data.duration      = self.printer.duration()
        data.remaining     = self.printer.remain()
        data.print_time    = self.printer.print_time
        data.feedrate      = self.printer.print_speed
        data.flowrate      = self.printer.flow_percentage
        data.fan           = self.printer.thermalManager['fan_speed'][0]
        data.led           = self.printer.led_percentage
        data.x_pos         = self.printer.current_position.x
        data.y_pos         = self.printer.current_position.y
        data.z_pos         = self.printer.current_position.z
        data.z_offset      = self.printer.BABY_Z_VAR
        data.z_requested   = self.printer.z_requested
        data.file_name     = self.printer.file_name
        data.max_velocity           = self.printer.max_velocity          
        data.max_accel              = self.printer.max_accel
        data.minimum_cruise_ratio   = self.printer.minimum_cruise_ratio
        data.square_corner_velocity = self.printer.square_corner_velocity

        self.lcd.data_update(data)

    def periodic_update(self):
        while self.running:
            self.update()
            time.sleep(2)

    def write_console_lines(self, text):
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        for line in reversed(lines):
            self.lcd.write_console(line)
            time.sleep(0.01)

    def run_net_get_ip(self):
        info = self.net_helper.get_ip_info()
        self.write_console_lines(info)
        for line in info.splitlines():
            if line.strip():
                self.printer.sendGCode(f'RESPOND MSG="{line.strip()}"')

    def run_net_wifi_status(self):
        info = self.net_helper.get_wifi_status()
        self.write_console_lines(info)
        for line in info.splitlines():
            if line.strip():
                self.printer.sendGCode(f'RESPOND MSG="{line.strip()}"')

    def run_net_wifi_scan(self):
        self.lcd.write_console("Scanning WiFi networks...")
        self.printer.sendGCode('RESPOND MSG="Scanning WiFi networks..."')
        res = self.net_helper.scan_wifi()
        self.write_console_lines(res)
        for line in res.splitlines():
            if line.strip():
                self.printer.sendGCode(f'RESPOND MSG="{line.strip()}"')

    def run_net_wifi_connect(self, cmd):
        target, password = parse_connect_args(cmd)
        if not target:
            usage = "Usage: WIFI_CONNECT ID=1 PASS=\"pass\""
            self.lcd.write_console(usage)
            self.printer.sendGCode(f'RESPOND TYPE=error MSG="{usage}"')
            return

        self.lcd.write_console(f"Connecting to {target}...")
        self.printer.sendGCode(f'RESPOND MSG="Connecting to {target}..."')
        res = self.net_helper.connect_wifi(target, password)
        self.write_console_lines(res)
        for line in res.splitlines():
            if line.strip():
                self.printer.sendGCode(f'RESPOND MSG="{line.strip()}"')

    def handle_network_console_cmd(self, cmd):
        c = cmd.upper()
        if c in ("GET_IP", "IP", "SHOW_IP"):
            Thread(target=self.run_net_get_ip, daemon=True).start()
            return True
        elif c in ("WIFI_SCAN", "SCAN_WIFI"):
            Thread(target=self.run_net_wifi_scan, daemon=True).start()
            return True
        elif c in ("WIFI_STATUS", "STATUS_WIFI"):
            Thread(target=self.run_net_wifi_status, daemon=True).start()
            return True
        elif c.startswith("WIFI_CONNECT"):
            Thread(target=self.run_net_wifi_connect, args=(cmd,), daemon=True).start()
            return True
        return False

    def printer_callback(self, data, data_type):
        if data_type == 'response':
            clean = data.replace("// ", "").strip()
            if clean == "__KLIPPERLCD_NET_GET_IP__":
                Thread(target=self.run_net_get_ip, daemon=True).start()
                return
            elif clean == "__KLIPPERLCD_NET_WIFI_SCAN__":
                Thread(target=self.run_net_wifi_scan, daemon=True).start()
                return
            elif clean == "__KLIPPERLCD_NET_WIFI_STATUS__":
                Thread(target=self.run_net_wifi_status, daemon=True).start()
                return
            elif clean.startswith("__KLIPPERLCD_NET_WIFI_CONNECT__"):
                Thread(target=self.run_net_wifi_connect, args=(clean,), daemon=True).start()
                return

        msg = self.lcd.format_console_data(data, data_type)
        if msg:
            self.lcd.write_console(msg)

    def show_thumbnail(self):
        if self.printer.file_path and (self.printer.file_name or self.lcd.files[self.lcd.selected_file]):
            file_name = ""
            if self.lcd.files:
                file_name = self.lcd.files[self.lcd.selected_file]
            elif self.printer.file_name:
                file_name = self.printer.file_name
            else:
                print("ERROR: gcode file not known")
            
            file = self.printer.file_path + "/" + file_name
            file = os.path.expanduser(file)

            # Reading file
            print(file)
            f = open(file, "r")
            if not f:
                f.close()
                print("File could not be opened: %s" % file)
                return
            buf = f.readlines()
            if not f:
                f.close()
                print("File could not be read")
                return

            f.close()
            thumbnail_found = False
            b64 = ""

            for line in buf:
                if 'thumbnail begin' in line:
                    thumbnail_found = True
                elif 'thumbnail end' in line:
                    thumbnail_found = False
                    break
                elif thumbnail_found:
                    b64 += line.strip(' \t\n\r;')
        
            if len(b64):
                # Decode Base64
                img = base64.b64decode(b64)        
                
                # Write thumbnail to LCD
                self.lcd.write_thumbnail(img)
            else:
                self.lcd.clear_thumbnail()
                print("Aborting thumbnail, no image found")
        else:
            print("File path or name to gcode-files missing")
        
        self.thumbnail_inprogress = False

    def lcd_callback(self, evt, data=None):
        if evt == self.lcd.evt.HOME:
            self.printer.home(data)
        elif evt == self.lcd.evt.MOVE_X:
            self.printer.moveRelative('X', data, 4000)
        elif evt == self.lcd.evt.MOVE_Y:
            self.printer.moveRelative('Y', data, 4000)
        elif evt == self.lcd.evt.MOVE_Z:
            self.printer.moveRelative('Z', data, 600)
        elif evt == self.lcd.evt.MOVE_E:
            print(data)
            self.printer.moveRelative('E', data[0], data[1])
        elif evt == self.lcd.evt.Z_OFFSET:
            self.printer.setZOffset(data)
        elif evt == self.lcd.evt.NOZZLE:
            self.printer.setExtTemp(data)
        elif evt == self.lcd.evt.BED:
            self.printer.setBedTemp(data)
        elif evt == self.lcd.evt.FILES:
            files = self.printer.GetFiles(True)
            return files
        elif evt == self.lcd.evt.PRINT_START:
            self.printer.openAndPrintFile(data)
            if self.thumbnail_inprogress == False:
                self.thumbnail_inprogress = True
        elif evt == self.lcd.evt.THUMBNAIL:
            if self.thumbnail_inprogress == False:
                self.thumbnail_inprogress = True
                Thread(target=self.show_thumbnail).start()
        elif evt == self.lcd.evt.PRINT_STATUS:
            pass
        elif evt == self.lcd.evt.PRINT_STOP:
            self.printer.cancel_job()
        elif evt == self.lcd.evt.PRINT_PAUSE:
            self.printer.pause_job()
        elif evt == self.lcd.evt.PRINT_RESUME:
            self.printer.resume_job()
        elif evt == self.lcd.evt.PRINT_SPEED:
            self.printer.set_print_speed(data)
        elif evt == self.lcd.evt.FLOW:
            self.printer.set_flow(data)
        elif evt == self.lcd.evt.PROBE:
            if data == None:
                self.printer.probe_calibrate()
                self.wait_probe = True
            else:
                self.printer.probe_adjust(data)
                self.update()
        elif evt == self.lcd.evt.PROBE_COMPLETE:
            self.wait_probe = False
            print("Save settings!")
            self.printer.sendGCode('ACCEPT')
            self.printer.sendGCode('G1 F1000 Z15.0')
            print("Calibrate!")
            self.lcd.write("pretemp.nozzle.txt=\"%d\"" % self.printer.thermalManager['temp_hotend'][0]['target'])
            self.lcd.write("pretemp.bed.txt=\"%d\"" % self.printer.thermalManager['temp_bed'][0]['target'])
            self.printer.sendGCode('M104 S120')
            self.printer.sendGCode('M140 S65')
            self.printer.sendGCode('G4 S10')
            self.printer.sendGCode('M190 S65')
            self.printer.sendGCode('M109 S120')
            self.printer.sendGCode('BED_MESH_CALIBRATE PROFILE=default METHOD=automatic')
            self.printer.sendGCode('G28 Z')
            self.printer.probe_calibrate()
        elif evt == self.lcd.evt.PROBE_BACK:
            print("BACK!")
            self.printer.sendGCode('ACCEPT')
            self.printer.sendGCode('G1 F1000 Z15.0')
            self.printer.sendGCode('SAVE_CONFIG')
        elif evt == self.lcd.evt.BED_MESH:
            pass
        elif evt == self.lcd.evt.LIGHT:
            self.printer.set_led(data)
        elif evt == self.lcd.evt.FAN:
            self.printer.set_fan(data)
        elif evt == self.lcd.evt.MOTOR_OFF:
            self.printer.sendGCode('M18')
        elif evt == self.lcd.evt.ACCEL:
            self.printer.sendGCode("SET_VELOCITY_LIMIT ACCEL=%d" % data)
            self.update()
        elif evt == self.lcd.evt.MIN_CRUISE_RATIO:
            self.printer.sendGCode("SET_VELOCITY_LIMIT MINIMUM_CRUISE_RATIO=%.2f" % data)
            self.update()
        elif evt == self.lcd.evt.VELOCITY:
            self.printer.sendGCode("SET_VELOCITY_LIMIT VELOCITY=%d" % data)
            self.update()
        elif evt == self.lcd.evt.SQUARE_CORNER_VELOCITY:
            self.printer.sendGCode("SET_VELOCITY_LIMIT SQUARE_CORNER_VELOCITY=%.1f" % data)
            self.update()
        elif evt == self.lcd.evt.CONSOLE:
            cmd = data.strip() if data else ""
            if not self.handle_network_console_cmd(cmd):
                self.printer.sendGCode(data)
        else:
            print("lcd_callback event not recognised %d" % evt)

if __name__ == "__main__":
    args = parse_args()
    x = KlipperLCD(
        port=args.port,
        baud=args.baud,
        api_key=args.api_key,
        url=args.url,
        wifi_iface=args.wifi_iface
    )
    x.start()

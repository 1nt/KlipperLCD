import subprocess
import json
import time
import socket
import os
import re

def parse_connect_args(cmd_str):
    s = re.sub(r'^(WIFI_CONNECT|__KLIPPERLCD_NET_WIFI_CONNECT__)\s*', '', cmd_str, flags=re.IGNORECASE).strip()
    if not s:
        return "", ""

    target = ""
    password = ""

    m_target = re.search(r'(?:TARGET|SSID|ID)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|(\S+))', s, re.IGNORECASE)
    if m_target:
        target = m_target.group(1) or m_target.group(2) or m_target.group(3) or ""

    m_pass = re.search(r'(?:PASS|PASSWORD)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|(\S+))', s, re.IGNORECASE)
    if m_pass:
        password = m_pass.group(1) or m_pass.group(2) or m_pass.group(3) or ""

    if not target:
        parts = s.split(maxsplit=1)
        if parts:
            target = parts[0].strip(' "\'')
            if len(parts) > 1 and not password:
                m2 = re.search(r'(?:PASS|PASSWORD)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|(\S+))', parts[1], re.IGNORECASE)
                if m2:
                    password = m2.group(1) or m2.group(2) or m2.group(3) or ""
                else:
                    password = parts[1].strip(' "\'')

    return target, password

class NetworkHelper:
    def __init__(self, iface=None):
        self.last_scan = {}  # str(idx) -> ssid
        self.wlan_iface = iface or self._detect_wlan_iface()

    def _detect_wlan_iface(self):
        try:
            for dev in sorted(os.listdir("/sys/class/net")):
                if dev.startswith("wlan") or os.path.exists(f"/sys/class/net/{dev}/wireless"):
                    return dev
        except Exception:
            pass
        return "wlan0"

    def _run_cmd(self, cmd, timeout=10):
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return res.stdout.strip()
        except Exception:
            return ""

    def _wpa_cmd(self, *args, timeout=10):
        cmd = ["sudo", "/usr/sbin/wpa_cli", "-i", self.wlan_iface] + list(args)
        return self._run_cmd(cmd, timeout=timeout)

    def get_ip_info(self):
        lines = ["--- Network IP ---"]
        hostname = socket.gethostname()

        raw_ip = self._run_cmd(["ip", "-j", "addr", "show"])
        try:
            ifaces = json.loads(raw_ip)
            for iface in ifaces:
                name = iface.get("ifname", "")
                if name in ("lo", "sit0", "ip6tnl0"):
                    continue
                state = iface.get("operstate", "UNKNOWN")
                v4_ips = [a.get("local") for a in iface.get("addr_info", []) if a.get("family") == "inet"]

                if name == self.wlan_iface:
                    if v4_ips:
                        ip_str = ", ".join(v4_ips)
                        ssid = self.get_current_ssid()
                        rssi = self.get_signal_rssi()
                        sig_info = ""
                        if ssid and rssi:
                            sig_info = f" ({ssid}, {rssi}dBm)"
                        elif ssid:
                            sig_info = f" ({ssid})"
                        lines.append(f"{name}: {ip_str}{sig_info}")
                    else:
                        lines.append(f"{name}: Disconnected ({state})")
                elif name.startswith("e") or name.startswith("eth"):
                    if v4_ips:
                        lines.append(f"{name}: {', '.join(v4_ips)}")
                    else:
                        lines.append(f"{name}: Disconnected")
                else:
                    if v4_ips:
                        lines.append(f"{name}: {', '.join(v4_ips)}")
        except Exception as e:
            lines.append(f"Error reading IP: {e}")

        lines.append(f"Host: {hostname}")
        return "\n".join(lines)

    def get_primary_ip(self):
        raw_ip = self._run_cmd(["ip", "-j", "addr", "show"])
        try:
            ifaces = json.loads(raw_ip)
            for iface in ifaces:
                name = iface.get("ifname", "")
                if name in (self.wlan_iface, "end0", "eth0"):
                    for a in iface.get("addr_info", []):
                        if a.get("family") == "inet":
                            return a.get("local")
        except Exception:
            pass
        return "No IP"

    def get_current_ssid(self):
        out = self._wpa_cmd("status")
        for line in out.splitlines():
            if line.startswith("ssid="):
                return line.split("=", 1)[1]
        return ""

    def get_signal_rssi(self):
        out = self._wpa_cmd("signal_poll")
        for line in out.splitlines():
            if line.startswith("RSSI="):
                return line.split("=", 1)[1]
        return ""

    def get_wifi_status(self):
        out = self._wpa_cmd("status")
        status_dict = {}
        for line in out.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                status_dict[k.strip()] = v.strip()

        ssid = status_dict.get("ssid", "Not connected")
        ip = status_dict.get("ip_address", "No IP")
        state = status_dict.get("wpa_state", "UNKNOWN")
        rssi = self.get_signal_rssi()
        sig_str = f" ({rssi}dBm)" if rssi else ""

        lines = [
            "--- WiFi Status ---",
            f"SSID: {ssid}",
            f"IP: {ip}",
            f"State: {state}{sig_str}",
            f"MAC: {status_dict.get('address', 'unknown')}"
        ]
        return "\n".join(lines)

    def decode_raw_ssid(self, raw):
        if not raw:
            return ""
        try:
            if "\\x" in raw:
                raw_bytes = bytes(raw, "utf-8").decode("unicode_escape").encode("latin1")
                return raw_bytes.decode("utf-8", errors="replace")
        except Exception:
            pass
        return raw

    def scan_wifi(self):
        self._wpa_cmd("scan")
        time.sleep(2)
        out = self._wpa_cmd("scan_results")
        lines = out.splitlines()
        if len(lines) <= 1:
            return "WiFi Scan: No networks found."

        raw_results = []
        for l in lines[1:]:
            parts = l.split("\t")
            if len(parts) >= 5:
                freq = parts[1]
                try:
                    signal = int(parts[2])
                except ValueError:
                    signal = -99
                flags = parts[3]
                raw_ssid = parts[4]
                ssid = self.decode_raw_ssid(raw_ssid).strip()
                if not ssid or "\x00" in ssid:
                    continue
                band = "5G" if int(freq) > 3000 else "2.4G"
                raw_results.append({
                    "ssid": ssid,
                    "signal": signal,
                    "band": band,
                    "flags": flags
                })

        dedup = {}
        for r in raw_results:
            s = r["ssid"]
            if s not in dedup or r["signal"] > dedup[s]["signal"]:
                dedup[s] = r

        sorted_networks = sorted(dedup.values(), key=lambda x: x["signal"], reverse=True)
        self.last_scan = {}

        res_lines = ["--- WiFi Networks ---"]
        for idx, net in enumerate(sorted_networks[:7], 1):
            self.last_scan[str(idx)] = net["ssid"]
            lock = " [open]" if "WPA" not in net["flags"] else ""
            res_lines.append(f"{idx}: {net['ssid']} ({net['signal']}dBm{lock})")

        res_lines.append("Use: WIFI_CONNECT ID=1 PASS=...")
        return "\n".join(res_lines)

    def connect_wifi(self, target, password=None):
        target = str(target).strip()
        ssid = target
        if target in self.last_scan:
            ssid = self.last_scan[target]
        elif target.isdigit() and target not in self.last_scan:
            return f"Error: Network ID {target} not in scan list. Run WIFI_SCAN first."

        if not ssid:
            return "Error: SSID is empty. Usage: WIFI_CONNECT SSID=name PASS=pass"

        net_list = self._wpa_cmd("list_networks")
        old_id = None
        for line in net_list.splitlines():
            if "[CURRENT]" in line:
                old_id = line.split()[0]
                break

        new_id = self._wpa_cmd("add_network")
        if not new_id.isdigit():
            return f"Error adding network: {new_id}"

        self._wpa_cmd("set_network", new_id, "ssid", f'"{ssid}"')

        if password and len(password.strip()) > 0:
            self._wpa_cmd("set_network", new_id, "psk", f'"{password.strip()}"')
        else:
            self._wpa_cmd("set_network", new_id, "key_mgmt", "NONE")

        self._wpa_cmd("enable_network", new_id)
        self._wpa_cmd("select_network", new_id)

        connected = False
        new_ip = None
        for _ in range(15):
            time.sleep(1)
            st = self._wpa_cmd("status")
            if "wpa_state=COMPLETED" in st:
                for l in st.splitlines():
                    if l.startswith("ip_address="):
                        new_ip = l.split("=", 1)[1]
                        connected = True
                        break
            if connected and new_ip:
                break

        if connected and new_ip:
            self.save_netplan(ssid, password)
            return f"Connected to {ssid}!\nIP: {new_ip}"
        else:
            self._wpa_cmd("remove_network", new_id)
            if old_id:
                self._wpa_cmd("select_network", old_id)
                self._wpa_cmd("enable_network", old_id)
            return f"Failed to connect to {ssid}.\nRestored previous connection."

    def save_netplan(self, ssid, password=None):
        try:
            iface = self.wlan_iface
            content = f"# Updated by KlipperLCD\nnetwork:\n  wifis:\n    {iface}:\n      dhcp4: yes\n      dhcp6: yes\n      access-points:\n        \"{ssid}\":\n"
            if password:
                content += f"          password: \"{password}\"\n"
            else:
                content += "          {}\n"

            tmp_path = "/tmp/30-wifis-dhcp.yaml"
            with open(tmp_path, "w") as f:
                f.write(content)
            self._run_cmd(["sudo", "cp", tmp_path, "/etc/netplan/30-wifis-dhcp.yaml"])
            self._run_cmd(["sudo", "chmod", "600", "/etc/netplan/30-wifis-dhcp.yaml"])
        except Exception as e:
            print(f"Error saving netplan: {e}")

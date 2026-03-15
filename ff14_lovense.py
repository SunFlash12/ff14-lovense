"""
FF14 Lovense Bridge v2.0 - Dalamud Edition
Works with XIVLauncher/Dalamud plugins for precise game event detection.

Two modes:
1. Dalamud Plugin Mode: Uses DalamudPlugin webhook/websocket for real-time combat data
2. ACT/Network Log Mode: Parses FF14 network log for events (fallback)

Recommended Dalamud plugins:
- PostNamazu / Triggernometry: Can send webhooks on custom triggers
- IINACT: ACT alternative that runs inside Dalamud, exposes websocket
- ChatBubbles / Chat2: For chat log access
"""

import os
import re
import sys
import time
import json
import struct
import threading
import requests
import urllib3
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

urllib3.disable_warnings()

# ============================================================
# CONFIG
# ============================================================
LOVENSE_DOMAIN = "https://192-168-0-231.lovense.club:30010"
WEBHOOK_PORT = 8069  # Local webhook server port for Dalamud to POST to

# Toy IDs (auto-detected on startup)
TOYS = {}

# FF14 Network log path (Dalamud writes these)  
NETWORK_LOG_DIR = Path.home() / "AppData" / "Roaming" / "Advanced Combat Tracker" / "FFXIVLogs"
DALAMUD_LOG_DIR = Path.home() / "AppData" / "Roaming" / "XIVLauncher" / "dalamud" / "logs"

# ============================================================
# LOVENSE CONTROLLER (same as v1)
# ============================================================
class LovenseController:
    def __init__(self, domain):
        self.domain = domain
        self.current_intensity = {}
        self.last_command_time = 0
        self.min_interval = 0.3
        self.connected = False
    
    def connect(self):
        toys = self.get_toys()
        if toys:
            self.connected = True
            global TOYS
            for tid, t in toys.items():
                TOYS[t["name"]] = tid
                print(f"  {t['name']}: {tid} ({t['battery']}%)")
            return True
        return False
    
    def send(self, toy_id, command):
        now = time.time()
        if now - self.last_command_time < self.min_interval:
            return None
        self.last_command_time = now
        try:
            cmd = {**command, "toy": toy_id or "", "apiVer": 1}
            r = requests.post(f"{self.domain}/command", json=cmd, timeout=3, verify=False)
            return r.json()
        except Exception as e:
            return None
    
    def vibrate(self, intensity, duration=5, toy=""):
        intensity = max(0, min(20, int(intensity)))
        self.current_intensity[toy] = intensity
        return self.send(toy, {"command": "Function", "action": f"Vibrate:{intensity}", "timeSec": duration})
    
    def pattern(self, strengths, duration=10, toy=""):
        return self.send(toy, {"command": "Pattern", "rule": "V:1;F:v;S:100#", "strength": strengths, "timeSec": duration})
    
    def preset(self, name, duration=10, toy=""):
        return self.send(toy, {"command": "Preset", "name": name, "timeSec": duration})
    
    def stop(self, toy=""):
        self.current_intensity[toy] = 0
        return self.send(toy, {"command": "Function", "action": "Vibrate:0", "timeSec": 0})
    
    def stop_all(self):
        self.send("", {"command": "Function", "action": "Vibrate:0", "timeSec": 0})
    
    def get_toys(self):
        try:
            r = requests.post(f"{self.domain}/command", json={"command": "GetToys"}, timeout=5, verify=False)
            data = r.json()
            if data.get("code") == 200:
                return json.loads(data["data"]["toys"])
        except:
            pass
        return {}


# ============================================================
# EVENT MAPPER (enhanced for Dalamud precision)
# ============================================================
class EventMapper:
    def __init__(self, controller):
        self.ctrl = controller
        self.combo_counter = 0
        self.last_event = None
        self.last_event_time = 0
        self.player_hp_pct = 100
        self.in_combat = False
        self.in_cutscene = False
        self.ambient_intensity = 0  # Background buzz level
    
    def handle(self, event_type, value=0, **kwargs):
        now = time.time()
        if event_type == self.last_event and now - self.last_event_time < 2:
            self.combo_counter = min(self.combo_counter + 1, 8)
        else:
            self.combo_counter = 0
        self.last_event = event_type
        self.last_event_time = now
        combo = self.combo_counter * 2
        
        edge = TOYS.get("edge", "")
        diamo = TOYS.get("diamo", "")
        gemini = TOYS.get("gemini", "")
        
        # === PRECISE COMBAT EVENTS (from Dalamud) ===
        
        if event_type == "hp_update":
            # Continuous HP tracking - intensity based on missing HP
            hp_pct = value
            self.player_hp_pct = hp_pct
            if hp_pct < 30:
                self.ctrl.vibrate(16 + combo, 3, edge)
            elif hp_pct < 50:
                self.ctrl.vibrate(12, 3, edge)
            elif hp_pct < 75:
                self.ctrl.vibrate(6, 3, edge)
            print(f"  ❤️ HP: {hp_pct}% → intensity {20 - hp_pct // 5}")
        
        elif event_type == "damage_taken":
            damage = value
            max_hp = kwargs.get("max_hp", 50000)
            pct = min(100, (damage / max(1, max_hp)) * 100)
            intensity = min(20, max(3, int(pct / 5) + 3 + combo))
            print(f"  ⚔️ Damage: {damage} ({pct:.0f}% HP) → {intensity}")
            self.ctrl.vibrate(intensity, 2, edge)
            if pct > 20:  # Big hit = diamo too
                self.ctrl.vibrate(min(intensity - 3, 15), 2, diamo)
        
        elif event_type == "damage_dealt":
            # Satisfying feedback for YOUR damage
            intensity = min(8, max(2, value // 10000 + 2))
            self.ctrl.vibrate(intensity, 1, diamo)
        
        elif event_type == "dot_tick":
            # Damage over time - persistent low buzz
            self.ctrl.vibrate(5 + combo, 2, edge)
        
        elif event_type == "vuln_stack":
            # Vulnerability stacks = increasing danger
            stacks = value
            print(f"  ⚠️ Vuln stacks: {stacks}")
            self.ctrl.vibrate(6 + stacks * 3, 5, edge)
        
        elif event_type == "tankbuster":
            print(f"  🛡️ TANKBUSTER → intense burst")
            self.ctrl.vibrate(20, 3, edge)
            self.ctrl.vibrate(15, 3, diamo)
        
        elif event_type == "aoe_warning":
            print(f"  🔴 AOE WARNING → pulse")
            self.ctrl.pattern("0;8;15;8;0;8;15;8;0", 3, edge)
        
        elif event_type == "stack_marker":
            print(f"  🔵 Stack marker → building")
            self.ctrl.pattern("5;8;11;14;17;20", 3)
        
        elif event_type == "proximity_marker":
            print(f"  ⭕ Proximity → escalating")
            self.ctrl.pattern("3;6;9;12;15;18;20;20;20", 5, edge)
        
        elif event_type == "death":
            print(f"  💀 DEATH")
            self.ctrl.vibrate(20, 1)
            time.sleep(1.5)
            self.ctrl.stop_all()
        
        elif event_type == "raise":
            print(f"  ✨ Raised! → celebration buzz")
            self.ctrl.pattern("0;5;10;15;10;5;0;5;10;15;20", 5)
        
        elif event_type == "heal_received":
            intensity = min(10, max(2, value // 5000 + 2))
            self.ctrl.pattern("3;5;7;5;3", 3, edge)
        
        elif event_type == "limit_break":
            level = kwargs.get("level", 1)
            print(f"  ⚡ LIMIT BREAK L{level}")
            self.ctrl.vibrate(20, 5 + level * 3)
            if gemini:
                self.ctrl.vibrate(20, 5 + level * 3, gemini)
        
        elif event_type == "boss_cast":
            cast_name = kwargs.get("name", "unknown")
            print(f"  🔥 Boss casting: {cast_name}")
            self.ctrl.pattern("5;10;15;18;20;20;20", 5, edge)
            self.ctrl.vibrate(10, 5, diamo)
        
        elif event_type == "enrage":
            print(f"  💀🔥 ENRAGE → EVERYTHING MAX")
            self.ctrl.vibrate(20, 30, edge)
            self.ctrl.vibrate(20, 30, diamo)
            if gemini:
                self.ctrl.vibrate(20, 30, gemini)
        
        elif event_type == "duty_complete":
            print(f"  🎉 DUTY COMPLETE → fireworks!")
            self.ctrl.preset("fireworks", 15)
        
        elif event_type == "wipe":
            print(f"  💀💀💀 WIPE")
            self.ctrl.stop_all()
        
        # === COMBAT STATE ===
        elif event_type == "combat_start":
            self.in_combat = True
            print(f"  ⚔️ Combat started")
            self.ctrl.vibrate(3, 10, edge)  # Low ambient combat buzz
        
        elif event_type == "combat_end":
            self.in_combat = False
            print(f"  🕊️ Combat ended")
            self.ctrl.pattern("5;3;2;1;0", 5)
        
        # === CUTSCENE/STORY ===
        elif event_type == "cutscene_start":
            self.in_cutscene = True
            print(f"  🎬 Cutscene started → ambient")
            self.ctrl.vibrate(2, 30)
        
        elif event_type == "cutscene_end":
            self.in_cutscene = False
            self.ctrl.stop_all()
        
        # === SOCIAL ===
        elif event_type == "emote":
            emote_name = kwargs.get("name", "")
            emote_map = {
                "hug": ("🤗", "5;8;10;8;5;3", 5),
                "kiss": ("💋", "3;5;8;12;15;18;15;12;8;5", 8),
                "pet": ("🐾", "4;6;4;6;4", 4),
                "slap": ("👋", None, 0),  # Special handling
                "spank": ("🍑", None, 0),
                "dance": ("💃", None, 0),
                "dote": ("🥰", "5;8;10;12;10;8;5", 6),
                "comfort": ("💕", "3;5;7;5;3;5;7;5;3", 8),
                "blowkiss": ("😘", "5;10;15;10;5", 5),
            }
            if emote_name in emote_map:
                emoji, pattern_str, dur = emote_map[emote_name]
                print(f"  {emoji} Emote: {emote_name}")
                if emote_name == "slap":
                    self.ctrl.vibrate(18, 1)
                elif emote_name == "spank":
                    self.ctrl.vibrate(20, 1)
                    time.sleep(1)
                    self.ctrl.pattern("0;15;0;15;0;15", 5)
                elif emote_name == "dance":
                    self.ctrl.preset("wave", 15)
                elif pattern_str:
                    self.ctrl.pattern(pattern_str, dur)
        
        # === CHAT/ERP ===
        elif event_type == "chat_trigger":
            keyword_type = kwargs.get("keyword_type", "mild")
            if keyword_type == "mild":
                self.ctrl.vibrate(8 + combo, 5, edge)
                self.ctrl.vibrate(4 + combo, 5, diamo)
            elif keyword_type == "intense":
                self.ctrl.pattern("10;14;18;20;18;14;10;14;18;20", 10, edge)
                self.ctrl.vibrate(14 + combo, 10, diamo)
            elif keyword_type == "climax":
                self.ctrl.vibrate(20, 15, edge)
                self.ctrl.vibrate(20, 15, diamo)
                if gemini:
                    self.ctrl.vibrate(20, 15, gemini)
            elif keyword_type == "tease":
                self.ctrl.pattern("5;8;12;15;18;15;12;8;5;0;0;0;5;8;12;15;18;20", 15, edge)
            elif keyword_type == "rough":
                self.ctrl.preset("earthquake", 8, edge)
        
        # === ZONE/MUSIC ===
        elif event_type == "zone_change":
            zone = kwargs.get("zone", "")
            print(f"  🗺️ Zone: {zone}")
            # Light buzz on zone change as haptic feedback
            self.ctrl.vibrate(3, 2)


# ============================================================
# WEBHOOK SERVER (for Dalamud plugins to POST events)
# ============================================================
class WebhookHandler(BaseHTTPRequestHandler):
    mapper = None
    
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')
        
        try:
            data = json.loads(body)
            event_type = data.get("event", data.get("type", ""))
            value = data.get("value", data.get("amount", 0))
            
            if self.mapper and event_type:
                self.mapper.handle(event_type, value, **data)
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        except Exception as e:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(str(e).encode())
    
    def log_message(self, format, *args):
        pass  # Silence HTTP logs


# ============================================================
# NETWORK LOG PARSER (fallback for non-webhook mode)
# ============================================================
class NetworkLogParser:
    """Parse FF14 ACT/IINACT network logs for combat events."""
    
    # FF14 network log opcodes
    OPCODES = {
        "00": "chat",           # Chat message
        "15": "ability_single", # Single-target ability
        "16": "ability_aoe",    # AOE ability
        "1A": "buff_gain",      # Gained a buff/debuff
        "1E": "buff_lose",      # Lost a buff/debuff  
        "19": "gauge_update",   # Job gauge update
        "21": "cast_start",     # Cast bar started
        "23": "cast_cancel",    # Cast cancelled
        "25": "death",          # Something died
        "03": "zone_change",    # Changed zone
        "26": "hp_update",      # HP/MP update
    }
    
    # Chat type codes
    CHAT_TYPES = {
        "000E": "party",
        "000D": "tell_receive",
        "000C": "tell_send",
        "000A": "say",
        "001E": "yell",
        "0039": "emote",
    }
    
    def __init__(self, mapper):
        self.mapper = mapper
        self.player_name = None
        self.player_id = None
    
    def parse_line(self, line):
        """Parse a single network log line."""
        parts = line.strip().split("|")
        if len(parts) < 3:
            return
        
        opcode = parts[0]
        timestamp = parts[1]
        
        if opcode == "00":  # Chat
            self._handle_chat(parts)
        elif opcode in ("15", "16"):  # Ability use
            self._handle_ability(parts)
        elif opcode == "25":  # Death
            self._handle_death(parts)
        elif opcode == "1A":  # Buff gained
            self._handle_buff(parts)
        elif opcode == "21":  # Cast start
            self._handle_cast(parts)
        elif opcode == "26":  # HP update
            self._handle_hp(parts)
    
    def _handle_chat(self, parts):
        if len(parts) < 5:
            return
        chat_code = parts[2]
        speaker = parts[3]
        message = parts[4] if len(parts) > 4 else ""
        msg_lower = message.lower()
        
        # ERP keyword detection
        erp_keywords = {
            "mild": ["moan", "gasp", "whimper", "pant", "shiver", "tremble", "blush"],
            "intense": ["thrust", "pound", "stroke", "grind", "ride", "bounce", "harder"],
            "climax": ["cum", "orgasm", "climax", "finish", "release"],
            "tease": ["tease", "edge", "deny", "beg", "plead", "slowly"],
            "rough": ["spank", "slap", "choke", "grab", "pull", "pin", "force"],
        }
        for ktype, keywords in erp_keywords.items():
            if any(kw in msg_lower for kw in keywords):
                self.mapper.handle("chat_trigger", keyword_type=ktype)
                return
        
        # Emote detection
        emote_keywords = {
            "hug": ["hugs", "embraces"],
            "kiss": ["kisses"],
            "pet": ["pets", "pats"],
            "slap": ["slaps"],
            "spank": ["spanks"],
            "dance": ["dances"],
            "dote": ["dotes"],
        }
        for emote, keywords in emote_keywords.items():
            if any(kw in msg_lower for kw in keywords):
                self.mapper.handle("emote", name=emote)
                return
    
    def _handle_ability(self, parts):
        if len(parts) < 10:
            return
        source_id = parts[2]
        source_name = parts[3]
        ability_id = parts[4]
        ability_name = parts[5]
        target_id = parts[6]
        target_name = parts[7]
        
        # Check for damage on player
        if len(parts) > 9:
            flags = parts[8] if len(parts) > 8 else ""
            damage_str = parts[9] if len(parts) > 9 else "0"
            try:
                damage = int(damage_str, 16) if damage_str else 0
                if damage > 0 and self.player_name and target_name == self.player_name:
                    self.mapper.handle("damage_taken", damage)
                elif damage > 0 and self.player_name and source_name == self.player_name:
                    self.mapper.handle("damage_dealt", damage)
            except:
                pass
    
    def _handle_death(self, parts):
        if len(parts) > 3:
            name = parts[3]
            if self.player_name and name == self.player_name:
                self.mapper.handle("death")
    
    def _handle_buff(self, parts):
        if len(parts) > 5:
            buff_name = parts[5] if len(parts) > 5 else ""
            target_name = parts[3]
            if "Vulnerability" in buff_name and self.player_name and target_name == self.player_name:
                stacks = 1  # Could parse stack count from parts
                self.mapper.handle("vuln_stack", stacks)
    
    def _handle_cast(self, parts):
        if len(parts) > 5:
            source_name = parts[3]
            ability_name = parts[5] if len(parts) > 5 else ""
            # Boss casts (not from player)
            if self.player_name and source_name != self.player_name:
                self.mapper.handle("boss_cast", name=ability_name)
    
    def _handle_hp(self, parts):
        if len(parts) > 6:
            name = parts[3]
            if self.player_name and name == self.player_name:
                try:
                    hp = int(parts[5])
                    max_hp = int(parts[6])
                    pct = (hp / max(1, max_hp)) * 100
                    self.mapper.handle("hp_update", int(pct), max_hp=max_hp)
                except:
                    pass


# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 55)
    print("  FF14 Lovense Bridge v2.0 - Dalamud Edition")  
    print("=" * 55)
    
    ctrl = LovenseController(LOVENSE_DOMAIN)
    
    print("\nConnecting to Lovense...")
    if not ctrl.connect():
        print("No toys found! Make sure:")
        print("  1. Lovense Remote app is open")
        print("  2. Game Mode is ON")
        print("  3. Toys are connected")
        return
    
    mapper = EventMapper(ctrl)
    
    # Test mode
    if "--test" in sys.argv:
        print("\n=== TEST MODE ===")
        tests = [
            ("Testing damage taken...", "damage_taken", 15000),
            ("Testing boss cast...", "boss_cast", 0),
            ("Testing limit break...", "limit_break", 0),
            ("Testing kiss emote...", "emote", 0),
            ("Testing victory...", "duty_complete", 0),
        ]
        for desc, evt, val in tests:
            print(f"\n{desc}")
            kwargs = {}
            if evt == "emote":
                kwargs["name"] = "kiss"
            if evt == "limit_break":
                kwargs["level"] = 3
            if evt == "boss_cast":
                kwargs["name"] = "Akh Morn"
            mapper.handle(evt, val, **kwargs)
            time.sleep(4)
        ctrl.stop_all()
        print("\nTest complete!")
        return
    
    # Start webhook server for Dalamud plugins
    print(f"\nStarting webhook server on port {WEBHOOK_PORT}...")
    WebhookHandler.mapper = mapper
    server = HTTPServer(("127.0.0.1", WEBHOOK_PORT), WebhookHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    print(f"Webhook ready at http://127.0.0.1:{WEBHOOK_PORT}")
    print("Configure Dalamud plugin to POST events here.\n")
    
    # Also start network log parser as fallback
    print("Looking for FF14 network logs...")
    log_parser = NetworkLogParser(mapper)
    
    # Try to find player name
    if "--player" in sys.argv:
        idx = sys.argv.index("--player") + 1
        if idx < len(sys.argv):
            log_parser.player_name = sys.argv[idx]
            print(f"Player: {log_parser.player_name}")
    
    # Find latest log file
    log_file = None
    for log_dir in [NETWORK_LOG_DIR, DALAMUD_LOG_DIR]:
        if log_dir.exists():
            files = sorted(log_dir.glob("*.log"), key=os.path.getmtime, reverse=True)
            if files:
                log_file = files[0]
                break
    
    if log_file:
        print(f"Watching log: {log_file}")
    else:
        print("No log file found yet (waiting for FF14 to start)")
    
    print("\n" + "=" * 55)
    print("  READY! Play FF14 and feel the game!")
    print("  Press Ctrl+C to stop")
    print("=" * 55 + "\n")
    
    try:
        if log_file:
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                f.seek(0, 2)  # Start at end
                while True:
                    line = f.readline()
                    if line:
                        log_parser.parse_line(line)
                    else:
                        time.sleep(0.05)
        else:
            # No log file - just run webhook server
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping toys...")
        ctrl.stop_all()
        server.shutdown()
        print("Bye! 🐸")


if __name__ == "__main__":
    main()

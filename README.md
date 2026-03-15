# FF14 Lovense Bridge 🎮🥵

**Feel the game.** Real-time haptic feedback for Final Fantasy XIV using Lovense toys.

Your in-game actions control your toys — combat damage, healing, emotes, boss mechanics, and more translate into vibration patterns automatically.

## Features

⚔️ **Combat Feedback**
- Damage taken scales vibration intensity
- HP tracking — lower HP = stronger buzz
- Boss mechanics (tankbusters, AOEs, stack markers)
- Limit Break = MAX POWER
- Enrage = everything maxed

💋 **Social & Emotes**
- /hug, /kiss, /pet, /slap — each has unique patterns
- ERP keyword detection with escalating intensity
- Dance = wave pattern

🎬 **Story**
- Cutscene ambient buzz
- Victory celebrations (fireworks!)
- Zone change haptic feedback

🔌 **Two Modes**
1. **Dalamud/XIVLauncher** (recommended) — webhook integration with Triggernometry
2. **ACT Network Log** — parses combat data automatically

## Quick Start

```bash
# Install
git clone https://github.com/Frowg/ff14-lovense.git
cd ff14-lovense
pip install requests

# Run
python ff14_lovense.py --player "Your Name"

# Test without FF14
python ff14_lovense.py --test
```

## Requirements
- Python 3.10+
- Lovense Remote app (Game Mode ON)
- Lovense toy(s) connected
- FF14 with XIVLauncher/Dalamud (recommended) or ACT

## Dalamud Setup
1. Install **Triggernometry** plugin
2. Add triggers that POST to `http://127.0.0.1:8069`
3. Example: `{"event": "damage_taken", "value": 15000}`

## Supported Toys
Works with any Lovense toy that supports vibration:
- Edge (prostate massager)
- Diamo (cock ring)  
- Gemini (nipple clamps)
- Lush, Hush, Max, Nora, etc.

## Supported Events

| Event | Trigger | Response |
|-------|---------|----------|
| Damage Taken | Getting hit | Vibration scales with damage |
| HP Low | HP below 50% | Continuous intensity increase |
| Tankbuster | Big single hit | Max burst |
| AOE Warning | Mechanic telegraph | Pulsing alert |
| Death | You die | Big buzz then silence |
| Limit Break | LB activation | MAX POWER |
| Healing | Receiving heals | Gentle waves |
| Victory | Duty complete | Fireworks preset |
| /kiss | Kiss emote | Building wave |
| /hug | Hug emote | Warm pulse |
| /slap | Slap emote | Sharp burst |
| ERP Chat | Keyword detection | Escalating patterns |

## Support the Project

If you enjoy this mod, consider supporting development:

☕ **[Buy Me a Coffee](https://ko-fi.com/theoneboundinink)**
💜 **[Ko-fi](https://ko-fi.com/theoneboundinink)**
🐸 **[Frowg Systems](https://frowg.org)**

## License
MIT — use it, mod it, share it.

## Disclaimer
This is a third-party tool and is not affiliated with Square Enix, Final Fantasy XIV, or Lovense. Use at your own risk. Not responsible for any in-game deaths caused by... distraction. 😈


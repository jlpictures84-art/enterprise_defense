# Enterprise Defense
### USS Enterprise NCC-1701-D — Tactical Defense

A Star Trek: The Next Generation themed touchscreen space shooter for **Raspberry Pi 4** running Wayland (labwc / Raspberry Pi OS).

Defend the Enterprise against waves of Klingon, Romulan, and Borg enemies across multiple chapters. Manage shields, hull integrity, weapons power, and special abilities.

---

## Requirements

- Raspberry Pi 4 (tested on Raspberry Pi OS with labwc/Wayland)
- Touchscreen display (1280×800 recommended)
- Python 3, pygame, numpy
- ffmpeg (for cutscene video playback)

---

## Install

```bash
git clone https://github.com/jlpictures84-art/enterprise_defense.git
cd enterprise_defense
bash install.sh
```

The installer:
- Installs `python3-pygame`, `python3-numpy`, and `ffmpeg` via apt
- Creates a desktop shortcut pointing to the cloned directory
- Makes launch scripts executable

---

## Cutscene Videos

The game supports optional video cutscenes before major battles. These are not included in the repo — place your own video files here:

| File | When it plays |
|---|---|
| `~/Downloads/1.mp4` | Before Level 10 (Chapter 1 Borg fleet) |
| `~/Downloads/2.mp4` | Before Chapter 2 Level 1 |

Chapters follow the same pattern: odd-numbered videos play before the 10th wave of each chapter; even-numbered videos play at the start of the next chapter.

The game runs fine without any video files — cutscenes are silently skipped.

**Tap anywhere on screen** (after 1 second) to skip a playing video.

---

## Gameplay

### Weapons
| Button | Action |
|---|---|
| **PHASER** | Instant beam — tap to fire at any point |
| **TORPEDO** | Slower projectile, more damage, costs power |
| **PHOTON BURST** | 8 torpedoes in all directions (cooldown) |

### Special Abilities
| Button | Effect |
|---|---|
| **SHIELDS** | Toggle shield bubble (absorbs damage before hull) |
| **RED ALERT** | Manual red alert mode |
| **AUTO LOCK** | 5-second auto-fire on all targets (1 charge per wave) |
| **ALL WEAPONS** | 8s dual auto-fire (phasers + torpedoes) + rapid shield regen |
| **WARP BOOST** | Temporary speed/evasion boost |
| **TRACTOR BEAM** | Slows enemies |
| **INTRUDER ALERT** | Clears on-screen enemies |
| **PAUSE** | Freeze game (tap RESUME to continue) |

### Health System
- **Shields** — recharge over time; absorb damage before hull takes a hit
- **Hull Integrity** — permanent damage; game over when hull reaches 0

### Wave Structure
| Wave | Type |
|---|---|
| 1–4 | Regular hostiles (Warbirds + Klingons) |
| 5 | 15 fast scout ships |
| 6–9 | Regular hostiles (all types) |
| 10 | **Borg Fleet** — 3 Borg cubes + cutscene |
| Repeat every 10 waves with new chapter |

---

## File Structure

```
enterprise_defense/
├── enterprise_defense.py       # main game
├── enterprise_defense_icon.svg # desktop icon
├── play_enterprise.sh          # launch script
├── install.sh                  # Pi setup script
└── README.md
```

---

## Running Without the Installer

```bash
# Install dependencies manually
sudo apt-get install python3-pygame python3-numpy ffmpeg

# Run directly
export SDL_VIDEODRIVER=wayland
export WAYLAND_DISPLAY=wayland-0
export XDG_RUNTIME_DIR=/run/user/$(id -u)
python3 enterprise_defense.py
```

---

## NatureFrame Integration

If you run the [NatureFrame](https://github.com/jlpictures84-art/birdstation) bird-watching display on the same Pi, `play_enterprise.sh` automatically stops and restarts the `nature_frame` systemd service around each game session.

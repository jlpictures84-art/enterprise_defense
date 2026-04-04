#!/usr/bin/env python3
"""
USS Enterprise NCC-1701-D: Tactical Defense  (v3 — LCARS Overhaul)
Star Trek TNG themed touch-screen space shooter for Raspberry Pi.
Tap anywhere to fire.  W = switch weapon.  ESC = quit.
"""

import pygame
import math
import random
import sys
import threading
import os
import wave
import tempfile
import time

# ── Display globals (initialised by _init_display, called from _android_main) ─
screen   = None
SCREEN_W = 1280
SCREEN_H = 800
CX       = 640
CY       = 400
CENTER_X = 640
CENTER_Y = 400
clock    = None
FPS      = 60
_SF      = 1.0
def _s(x): return max(1, int(x * _SF))

# ── LCARS Color Palette ───────────────────────────────────────────────────────
BLACK       = (  0,   0,   0)
LCARS_ORA   = (255, 153,   0)
LCARS_GOLD  = (255, 204, 102)
LCARS_RED   = (204,  51,  51)
LCARS_BLUE  = (153, 204, 255)
LCARS_PURP  = (153, 102, 204)
LCARS_TEAL  = ( 51, 204, 204)
WHITE       = (255, 255, 255)
BORG_GREEN  = ( 50, 210,  80)
ROMULAN_RED = (200,  60,  60)
KLINGON_PUR = (130,  60, 180)
PHASER_COL  = (255, 140,  20)
ALERT_RED   = (180,  20,  20)

# ── Fonts (initialised by _init_display) ──────────────────────────────────────
font_huge = font_large = font_med = font_small = font_tiny = None

def _init_display():
    global screen, SCREEN_W, SCREEN_H, CX, CY, CENTER_X, CENTER_Y, clock, _SF
    global font_huge, font_large, font_med, font_small, font_tiny
    pygame.init()
    pygame.mixer.init(frequency=48000)
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    _info  = pygame.display.Info()
    SCREEN_W = _info.current_w
    SCREEN_H = _info.current_h
    CX = SCREEN_W // 2
    CY = SCREEN_H // 2
    CENTER_X = CX
    CENTER_Y = CY
    pygame.display.set_caption("USS Enterprise: Tactical Defense")
    clock = pygame.time.Clock()
    _SF = min(SCREEN_W / 1280, SCREEN_H / 800)
    pygame.font.init()
    font_huge  = pygame.font.SysFont("monospace", _s(64), bold=True)
    font_large = pygame.font.SysFont("monospace", _s(42), bold=True)
    font_med   = pygame.font.SysFont("monospace", _s(26), bold=True)
    font_small = pygame.font.SysFont("monospace", _s(18))
    font_tiny  = pygame.font.SysFont("monospace", _s(14))
    global shield_surf, alert_surf
    shield_surf = pygame.Surface((260, 260), pygame.SRCALPHA)
    alert_surf  = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    _load_sounds()

# ── Sound: synthesise WAV files, load into pygame.mixer ──────────────────────
SR = 48000
_SFX_DIR = tempfile.mkdtemp(prefix='enterprise_sfx_')
WAV = {}          # name -> /tmp/... path
_SOUNDS = {}      # name -> pygame.mixer.Sound object
SOUNDS_OK = False
sfx_on = True     # weapons / effects audio toggle

def _write_wav(arr, name):
    """Write float32 mono array to a WAV file; return path."""
    path = os.path.join(_SFX_DIR, f'{name}.wav')
    s16 = (arr.clip(-1, 1) * 32767 * 0.5).astype('int16')
    with wave.open(path, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(s16.tobytes())
    return path

try:
    import numpy as np

    def _sweep(f0, f1, dur, amp=0.7):
        n = int(SR * dur)
        freqs = np.linspace(f0, f1, n)
        phase = np.cumsum(2 * np.pi * freqs / SR)
        sig = amp * np.sin(phase)
        fade = min(int(0.01 * SR), n // 4)
        sig[:fade] *= np.linspace(0, 1, fade)
        sig[-fade:] *= np.linspace(1, 0, fade)
        return sig.astype(np.float32)

    def _noise(dur, amp=0.6, smooth=4):
        n = int(SR * dur)
        sig = (np.random.random(n) * 2 - 1).astype(np.float32) * amp
        if smooth > 1:
            sig = np.convolve(sig, np.ones(smooth)/smooth, mode='same')
        fade = min(int(0.008 * SR), n // 4)
        sig[:fade] *= np.linspace(0, 1, fade)
        sig[-fade:] *= np.linspace(1, 0, fade)
        return sig.astype(np.float32)

    # Phaser: frequency sweep down
    WAV['phaser'] = _write_wav(_sweep(1600, 180, 0.35, amp=0.65), 'phaser')

    # Torpedo: rising whine
    WAV['torpedo'] = _write_wav(_sweep(50, 950, 0.45, amp=0.60), 'torpedo')

    # Explosions
    _exp_s = _noise(0.30, amp=0.55, smooth=8)
    WAV['explode'] = _write_wav(_exp_s, 'explode')

    _exp_b = _noise(0.60, amp=0.70, smooth=16) + _sweep(100, 25, 0.60, amp=0.40)
    WAV['big_explode'] = _write_wav(_exp_b.clip(-1, 1).astype(np.float32), 'big_explode')

    # TNG-style red alert: 5 descending "WHOOP" blasts, ~3.5s total, plays once
    _ra_dur   = 3.6
    _ra_n     = int(SR * _ra_dur)
    _ra_sig   = np.zeros(_ra_n, dtype=np.float32)
    _whoop    = 0.48   # seconds per whoop
    _gap      = 0.10   # silence between whoops
    for _i in range(5):
        _nw  = int(SR * _whoop)
        _tw  = np.arange(_nw) / SR
        _f   = np.linspace(1020, 480, _nw)          # sweep high→low
        _ph  = np.cumsum(2 * np.pi * _f / SR)
        # Brass-like tone: fundamental + harmonics
        _tone = (0.50 * np.sin(_ph) +
                 0.22 * np.sin(2 * _ph) +
                 0.12 * np.sin(3 * _ph) +
                 0.06 * np.sin(4 * _ph))
        # Sharp attack, tail off
        _atk = int(0.012 * SR); _rel = int(0.09 * SR)
        _env = np.ones(_nw)
        _env[:_atk] = np.linspace(0, 1, _atk)
        _env[-_rel:] = np.linspace(1, 0, _rel)
        _tone = (_tone * _env * 0.62).astype(np.float32)
        _s0 = int((_i * (_whoop + _gap) + 0.04) * SR)
        _s1 = min(_s0 + _nw, _ra_n)
        _ra_sig[_s0:_s1] += _tone[:_s1 - _s0]
    WAV['klaxon'] = _write_wav(_ra_sig.clip(-1, 1).astype(np.float32), 'klaxon')

    # Shield hit
    WAV['shield_hit'] = _write_wav(_sweep(320, 70, 0.20, amp=0.55), 'shield_hit')

    # Weapon switch
    WAV['switch'] = _write_wav(_sweep(400, 1100, 0.12, amp=0.45), 'switch')

    # Boss appear: low drone + rising tone
    _n = int(SR * 1.8)
    _t = np.arange(_n) / SR
    _drone = 0.45 * np.sin(2 * np.pi * 55 * _t)
    _rise  = _sweep(80, 600, 1.8, amp=0.40)
    _boss  = (_drone + _rise).clip(-1, 1).astype(np.float32)
    fade = int(0.05 * SR)
    _boss[:fade] *= np.linspace(0, 1, fade)
    _boss[-fade:] *= np.linspace(1, 0, fade)
    WAV['boss_appear'] = _write_wav(_boss, 'boss_appear')

    # Intruder Alert: fast high triple klaxon (2.5s)
    _ia_n = int(SR * 2.5); _ia = np.zeros(_ia_n, np.float32)
    for _i in range(4):
        _nb = int(SR * 0.26); _tb2 = np.arange(_nb)/SR
        _fb = np.linspace(1400, 850, _nb)
        _pb = np.cumsum(2*np.pi*_fb/SR)
        _bip = (0.55*np.sin(_pb)+0.2*np.sin(2*_pb)) * np.exp(-_tb2*9) * 0.7
        _s2 = int((_i*0.58+0.04)*SR); _e2 = min(_s2+_nb, _ia_n)
        _ia[_s2:_e2] += _bip[:_e2-_s2]
    WAV['intruder'] = _write_wav(_ia, 'intruder')

    # Warp Boost: rising engine hum (1.5s)
    _wb_n = int(SR*1.5); _wb_t = np.arange(_wb_n)/SR
    _wb_f = np.linspace(55, 290, _wb_n)
    _wb_p = np.cumsum(2*np.pi*_wb_f/SR)
    _wb = (0.5*np.sin(_wb_p)+0.28*np.sin(2*_wb_p)+0.12*np.sin(3*_wb_p))
    _wb *= np.minimum(_wb_t*5,1.0) * np.exp(-_wb_t*0.5)
    WAV['warp_boost'] = _write_wav(_wb.astype(np.float32), 'warp_boost')

    # Tractor Beam: deep resonant pulse (1.4s)
    _tr_n = int(SR*1.4); _tr_t = np.arange(_tr_n)/SR
    _tr = (0.5*np.sin(2*np.pi*68*_tr_t)+0.3*np.sin(2*np.pi*102*_tr_t)+0.14*np.sin(2*np.pi*34*_tr_t))
    _tr *= np.minimum(_tr_t*6,1.0) * np.exp(-_tr_t*1.0)
    WAV['tractor'] = _write_wav(_tr.astype(np.float32), 'tractor')

except Exception as _e:
    print(f"[audio] sound synthesis failed: {_e}")

def _load_sounds():
    global SOUNDS_OK
    if not WAV:
        return
    for _name, _path in WAV.items():
        try:
            _SOUNDS[_name] = pygame.mixer.Sound(_path)
        except Exception as _e2:
            print(f"[audio] failed to load {_name}: {_e2}")
    if _SOUNDS:
        SOUNDS_OK = True
        print(f"[audio] loaded {len(_SOUNDS)} sounds from {_SFX_DIR}")

def play_oneshot(name, _vol=1.0):
    """Play a one-shot sound via pygame.mixer."""
    if not SOUNDS_OK or name not in _SOUNDS or not sfx_on:
        return
    try:
        snd = _SOUNDS[name]
        snd.set_volume(_vol)
        snd.play()
    except Exception:
        pass

_klaxon_channel = None

def play_klaxon():
    """Play the red alert sound once (3.5s) — no looping."""
    global _klaxon_channel
    stop_klaxon()
    if not SOUNDS_OK or not sfx_on or 'klaxon' not in _SOUNDS:
        return
    try:
        _klaxon_channel = _SOUNDS['klaxon'].play()
    except Exception:
        pass

def stop_klaxon():
    global _klaxon_channel
    if _klaxon_channel:
        try:
            _klaxon_channel.stop()
        except Exception:
            pass
    _klaxon_channel = None

def speak(text):
    pass   # voice removed

# ── Chapter cutscenes ─────────────────────────────────────────────────────────
def play_cutscene(video_num):
    """Show an LCARS chapter title card — works on all platforms (no ffplay/evdev)."""
    chapter = (video_num + 1) // 2
    is_pre  = (video_num % 2 == 1)   # odd = before Borg fleet, even = new chapter

    screen.fill(BLACK)
    y = CY - _s(100)
    for text, col in [
        ("STAR  TREK",                    LCARS_PURP),
        ("USS  ENTERPRISE  NCC-1701-D",   LCARS_BLUE),
        ("",                              BLACK),
        (f"CHAPTER  {chapter}",            LCARS_ORA),
        ("BORG  INCURSION" if is_pre else "MISSION  CONTINUES", LCARS_GOLD),
        ("",                              BLACK),
        ("TAP  TO  CONTINUE",             WHITE),
    ]:
        if text:
            surf = font_med.render(text, True, col)
            screen.blit(surf, surf.get_rect(center=(CX, y)))
        y += _s(42)
    pygame.display.flip()

    time.sleep(1.0)
    waiting = True
    while waiting:
        for ev in pygame.event.get():
            if ev.type in (pygame.MOUSEBUTTONDOWN, pygame.FINGERDOWN, pygame.KEYDOWN):
                waiting = False
        clock.tick(30)

# ── Starfield ─────────────────────────────────────────────────────────────────
def make_stars(n=250):
    return [
        [random.randint(0, SCREEN_W),
         random.randint(0, SCREEN_H),
         random.uniform(0.3, 1.0),
         random.uniform(0.05, 0.3)]
        for _ in range(n)
    ]

stars = make_stars()
star_time = 0.0

def draw_stars(dt):
    global star_time
    star_time += dt
    for s in stars:
        twinkle = 0.6 + 0.4 * math.sin(star_time * s[3] * 10 + s[0])
        brightness = int(s[2] * twinkle * 220)
        brightness = max(30, min(255, brightness))
        c = (brightness, brightness, brightness)
        pygame.draw.circle(screen, c, (int(s[0]), int(s[1])), 1)

# ── Enterprise-D (top-down view) ─────────────────────────────────────────────
def draw_enterprise(cx, cy):
    # Nacelle pylons
    pygame.draw.line(screen, (90, 90, 120),  (cx-_s(18), cy+_s(38)), (cx-_s(72), cy+_s(52)), _s(4))
    pygame.draw.line(screen, (90, 90, 120),  (cx+_s(18), cy+_s(38)), (cx+_s(72), cy+_s(52)), _s(4))

    # Nacelles
    for nx in (-_s(72), _s(52)):
        pygame.draw.ellipse(screen, (80, 110, 180), (cx+nx, cy+_s(25), _s(28), _s(72)))
        pygame.draw.ellipse(screen, (110, 140, 210), (cx+nx+_s(2), cy+_s(27), _s(24), _s(68)), _s(2))
        pygame.draw.circle(screen, (220, 60, 30),  (cx+nx+_s(14), cy+_s(30)), _s(9))
        pygame.draw.circle(screen, (255, 120, 60), (cx+nx+_s(14), cy+_s(30)), _s(5))
        pygame.draw.ellipse(screen, (120, 180, 255), (cx+nx+_s(2), cy+_s(84), _s(24), _s(8)))
        pygame.draw.ellipse(screen, (180, 220, 255), (cx+nx+_s(5), cy+_s(85), _s(18), _s(6)))

    # Secondary hull
    pygame.draw.ellipse(screen, (120, 120, 145), (cx-_s(26), cy+_s(18), _s(52), _s(58)))
    pygame.draw.ellipse(screen, (160, 160, 185), (cx-_s(24), cy+_s(20), _s(48), _s(54)), _s(2))

    # Deflector dish
    pygame.draw.circle(screen, ( 60, 130, 220), (cx, cy+_s(36)), _s(10))
    pygame.draw.circle(screen, (140, 200, 255), (cx, cy+_s(36)),  _s(7))
    pygame.draw.circle(screen, (220, 240, 255), (cx, cy+_s(36)),  _s(4))

    # Connecting neck
    pygame.draw.ellipse(screen, (130, 130, 155), (cx-_s(10), cy+_s(8), _s(20), _s(20)))

    # Saucer section
    pygame.draw.ellipse(screen, (155, 155, 180), (cx-_s(72), cy-_s(56), _s(144), _s(110)))
    pygame.draw.ellipse(screen, (180, 180, 200), (cx-_s(68), cy-_s(52), _s(136), _s(102)), _s(2))
    pygame.draw.ellipse(screen, (140, 140, 165), (cx-_s(52), cy-_s(40), _s(104),  _s(78)), _s(2))

    # Bridge dome
    pygame.draw.circle(screen, (200, 200, 220), (cx, cy-_s(22)), _s(14))
    pygame.draw.circle(screen, (220, 220, 240), (cx, cy-_s(22)), _s(11))
    pygame.draw.circle(screen, (170, 170, 200), (cx, cy-_s(22)), _s(11), _s(2))

    # Phaser arrays
    pygame.draw.arc(screen, LCARS_ORA, (cx-_s(60), cy-_s(50), _s(120), _s(90)),
                    math.radians(20), math.radians(160), _s(2))
    pygame.draw.arc(screen, LCARS_ORA, (cx-_s(60), cy-_s(50), _s(120), _s(90)),
                    math.radians(200), math.radians(340), _s(2))

# ── Geometry helpers ──────────────────────────────────────────────────────────
def _seg_dist(px, py, x1, y1, x2, y2):
    """Shortest distance from point (px,py) to segment (x1,y1)-(x2,y2)."""
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    nx = x1 + t * dx
    ny = y1 + t * dy
    return math.hypot(px - nx, py - ny)

def _lerp(a, b, t):
    return a + (b - a) * t

# ── LCARS Layout Constants ────────────────────────────────────────────────────
PANEL_W = _s(210)    # left/right panel width
TOP_H   = _s(62)     # top bar height
BOT_H   = _s(78)     # bottom bar height

# ── Button rects (used by both draw_hud and event handler) ────────────────────
_LP = 0                      # left panel x start
_RP = SCREEN_W - PANEL_W     # right panel x start

_BB = SCREEN_H - BOT_H   # bottom of play area = 722

# Left panel — 6 buttons stacked from bottom up
BTN_QUIT         = pygame.Rect(_LP+_s(10), _BB-_s( 50), PANEL_W-_s(20), _s(44))
BTN_WARP_BOOST   = pygame.Rect(_LP+_s(10), _BB-_s(102), PANEL_W-_s(20), _s(46))
BTN_INTRUDER     = pygame.Rect(_LP+_s(10), _BB-_s(156), PANEL_W-_s(20), _s(48))
BTN_SHIELD       = pygame.Rect(_LP+_s(10), _BB-_s(212), PANEL_W-_s(20), _s(50))
BTN_PAUSE        = pygame.Rect(_LP+_s(10), _BB-_s(272), PANEL_W-_s(20), _s(52))
BTN_SFX          = pygame.Rect(_LP+_s(10), _BB-_s(332), PANEL_W-_s(20), _s(52))

# Right panel — 5 buttons stacked from bottom up
BTN_TRACTOR      = pygame.Rect(_RP+_s(10), _BB-_s( 50), PANEL_W-_s(20), _s(44))
BTN_PHOTON_BURST = pygame.Rect(_RP+_s(10), _BB-_s(102), PANEL_W-_s(20), _s(46))
BTN_AUTO_LOCK    = pygame.Rect(_RP+_s(10), _BB-_s(156), PANEL_W-_s(20), _s(48))
BTN_RED_ALERT    = pygame.Rect(_RP+_s(10), _BB-_s(212), PANEL_W-_s(20), _s(50))
BTN_ALL_WEAPONS  = pygame.Rect(_RP+_s(10), _BB-_s(272), PANEL_W-_s(20), _s(52))

# Bottom weapon buttons (inside the bottom bar)
_BW = _s(170)
BTN_PHASER  = pygame.Rect(PANEL_W + _s(30),             SCREEN_H - BOT_H + _s(14), _BW, _s(50))
BTN_TORPEDO = pygame.Rect(SCREEN_W - PANEL_W - _s(200), SCREEN_H - BOT_H + _s(14), _BW, _s(50))

# Torpedo power cost (referenced in draw_hud)
TORPEDO_POWER_COST = 22.0

# ── LCARS helper: pill button ─────────────────────────────────────────────────
def draw_lcars_btn(surf, rect, label, color, lit=True, border_only=False):
    """LCARS pill-shaped button. lit=False draws dim/inactive state."""
    r = rect.height // 2
    if border_only:
        bg = (max(0, color[0]//5), max(0, color[1]//5), max(0, color[2]//5))
    else:
        bg = color if lit else tuple(max(0, c//4) for c in color)
    pygame.draw.rect(surf, bg, rect, border_radius=r)
    pygame.draw.rect(surf, color if lit else tuple(c//2 for c in color), rect, 2, border_radius=r)
    txt_col = BLACK if lit and not border_only else (color if not lit else WHITE)
    fnt = font_small if len(label) <= 14 else font_tiny
    lbl = fnt.render(label, True, txt_col)
    surf.blit(lbl, (rect.centerx - lbl.get_width()//2, rect.centery - lbl.get_height()//2))

# ── LCARS helper: segmented power bar ────────────────────────────────────────
def draw_power_bar(surf, x, y, w, h, power, max_power):
    """Segmented LCARS power bar."""
    pct = max(0.0, power / max_power)
    pygame.draw.rect(surf, (15, 15, 15), (x, y, w, h), border_radius=4)
    n = 24
    sw = max(1, (w - n - 2) // n)
    for i in range(n):
        filled = (i / n) < pct
        if filled:
            c = (50, 210, 80) if pct > 0.6 else (210, 180, 40) if pct > 0.25 else (210, 50, 30)
        else:
            c = (25, 25, 25)
        sx = x + 1 + i * (sw + 1)
        pygame.draw.rect(surf, c, (sx, y+2, sw, h-4), border_radius=2)
    pygame.draw.rect(surf, LCARS_ORA, (x, y, w, h), 1, border_radius=4)

# ── Phaser Beam (instant) ──────────────────────────────────────────────────────
class PhaserBeam:
    FADE_TIME = 0.28

    def __init__(self, tx, ty):
        self.x1 = float(CX)
        self.y1 = float(CY - 8)
        # Extend beam to screen edge
        dx = tx - CX
        dy = ty - (CY - 8)
        dist = math.hypot(dx, dy) or 1
        scale = math.hypot(SCREEN_W, SCREEN_H)
        self.x2 = self.x1 + (dx / dist) * scale
        self.y2 = self.y1 + (dy / dist) * scale
        self.life = self.FADE_TIME
        self.alive = True
        self.did_hit = False

    def check_hits(self, enemies, boss):
        """Called once after creation. Returns (hit_enemy_list, hit_boss_bool)."""
        if self.did_hit:
            return [], False
        self.did_hit = True
        hit_enemies = []
        for e in enemies:
            if not e.alive:
                continue
            d = _seg_dist(e.x, e.y, self.x1, self.y1, self.x2, self.y2)
            if d < e.size + 4:
                hit_enemies.append(e)
        hit_boss = False
        if boss is not None and boss.alive:
            d = _seg_dist(boss.x, boss.y, self.x1, self.y1, self.x2, self.y2)
            if d < boss.size + 4:
                hit_boss = True
        return hit_enemies, hit_boss

    def update(self, dt):
        self.life -= dt
        if self.life <= 0:
            self.alive = False

    def draw(self, surf):
        if not self.alive:
            return
        t = self.life / self.FADE_TIME   # 1 → 0
        alpha = int(t * 255)
        bsurf = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        p1 = (int(self.x1), int(self.y1))
        p2 = (int(self.x2), int(self.y2))
        pygame.draw.line(bsurf, (255, 120, 0, min(alpha, 120)), p1, p2, 9)
        pygame.draw.line(bsurf, (255, 165, 20, min(alpha, 200)), p1, p2, 4)
        pygame.draw.line(bsurf, (255, 255, 220, min(alpha, 255)), p1, p2, 2)
        surf.blit(bsurf, (0, 0))

# ── Photon Torpedo ────────────────────────────────────────────────────────────
class PhotonTorpedo:
    SPEED     = 9
    AOE_R     = 55
    TRAIL_LEN = 18

    def __init__(self, tx, ty):
        dx = tx - CX
        dy = ty - (CY - 8)
        dist = math.hypot(dx, dy) or 1
        self.vx = (dx / dist) * self.SPEED
        self.vy = (dy / dist) * self.SPEED
        self.x  = float(CX)
        self.y  = float(CY - 8)
        self.tx = float(tx)
        self.ty = float(ty)
        self.alive = True
        self.trail = []
        self.exploded = False

    def proximity_check(self, enemies, boss):
        """Returns True if torpedo is within contact range of any enemy/boss."""
        for e in enemies:
            if not e.alive:
                continue
            if math.hypot(self.x - e.x, self.y - e.y) < e.size + 8:
                return True
        if boss is not None and boss.alive:
            if math.hypot(self.x - boss.x, self.y - boss.y) < boss.size + 8:
                return True
        return False

    def aoe_check(self, enemies, boss):
        """Apply AoE damage. Returns (score_gained, hit_boss)."""
        score = 0
        hit_boss = False
        for e in enemies:
            if not e.alive:
                continue
            if math.hypot(self.x - e.x, self.y - e.y) < self.AOE_R:
                for _ in range(2):
                    killed = e.hit()
                    if killed:
                        score += Enemy.SCORES[e.kind]
                        break
        if boss is not None and boss.alive:
            if math.hypot(self.x - boss.x, self.y - boss.y) < self.AOE_R:
                boss.hp -= 3
                boss.flash = 0.15
                if boss.hp <= 0:
                    boss.hp = 0
                    boss.alive = False
                hit_boss = True
        return score, hit_boss

    def update(self):
        self.trail.append((self.x, self.y))
        if len(self.trail) > self.TRAIL_LEN:
            self.trail.pop(0)
        self.x += self.vx
        self.y += self.vy
        if math.hypot(self.x - self.tx, self.y - self.ty) < self.SPEED + 2:
            self.alive = False
            self.exploded = True
        if not (0 <= self.x <= SCREEN_W and 0 <= self.y <= SCREEN_H):
            self.alive = False

    def draw(self, surf):
        n = len(self.trail)
        for i, (tx, ty) in enumerate(self.trail):
            t = (i + 1) / (n + 1)
            r = int(255 * t)
            g = int(100 * t)
            b = int(20 * t)
            sz = max(1, int(5 * t))
            pygame.draw.circle(surf, (r, g, b), (int(tx), int(ty)), sz)
        pygame.draw.circle(surf, (255, 80, 0),   (int(self.x), int(self.y)), 9)
        pygame.draw.circle(surf, (255, 160, 60),  (int(self.x), int(self.y)), 6)
        pygame.draw.circle(surf, (255, 240, 200), (int(self.x), int(self.y)), 3)

# ── Explosion Particles ────────────────────────────────────────────────────────
class Explosion:
    def __init__(self, x, y, color, n=18, big=False):
        self.particles = []
        sc = 1.8 if big else 1.0
        for _ in range(n):
            angle = random.uniform(0, 2 * math.pi)
            spd   = random.uniform(2, 7) * sc
            life  = random.uniform(0.4, 0.9) * sc
            self.particles.append({
                'x': x, 'y': y,
                'vx': math.cos(angle) * spd,
                'vy': math.sin(angle) * spd,
                'life': life,
                'max_life': life,
                'size': random.uniform(3, 8) * sc,
                'color': color
            })
        self.alive = True

    def update(self, dt):
        for p in self.particles:
            p['x']  += p['vx']
            p['y']  += p['vy']
            p['vx'] *= 0.90
            p['vy'] *= 0.90
            p['life'] -= dt
        self.particles = [p for p in self.particles if p['life'] > 0]
        if not self.particles:
            self.alive = False

    def draw(self, surf):
        for p in self.particles:
            t  = p['life'] / p['max_life']
            sz = max(1, int(p['size'] * t))
            r, g, b = p['color']
            col = (int(r * t + 255 * (1 - t) * 0.3),
                   int(g * t),
                   int(b * t))
            pygame.draw.circle(surf, col, (int(p['x']), int(p['y'])), sz)

# ── Enemy Ships ────────────────────────────────────────────────────────────────
ENEMY_TYPES = ['borg', 'warbird', 'klingon']

class Enemy:
    SCORES   = {'borg': 60, 'warbird': 35, 'klingon': 20, 'scout': 10}
    HP_BASE  = {'borg':  3, 'warbird':  2, 'klingon':  1, 'scout':  1}
    SIZES    = {'borg': 24, 'warbird': 22, 'klingon': 16, 'scout': 10}
    COLORS   = {'borg': BORG_GREEN, 'warbird': ROMULAN_RED, 'klingon': KLINGON_PUR,
                'scout': (80, 180, 255)}

    def __init__(self, wave, kinds=None):
        self.wave = wave
        angle = random.uniform(0, 2 * math.pi)
        spawn_r = math.hypot(SCREEN_W, SCREEN_H) * 0.58
        self.x = CX + math.cos(angle) * spawn_r
        self.y = CY + math.sin(angle) * spawn_r
        self.kind  = random.choice(kinds if kinds else ENEMY_TYPES)
        if self.kind == 'scout':
            self.speed = 2.2 + random.uniform(0, 0.6)   # scouts are fast
        else:
            spd = 0.55 + wave * 0.12 + random.uniform(0, 0.3)
            self.speed = min(spd, 3.5)
        self.size  = self.SIZES[self.kind]
        self.color = self.COLORS[self.kind]
        self.max_hp = self.HP_BASE[self.kind] + wave // 4
        self.hp    = self.max_hp
        self.alive = True
        self.angle = angle
        self.flash = 0

    def update(self, dt):
        dx = CX - self.x
        dy = CY - self.y
        dist = math.hypot(dx, dy)
        if dist < 8:
            self.alive = False
            return True
        self.x += (dx / dist) * self.speed
        self.y += (dy / dist) * self.speed
        self.angle = math.atan2(dy, dx)
        self.flash = max(0, self.flash - dt)
        return False

    def hit(self, dmg=1):
        self.hp -= dmg
        self.flash = 0.12
        if self.hp <= 0:
            self.alive = False
            return True
        return False

    def draw(self, surf):
        col = WHITE if self.flash > 0 else self.color
        cx, cy = int(self.x), int(self.y)
        a = self.angle

        if self.kind == 'borg':
            r = self.size
            rect = pygame.Rect(cx - r, cy - r, r * 2, r * 2)
            pygame.draw.rect(surf, (20, 80, 30), rect)
            pygame.draw.rect(surf, col, rect, 3)
            pygame.draw.line(surf, col, (cx - r, cy), (cx + r, cy), 1)
            pygame.draw.line(surf, col, (cx, cy - r), (cx, cy + r), 1)
            pygame.draw.circle(surf, BORG_GREEN, (cx, cy), 5)
            pygame.draw.circle(surf, WHITE,      (cx, cy), 3)

        elif self.kind == 'warbird':
            fw = math.cos(a) * self.size * 1.3
            fh = math.sin(a) * self.size * 1.3
            lx = math.cos(a + math.pi / 2)
            ly = math.sin(a + math.pi / 2)
            pts = [
                (cx + fw,                cy + fh),
                (cx - lx * self.size * 1.6, cy - ly * self.size * 1.6),
                (cx - math.cos(a) * self.size * 0.6,
                 cy - math.sin(a) * self.size * 0.6),
                (cx + lx * self.size * 1.6, cy + ly * self.size * 1.6),
            ]
            pygame.draw.polygon(surf, (80, 20, 20), pts)
            pygame.draw.polygon(surf, col, pts, 2)
            pygame.draw.circle(surf, (255, 100, 50),
                               (int(cx + fw * 0.7), int(cy + fh * 0.7)), 4)

        elif self.kind == 'scout':
            # Small fast blue arrowhead
            fw = math.cos(a) * self.size * 1.4
            fh = math.sin(a) * self.size * 1.4
            lx = math.cos(a + math.pi / 2)
            ly = math.sin(a + math.pi / 2)
            pts = [
                (cx + fw,                          cy + fh),
                (cx + lx * self.size * 0.9,        cy + ly * self.size * 0.9),
                (cx - math.cos(a) * self.size * 0.5,
                 cy - math.sin(a) * self.size * 0.5),
                (cx - lx * self.size * 0.9,        cy - ly * self.size * 0.9),
            ]
            pygame.draw.polygon(surf, (10, 40, 80), pts)
            pygame.draw.polygon(surf, col, pts, 2)
            # Engine glow
            pygame.draw.circle(surf, (120, 220, 255),
                               (int(cx - math.cos(a)*self.size*0.3),
                                int(cy - math.sin(a)*self.size*0.3)), 3)

        else:  # klingon
            fw = math.cos(a) * self.size
            fh = math.sin(a) * self.size
            lx = math.cos(a + math.pi / 2)
            ly = math.sin(a + math.pi / 2)
            pts = [
                (cx + fw,               cy + fh),
                (cx - lx * self.size,   cy - ly * self.size),
                (cx - math.cos(a) * self.size * 0.8,
                 cy - math.sin(a) * self.size * 0.8),
                (cx + lx * self.size,   cy + ly * self.size),
            ]
            pygame.draw.polygon(surf, (50, 20, 70), pts)
            pygame.draw.polygon(surf, col, pts, 2)
            pygame.draw.circle(surf, (180, 100, 255),
                               (int(cx + fw * 0.6), int(cy + fh * 0.6)), 3)

        if self.hp < self.max_hp:
            bw = self.size * 2
            bx = cx - self.size
            by = cy - self.size - 10
            pygame.draw.rect(surf, LCARS_RED,  (bx, by, bw, 5))
            fill = int(bw * self.hp / self.max_hp)
            pygame.draw.rect(surf, BORG_GREEN, (bx, by, fill, 5))

# ── Boss Plasma Bolt ───────────────────────────────────────────────────────────
class BossPlasma:
    SPEED  = 2.5
    DAMAGE = 15
    TRAIL_LEN = 12

    def __init__(self, bx, by):
        dx = CX - bx
        dy = CY - by
        dist = math.hypot(dx, dy) or 1
        self.vx = (dx / dist) * self.SPEED
        self.vy = (dy / dist) * self.SPEED
        self.x  = float(bx)
        self.y  = float(by)
        self.alive = True
        self.trail = []

    def update(self):
        self.trail.append((self.x, self.y))
        if len(self.trail) > self.TRAIL_LEN:
            self.trail.pop(0)
        self.x += self.vx
        self.y += self.vy
        if math.hypot(self.x - CX, self.y - CY) < 10:
            self.alive = False
            return True   # hit enterprise
        if not (0 <= self.x <= SCREEN_W and 0 <= self.y <= SCREEN_H):
            self.alive = False
        return False

    def draw(self, surf):
        n = len(self.trail)
        for i, (tx, ty) in enumerate(self.trail):
            t = (i + 1) / (n + 1)
            g = int(200 * t)
            pygame.draw.circle(surf, (0, g, 0), (int(tx), int(ty)),
                               max(1, int(4 * t)))
        pygame.draw.circle(surf, (0, 255, 80),  (int(self.x), int(self.y)), 7)
        pygame.draw.circle(surf, (100, 255, 150), (int(self.x), int(self.y)), 4)
        pygame.draw.circle(surf, (220, 255, 220), (int(self.x), int(self.y)), 2)

# ── Boss: Borg Tactical Cube ───────────────────────────────────────────────────
class BossEnemy:
    SIZE  = 55
    SCORE = 2500

    def __init__(self, wave, start_x=None, start_y=None):
        self.wave   = wave
        self.x      = float(start_x if start_x is not None else PANEL_W + self.SIZE + 10)
        self.y      = float(start_y if start_y is not None else CY - 220)
        self.size   = self.SIZE
        self.max_hp = 50 + wave * 3
        self.hp     = self.max_hp
        self.alive  = True
        self.angle  = 0.0
        self.rot_speed = 0.45
        self.flash  = 0.0
        self.fire_timer = 3.0
        self.color  = (30, 160, 50)
        # Side-to-side sweep speed, increases each wave
        self.strafe_speed = 4.0 + wave * 0.4
        self.strafe_dir   = 1   # 1 = moving right, -1 = moving left
        # Bounce bounds (stay within playfield, clear of side panels)
        self.x_min = PANEL_W + self.SIZE + 8
        self.x_max = SCREEN_W - PANEL_W - self.SIZE - 8

    def update(self, dt):
        self.angle += self.rot_speed * dt
        self.flash  = max(0, self.flash - dt)

        # Fast side-to-side sweep
        self.x += self.strafe_speed * self.strafe_dir
        if self.x >= self.x_max:
            self.x = self.x_max
            self.strafe_dir = -1
        elif self.x <= self.x_min:
            self.x = self.x_min
            self.strafe_dir = 1

        # Fire timer
        self.fire_timer -= dt
        if self.fire_timer <= 0:
            self.fire_timer = 4.5
            return 'fire'
        return None

    def take_phaser_damage(self):
        self.hp -= 1
        self.flash = 0.12
        if self.hp <= 0:
            self.hp = 0
            self.alive = False
            return True
        return False

    def take_torpedo_damage(self):
        # Direct hit: 3 damage
        self.hp -= 3
        self.flash = 0.20
        if self.hp <= 0:
            self.hp = 0
            self.alive = False
            return True
        return False

    def _rotated_corner(self, ox, oy):
        c = math.cos(self.angle)
        s = math.sin(self.angle)
        return (self.x + c * ox - s * oy,
                self.y + s * ox + c * oy)

    def draw(self, surf):
        col = (200, 255, 200) if self.flash > 0 else (80, 220, 100)
        sz = self.size
        # Four corners of cube
        corners = [
            self._rotated_corner(-sz, -sz),
            self._rotated_corner( sz, -sz),
            self._rotated_corner( sz,  sz),
            self._rotated_corner(-sz,  sz),
        ]
        ipts = [(int(px), int(py)) for (px, py) in corners]

        # Dark green fill
        pygame.draw.polygon(surf, (10, 50, 15), ipts)
        # Bright green outline
        pygame.draw.polygon(surf, col, ipts, 3)

        # Grid lines at 33% and 66% along each axis
        for t_val in (1/3, 2/3):
            # Horizontal grid line
            lx1, ly1 = (
                _lerp(corners[0][0], corners[1][0], t_val),
                _lerp(corners[0][1], corners[1][1], t_val),
            )
            lx2, ly2 = (
                _lerp(corners[3][0], corners[2][0], t_val),
                _lerp(corners[3][1], corners[2][1], t_val),
            )
            pygame.draw.line(surf, col, (int(lx1), int(ly1)), (int(lx2), int(ly2)), 1)
            # Vertical grid line
            lx3, ly3 = (
                _lerp(corners[0][0], corners[3][0], t_val),
                _lerp(corners[0][1], corners[3][1], t_val),
            )
            lx4, ly4 = (
                _lerp(corners[1][0], corners[2][0], t_val),
                _lerp(corners[1][1], corners[2][1], t_val),
            )
            pygame.draw.line(surf, col, (int(lx3), int(ly3)), (int(lx4), int(ly4)), 1)

        # Red glowing eye at center
        ex, ey = int(self.x), int(self.y)
        pygame.draw.circle(surf, (180,  0,  0), (ex, ey), 12)
        pygame.draw.circle(surf, (255, 60, 60), (ex, ey),  8)
        pygame.draw.circle(surf, (255, 200, 200), (ex, ey), 4)

        # HP bar above cube
        bar_w = sz * 2 + 20
        bar_x = ex - bar_w // 2
        bar_y = ey - sz - 28
        pygame.draw.rect(surf, (60, 0, 0),    (bar_x, bar_y, bar_w, 10), border_radius=4)
        fill = int(bar_w * max(0, self.hp) / self.max_hp)
        pygame.draw.rect(surf, (0, 220, 60),  (bar_x, bar_y, fill, 10), border_radius=4)
        pygame.draw.rect(surf, col,            (bar_x, bar_y, bar_w, 10), 1, border_radius=4)

        lbl = font_tiny.render("THE BORG", True, (80, 255, 120))
        surf.blit(lbl, (ex - lbl.get_width() // 2, bar_y - 18))

# ── Shield Ring ────────────────────────────────────────────────────────────────
shield_surf = None  # created in _init_display()

def draw_shield(shields, max_shields):
    shield_surf.fill((0, 0, 0, 0))
    pct = shields / max_shields
    alpha = int(pct * 55) + 10
    ring_alpha = int(pct * 160) + 40
    pygame.draw.circle(shield_surf, (100, 160, 255, alpha),     (130, 130), 118)
    pygame.draw.circle(shield_surf, (160, 210, 255, ring_alpha), (130, 130), 118, 3)
    for i in range(0, 360, 30):
        rad = math.radians(i)
        x1 = 130 + math.cos(rad) * 100
        y1 = 130 + math.sin(rad) * 100
        x2 = 130 + math.cos(rad) * 118
        y2 = 130 + math.sin(rad) * 118
        pygame.draw.line(shield_surf, (100, 160, 255, ring_alpha // 2),
                         (int(x1), int(y1)), (int(x2), int(y2)), 1)
    screen.blit(shield_surf, (CX - 130, CY - 130))

# ── Red-alert border overlay ───────────────────────────────────────────────────
alert_surf = None  # created in _init_display()
alert_phase = 0.0
BORDER_T = 18   # thickness of red border

def draw_red_alert_border(dt):
    global alert_phase
    alert_phase += dt * 3.5
    a = int(80 + 80 * math.sin(alert_phase))
    col = (200, 0, 0, a)
    alert_surf.fill((0, 0, 0, 0))
    pygame.draw.rect(alert_surf, col, (0, 0, SCREEN_W, BORDER_T))
    pygame.draw.rect(alert_surf, col, (0, SCREEN_H - BORDER_T, SCREEN_W, BORDER_T))
    pygame.draw.rect(alert_surf, col, (0, 0, BORDER_T, SCREEN_H))
    pygame.draw.rect(alert_surf, col, (SCREEN_W - BORDER_T, 0, BORDER_T, SCREEN_H))
    screen.blit(alert_surf, (0, 0))

# ── LCARS HUD ─────────────────────────────────────────────────────────────────
def draw_hud(shields, max_shields, score, wave, enemies_left, wave_total,
             weapon, red_alert, boss_hp, boss_max_hp, power, max_power,
             shields_on, red_alert_manual,
             auto_lock_active=False, auto_lock_charges=0, auto_lock_timer=0.0,
             specials=None, hull=100, max_hull=100,
             all_weapons_active=False, all_weapons_charges=0, all_weapons_timer=0.0,
             paused=False, sfx_on=True):
    surf = screen

    # ── Top bar ──────────────────────────────────────────────────────────────
    if red_alert:
        top_bg = (80, 10, 10)
    else:
        top_bg = LCARS_ORA
    pygame.draw.rect(surf, top_bg, (0, 0, SCREEN_W, TOP_H))
    # Black cutout in center
    pygame.draw.rect(surf, BLACK, (PANEL_W, 0, SCREEN_W - PANEL_W * 2, TOP_H))

    # Left top accent: 22px purple strip + orange pill label
    pygame.draw.rect(surf, LCARS_PURP, (0, 0, 22, TOP_H))
    pill_rect = pygame.Rect(28, 8, 140, TOP_H - 16)
    pygame.draw.rect(surf, LCARS_ORA if not red_alert else (160, 20, 20),
                     pill_rect, border_radius=pill_rect.height // 2)
    lbl = font_tiny.render("TACTICAL STATION", True, BLACK)
    surf.blit(lbl, (pill_rect.centerx - lbl.get_width() // 2,
                    pill_rect.centery - lbl.get_height() // 2))

    # Right top accent: 22px blue strip + stardate
    pygame.draw.rect(surf, LCARS_BLUE, (SCREEN_W - 22, 0, 22, TOP_H))
    sd_lbl = font_tiny.render("STARDATE  47634.44", True,
                               LCARS_GOLD if not red_alert else (255, 100, 100))
    surf.blit(sd_lbl, (SCREEN_W - PANEL_W + 6, TOP_H // 2 - sd_lbl.get_height() // 2))

    # Center: ship name or red alert text
    if red_alert:
        msg = font_med.render("!! RED ALERT !!  THE BORG ARE HERE  !! RED ALERT !!", True,
                              (255, 80, 80))
    else:
        msg = font_med.render("USS ENTERPRISE  NCC-1701-D", True, LCARS_ORA)
    surf.blit(msg, (SCREEN_W // 2 - msg.get_width() // 2,
                    TOP_H // 2 - msg.get_height() // 2))

    # ── Left panel ───────────────────────────────────────────────────────────
    panel_top = TOP_H
    panel_bot = SCREEN_H - BOT_H
    panel_h   = panel_bot - panel_top

    # 22px purple vertical strip
    pygame.draw.rect(surf, LCARS_PURP, (0, panel_top, 22, panel_h))
    # 4px black gap
    pygame.draw.rect(surf, BLACK, (22, panel_top, 4, panel_h))
    # Content area
    pygame.draw.rect(surf, BLACK, (26, panel_top, PANEL_W - 26, panel_h))

    y = panel_top + 10

    # Orange accent separator
    pygame.draw.rect(surf, LCARS_ORA, (26, y, PANEL_W - 26, 6), border_radius=3)
    y += 12

    # "TACTICAL" label
    lbl = font_tiny.render("TACTICAL", True, LCARS_PURP)
    surf.blit(lbl, (28, y)); y += lbl.get_height() + 4

    # CHAPTER / LEVEL
    _ch = (wave - 1) // 10 + 1
    _cl = ((wave - 1) % 10) + 1
    lbl = font_tiny.render(f"CHAPTER  {_ch}", True, LCARS_PURP)
    surf.blit(lbl, (28, y)); y += lbl.get_height() + 2
    wv = font_large.render(f"L.{_cl:02d}", True, LCARS_ORA)
    surf.blit(wv, (28, y)); y += wv.get_height() + 6

    # ENEMIES
    lbl = font_tiny.render("ENEMIES", True, LCARS_PURP)
    surf.blit(lbl, (28, y)); y += lbl.get_height() + 2
    en = font_med.render(f"{enemies_left:02d}", True, LCARS_RED)
    surf.blit(en, (28, y)); y += en.get_height() + 6

    # SCORE
    lbl = font_tiny.render("SCORE", True, LCARS_PURP)
    surf.blit(lbl, (28, y)); y += lbl.get_height() + 2
    sc_lbl = font_med.render(f"{score:06d}", True, LCARS_GOLD)
    surf.blit(sc_lbl, (28, y)); y += sc_lbl.get_height() + 8

    # Orange separator
    pygame.draw.rect(surf, LCARS_ORA, (26, y, PANEL_W - 26, 4), border_radius=2)
    y += 10

    # SYSTEM POWER
    lbl = font_tiny.render("SYSTEM POWER", True, LCARS_PURP)
    surf.blit(lbl, (28, y)); y += lbl.get_height() + 4
    pbar_w = PANEL_W - 36
    draw_power_bar(surf, 28, y, pbar_w, 18, power, max_power)
    y += 22

    # Power tier label
    pct_p = power / max_power
    if pct_p > 0.6:
        tier_col, tier_txt = BORG_GREEN, "HIGH"
    elif pct_p > 0.25:
        tier_col, tier_txt = LCARS_GOLD, "NOMINAL"
    elif pct_p > 0.10:
        tier_col, tier_txt = LCARS_ORA, "LOW"
    else:
        tier_col, tier_txt = LCARS_RED, "CRITICAL"
    tier_lbl = font_small.render(tier_txt, True, tier_col)
    surf.blit(tier_lbl, (28, y)); y += tier_lbl.get_height() + 8

    # Another separator
    pygame.draw.rect(surf, LCARS_ORA, (26, y, PANEL_W - 26, 4), border_radius=2)
    y += 10

    # Boss HP mini bar (only when boss alive)
    if boss_max_hp > 1 and boss_hp > 0:
        lbl = font_tiny.render("BORG HP", True, (100, 255, 120))
        surf.blit(lbl, (28, y)); y += lbl.get_height() + 4
        bbar_w = PANEL_W - 36
        pygame.draw.rect(surf, (30, 0, 0), (28, y, bbar_w, 10), border_radius=4)
        bfill = int(bbar_w * max(0, boss_hp) / boss_max_hp)
        pygame.draw.rect(surf, (0, 200, 60), (28, y, bfill, 10), border_radius=4)
        pygame.draw.rect(surf, (80, 255, 120), (28, y, bbar_w, 10), 1, border_radius=4)
        y += 18

    # SHIELD toggle button
    shield_btn_color = BORG_GREEN if shields_on else LCARS_RED
    draw_lcars_btn(surf, BTN_SHIELD,
                   "SHIELDS: ON" if shields_on else "SHIELDS: OFF",
                   shield_btn_color, lit=shields_on)

    # QUIT button
    draw_lcars_btn(surf, BTN_QUIT, "QUIT GAME", (180, 40, 40), lit=True)

    # SFX toggle button
    if sfx_on:
        draw_lcars_btn(surf, BTN_SFX, "SFX: ON", LCARS_TEAL, lit=True)
    else:
        draw_lcars_btn(surf, BTN_SFX, "SFX: OFF", LCARS_RED, lit=False)

    # PAUSE button
    if paused:
        draw_lcars_btn(surf, BTN_PAUSE, "▶  RESUME", (0, 200, 100), lit=True)
    else:
        draw_lcars_btn(surf, BTN_PAUSE, "⏸  PAUSE", (100, 100, 180), lit=True)

    # INTRUDER ALERT button
    sp_ia = (specials or {}).get('intruder', {})
    if sp_ia.get('active'):
        ia_pulse = int(100+155*abs(math.sin(sp_ia.get('timer',0)*5)))
        draw_lcars_btn(surf, BTN_INTRUDER, f"INTRUDER  {sp_ia['timer']:.1f}s",
                       (ia_pulse, ia_pulse, 0), lit=True)
    elif sp_ia.get('cd', 0) > 0:
        draw_lcars_btn(surf, BTN_INTRUDER, f"INTRUDER  CD{sp_ia['cd']:.0f}s",
                       (60, 60, 0), lit=False)
    else:
        draw_lcars_btn(surf, BTN_INTRUDER, "INTRUDER ALERT", (220, 200, 0), lit=True)

    # WARP BOOST button
    sp_wb = (specials or {}).get('warp', {})
    if sp_wb.get('active'):
        wb_pulse = int(100+155*abs(math.sin(sp_wb.get('timer',0)*6)))
        draw_lcars_btn(surf, BTN_WARP_BOOST, f"MAX POWER  {sp_wb['timer']:.1f}s",
                       (wb_pulse, wb_pulse//2, 0), lit=True)
    elif sp_wb.get('cd', 0) > 0:
        draw_lcars_btn(surf, BTN_WARP_BOOST, f"MAX POWER  CD{sp_wb['cd']:.0f}s",
                       (50, 30, 0), lit=False)
    else:
        draw_lcars_btn(surf, BTN_WARP_BOOST, "MAX POWER", (255, 140, 0), lit=True)

    # ── Right panel ──────────────────────────────────────────────────────────
    rx = SCREEN_W - PANEL_W

    # 22px blue strip on far right
    pygame.draw.rect(surf, LCARS_BLUE, (SCREEN_W - 22, panel_top, 22, panel_h))
    # 4px black gap
    pygame.draw.rect(surf, BLACK, (SCREEN_W - 26, panel_top, 4, panel_h))
    # Content area
    pygame.draw.rect(surf, BLACK, (rx, panel_top, PANEL_W - 26, panel_h))

    sy = panel_top + 10

    # Blue accent bar
    pygame.draw.rect(surf, LCARS_BLUE, (rx, sy, PANEL_W - 26, 6), border_radius=3)
    sy += 12

    # DEFENSIVE SYSTEMS label
    lbl = font_tiny.render("DEFENSIVE SYSTEMS", True, LCARS_BLUE)
    surf.blit(lbl, (rx + 6, sy)); sy += lbl.get_height() + 4

    # SHIELDS label + percentage
    lbl = font_tiny.render("SHIELDS", True, LCARS_BLUE)
    surf.blit(lbl, (rx + 6, sy)); sy += lbl.get_height() + 2

    pct_s = shields / max_shields
    pct_color = ((80, 220, 80) if pct_s > 0.50
                 else (255, 200, 0) if pct_s > 0.25
                 else LCARS_RED)
    pct_txt = font_large.render(f"{shields}%", True, pct_color)
    surf.blit(pct_txt, (rx + 6, sy)); sy += pct_txt.get_height() + 6

    # Vertical shield bar
    bar_h = 90
    bar_x = rx + 30
    pygame.draw.rect(surf, (40, 40, 40), (bar_x, sy, 40, bar_h), border_radius=6)
    fill_h = int(bar_h * shields / max_shields)
    pygame.draw.rect(surf, pct_color, (bar_x, sy + bar_h - fill_h, 40, fill_h),
                     border_radius=6)
    for i in range(1, 5):
        ty2 = sy + int(bar_h * i / 5)
        pygame.draw.line(surf, (60, 60, 80), (bar_x - 2, ty2), (bar_x + 42, ty2), 1)
    sy += bar_h + 10

    # Hull status
    # Hull integrity bar
    _h_pct = hull / max(1, max_hull)
    _hull_col = (80, 220, 80) if _h_pct > 0.66 else (255, 200, 0) if _h_pct > 0.33 else LCARS_RED
    _hull_status = ("NOMINAL" if _h_pct > 0.66 else "DAMAGED" if _h_pct > 0.33 else "CRITICAL")
    lbl = font_small.render(f"HULL: {_hull_status}", True, _hull_col)
    surf.blit(lbl, (rx + 6, sy)); sy += lbl.get_height() + 4
    _hbw = PANEL_W - 36
    pygame.draw.rect(surf, (40, 40, 40), (rx + 6, sy, _hbw, 8), border_radius=3)
    _hfill = int(_hbw * hull / max(1, max_hull))
    pygame.draw.rect(surf, _hull_col, (rx + 6, sy, _hfill, 8), border_radius=3)
    pygame.draw.rect(surf, _hull_col, (rx + 6, sy, _hbw, 8), 1, border_radius=3)
    sy += 14

    # Blue accent separator
    pygame.draw.rect(surf, LCARS_BLUE, (rx, sy, PANEL_W - 26, 4), border_radius=2)
    sy += 10

    # WARP CORE
    lbl = font_tiny.render("WARP CORE", True, LCARS_BLUE)
    surf.blit(lbl, (rx + 6, sy)); sy += lbl.get_height() + 2
    lbl = font_small.render("ONLINE", True, BORG_GREEN)
    surf.blit(lbl, (rx + 6, sy)); sy += lbl.get_height() + 6

    # Low power warning
    if power < 25:
        lbl = font_tiny.render("POWER: CRITICAL", True, LCARS_RED)
        surf.blit(lbl, (rx + 6, sy)); sy += lbl.get_height() + 4

    # RED ALERT button
    ra_label = "STAND DOWN" if red_alert_manual else "RED ALERT"
    draw_lcars_btn(surf, BTN_RED_ALERT, ra_label, ALERT_RED, lit=red_alert_manual)

    # AUTO LOCK button
    if auto_lock_active:
        pulse_c = int(100 + 155 * abs(math.sin(auto_lock_timer * 6)))
        al_color = (0, pulse_c, 0)
        secs_left = f"{auto_lock_timer:.1f}s"
        draw_lcars_btn(surf, BTN_AUTO_LOCK, f"LOCKED  {secs_left}", al_color, lit=True)
    elif auto_lock_charges > 0:
        draw_lcars_btn(surf, BTN_AUTO_LOCK, f"AUTO LOCK  [{auto_lock_charges}]",
                       (255, 220, 0), lit=True)
    else:
        draw_lcars_btn(surf, BTN_AUTO_LOCK, "AUTO LOCK  [USED]",
                       (80, 80, 40), lit=False)

    # PHOTON BURST button
    sp_pb = (specials or {}).get('photon', {})
    pb_ready = sp_pb.get('cd', 0) <= 0 and power >= 55
    if sp_pb.get('cd', 0) > 0:
        draw_lcars_btn(surf, BTN_PHOTON_BURST, f"BURST  CD{sp_pb['cd']:.0f}s",
                       (50, 50, 0), lit=False)
    elif not pb_ready:
        draw_lcars_btn(surf, BTN_PHOTON_BURST, "BURST [LOW PWR]", (80, 60, 0), lit=False)
    else:
        draw_lcars_btn(surf, BTN_PHOTON_BURST, "PHOTON BURST", (255, 230, 30), lit=True)

    # TRACTOR BEAM button
    sp_tr = (specials or {}).get('tractor', {})
    if sp_tr.get('active'):
        tr_pulse = int(80+175*abs(math.sin(sp_tr.get('timer',0)*4)))
        draw_lcars_btn(surf, BTN_TRACTOR, f"TRACTOR  {sp_tr['timer']:.1f}s",
                       (0, tr_pulse//2, tr_pulse), lit=True)
    elif sp_tr.get('cd', 0) > 0:
        draw_lcars_btn(surf, BTN_TRACTOR, f"TRACTOR  CD{sp_tr['cd']:.0f}s",
                       (0, 20, 50), lit=False)
    else:
        draw_lcars_btn(surf, BTN_TRACTOR, "TRACTOR BEAM", (30, 160, 255), lit=True)

    # ALL WEAPONS button
    if all_weapons_active:
        _aw_p = int(80 + 175 * abs(math.sin(all_weapons_timer * 7)))
        draw_lcars_btn(surf, BTN_ALL_WEAPONS, f"ALL WPNS  {all_weapons_timer:.1f}s",
                       (255, _aw_p, 0), lit=True)
    elif all_weapons_charges > 0:
        draw_lcars_btn(surf, BTN_ALL_WEAPONS, f"ALL WEAPONS [{all_weapons_charges}]",
                       (255, 180, 0), lit=True)
    else:
        draw_lcars_btn(surf, BTN_ALL_WEAPONS, "ALL WEAPONS [USED]",
                       (80, 60, 0), lit=False)

    # ── Viewscreen border ────────────────────────────────────────────────────
    pygame.draw.rect(surf, LCARS_ORA,
                     (PANEL_W, TOP_H, SCREEN_W - PANEL_W * 2, SCREEN_H - TOP_H - BOT_H), 2)

    # ── Bottom bar ───────────────────────────────────────────────────────────
    pygame.draw.rect(surf, (15, 10, 5), (0, SCREEN_H - BOT_H, SCREEN_W, BOT_H))
    # Orange separator at top of bottom bar
    pygame.draw.line(surf, LCARS_ORA, (0, SCREEN_H - BOT_H), (SCREEN_W, SCREEN_H - BOT_H), 2)
    # Teal strip far left
    pygame.draw.rect(surf, LCARS_TEAL, (0, SCREEN_H - BOT_H, 22, BOT_H))
    # Purple strip far right
    pygame.draw.rect(surf, LCARS_PURP, (SCREEN_W - 22, SCREEN_H - BOT_H, 22, BOT_H))

    # Phaser button
    ph_lit = (weapon == 'phaser')
    ph_col = LCARS_ORA if ph_lit else (80, 50, 0)
    draw_lcars_btn(surf, BTN_PHASER, "PHASERS", ph_col, lit=ph_lit)

    # Torpedo button
    tp_lit = (weapon == 'torpedo')
    tp_low = (power < TORPEDO_POWER_COST)
    if tp_low:
        draw_lcars_btn(surf, BTN_TORPEDO, "TORPEDO [LOW PWR]",
                       (200, 180, 0), lit=False, border_only=True)
    else:
        tp_col = (255, 220, 60) if tp_lit else (80, 70, 0)
        draw_lcars_btn(surf, BTN_TORPEDO, "PHOTON TORPEDO", tp_col, lit=tp_lit)

    # Center power display between weapon buttons
    cx_bot = (BTN_PHASER.right + BTN_TORPEDO.left) // 2
    pw_bar_w = 300
    pw_bar_x = cx_bot - pw_bar_w // 2
    pw_bar_y = SCREEN_H - BOT_H + 14
    pw_lbl = font_tiny.render("WEAPONS POWER", True, LCARS_GOLD)
    surf.blit(pw_lbl, (cx_bot - pw_lbl.get_width() // 2, pw_bar_y))
    draw_power_bar(surf, pw_bar_x, pw_bar_y + pw_lbl.get_height() + 2,
                   pw_bar_w, 16, power, max_power)
    # Power tier under bar
    tier_lbl2 = font_tiny.render(tier_txt, True, tier_col)
    surf.blit(tier_lbl2, (cx_bot - tier_lbl2.get_width() // 2,
                           pw_bar_y + pw_lbl.get_height() + 22))

    # Hint line at very bottom
    hint = font_tiny.render("TAP WEAPON TO SWITCH  \u2022  TAP SCREEN TO FIRE",
                             True, LCARS_GOLD)
    surf.blit(hint, (SCREEN_W // 2 - hint.get_width() // 2,
                     SCREEN_H - hint.get_height() - 4))

# ── Main Game ──────────────────────────────────────────────────────────────────
def run_game():
    shields     = 100
    max_shields = 100
    score       = 0
    wave        = 1

    enemies     = []
    beams       = []      # PhaserBeam list
    torpedoes   = []      # PhotonTorpedo list
    boss_plasma = []      # BossPlasma list
    explosions  = []
    boss        = None    # BossEnemy or None
    boss_fleet  = []          # list of BossEnemy for wave-10 multi-ship assault
    wave10_mode = False
    hull        = 100.0       # hull integrity (0 = destroyed)
    max_hull    = 100.0
    shield_restore_timer = 0.0   # wave10: seconds until shields auto-restore
    game_over_reason = 'shields'

    weapon      = 'phaser'   # 'phaser' or 'torpedo'
    global sfx_on

    # Power system
    power         = 100.0
    max_power     = 100.0
    shields_on    = False       # must be manually activated
    red_alert_manual = False

    POWER_REGEN  = 7.0    # per second
    SHIELD_DRAIN = 1.5    # per second when shields on
    ALERT_DRAIN  = 1.0    # extra per second in manual red alert
    PHASER_COST  = 5.0
    TORPEDO_COST = 14.0

    # Auto-lock state
    auto_lock_charges  = 1     # start with 1; get 1 per wave clear
    auto_lock_active   = False
    auto_lock_timer    = 0.0
    auto_lock_fire_t   = 0.0   # sub-timer for auto-fire rate

    # Additional tactical abilities
    intruder_active = False;  intruder_timer = 0.0;  intruder_cd = 0.0
    warp_active     = False;  warp_timer     = 0.0;  warp_cd     = 0.0
    tractor_active  = False;  tractor_timer  = 0.0;  tractor_cd  = 0.0
    photon_cd       = 0.0
    PHOTON_BURST_COST = 55.0

    # ALL WEAPONS: dual auto-fire + shield regen, 1 charge per wave
    all_weapons_active  = False
    all_weapons_timer   = 0.0
    all_weapons_charges = 1
    all_wpn_fire_t      = 0.0   # phaser sub-timer
    all_wpn_torp_t      = 0.0   # torpedo sub-timer

    spawn_timer     = 1.5
    spawn_interval  = 2.5
    enemies_per_wave = 6
    wave_total      = enemies_per_wave
    enemies_spawned = 0
    wave_clear_timer = 0.0
    wave_announce    = 2.5    # show wave banner at start
    boss_wave        = False
    red_alert        = False

    game_over = False
    paused    = False
    dt        = 0.0

    while True:
        dt = clock.tick(FPS) / 1000.0

        # ── Events ────────────────────────────────────────────────────────────
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                stop_klaxon()
                pygame.quit()
                sys.exit()

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    stop_klaxon()
                    pygame.quit()
                    sys.exit()
                if game_over:
                    stop_klaxon()
                    return

            if event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                if game_over:
                    stop_klaxon()
                    return

                # ── Named button routing (check before anything else) ──

                # Pause toggle — always available
                if BTN_PAUSE.collidepoint(mx, my):
                    paused = not paused
                    continue

                # SFX toggle — always available
                if BTN_SFX.collidepoint(mx, my):
                    sfx_on = not sfx_on
                    if not sfx_on:
                        stop_klaxon()
                    continue

                # Quit always available
                if BTN_QUIT.collidepoint(mx, my):
                    stop_klaxon()
                    pygame.quit()
                    sys.exit()

                # Block all other input when paused
                if paused:
                    continue

                # Shield toggle
                if BTN_SHIELD.collidepoint(mx, my):
                    shields_on = not shields_on
                    play_oneshot('switch')
                    continue

                # Red Alert toggle
                if BTN_RED_ALERT.collidepoint(mx, my):
                    red_alert_manual = not red_alert_manual
                    if red_alert_manual and not (boss is not None and boss.alive):
                        play_klaxon()
                        speak("Red Alert! All hands to battle stations!")
                    elif not red_alert_manual and not (boss is not None and boss.alive):
                        stop_klaxon()
                        speak("Stand down from Red Alert.")
                    play_oneshot('switch')
                    continue

                # Auto-lock button
                if BTN_AUTO_LOCK.collidepoint(mx, my):
                    if auto_lock_charges > 0 and not auto_lock_active:
                        auto_lock_active  = True
                        auto_lock_timer   = 5.0
                        auto_lock_fire_t  = 0.0
                        auto_lock_charges -= 1
                        play_oneshot('boss_appear')
                        speak("Auto lock engaged.")
                    continue

                # Intruder Alert
                if BTN_INTRUDER.collidepoint(mx, my):
                    if intruder_cd <= 0:
                        intruder_active = True; intruder_timer = 8.0; intruder_cd = 12.0
                        play_oneshot('intruder')
                    continue

                # Warp Boost
                if BTN_WARP_BOOST.collidepoint(mx, my):
                    if warp_cd <= 0:
                        warp_active = True; warp_timer = 6.0; warp_cd = 15.0
                        play_oneshot('warp_boost')
                    continue

                # Photon Burst — 8 torpedoes in all directions
                if BTN_PHOTON_BURST.collidepoint(mx, my):
                    if photon_cd <= 0 and power >= PHOTON_BURST_COST:
                        power -= PHOTON_BURST_COST; photon_cd = 8.0
                        for _ang in range(0, 360, 45):
                            _r = math.radians(_ang)
                            torpedoes.append(PhotonTorpedo(CX + math.cos(_r)*420,
                                                           CY + math.sin(_r)*420))
                        play_oneshot('big_explode')
                    continue

                # Tractor Beam
                if BTN_TRACTOR.collidepoint(mx, my):
                    if tractor_cd <= 0:
                        tractor_active = True; tractor_timer = 6.0; tractor_cd = 12.0
                        play_oneshot('tractor')
                    continue

                # All Weapons
                if BTN_ALL_WEAPONS.collidepoint(mx, my):
                    if all_weapons_charges > 0 and not all_weapons_active:
                        all_weapons_active  = True
                        all_weapons_timer   = 8.0
                        all_weapons_charges -= 1
                        all_wpn_fire_t      = 0.0
                        all_wpn_torp_t      = 0.0
                        play_oneshot('boss_appear')
                    continue

                # Quit button
                if BTN_QUIT.collidepoint(mx, my):
                    stop_klaxon()
                    pygame.quit()
                    sys.exit()

                # Phaser weapon button
                if BTN_PHASER.collidepoint(mx, my):
                    weapon = 'phaser'
                    play_oneshot('switch')
                    continue

                # Torpedo weapon button
                if BTN_TORPEDO.collidepoint(mx, my):
                    if power >= TORPEDO_COST:
                        weapon = 'torpedo'
                        play_oneshot('switch')
                    continue

                # Bottom bar (center area) — no extra action needed, buttons handled above
                if my >= SCREEN_H - BOT_H and PANEL_W <= mx <= SCREEN_W - PANEL_W:
                    continue

                # Side panels: ignore
                if mx < PANEL_W or mx > SCREEN_W - PANEL_W:
                    continue
                # Top bar: ignore
                if my < TOP_H or my >= SCREEN_H - BOT_H:
                    continue

                # ── Fire weapon ──
                if weapon == 'phaser':
                    if power >= PHASER_COST:
                        power -= PHASER_COST
                        beam = PhaserBeam(mx, my)
                        hit_enemies, hit_boss_flag = beam.check_hits(enemies, boss)
                        play_oneshot('phaser')
                        beams.append(beam)
                        for e in hit_enemies:
                            killed = e.hit()
                            if killed:
                                score += Enemy.SCORES[e.kind]
                                # Power bonus on kill
                                power = min(max_power, power + 8)
                                explosions.append(
                                    Explosion(e.x, e.y, e.color, n=20,
                                              big=(e.kind == 'borg')))
                                play_oneshot('explode')
                        if hit_boss_flag and boss is not None and boss.alive:
                            dead = boss.take_phaser_damage()
                            if dead:
                                score += BossEnemy.SCORE
                                # Boss kill power bonuses
                                power = min(max_power, power + 50)
                                max_power = min(150, max_power + 10)
                                explosions.append(
                                    Explosion(boss.x, boss.y, (0, 255, 80),
                                              n=40, big=True))
                                play_oneshot('big_explode')
                                stop_klaxon()
                                red_alert_manual = False
                                red_alert = False
                                speak("Hostile vessel destroyed. Stand down from Red Alert.")
                                boss = None
                        # Boss fleet manual phaser hits
                        for _fbp in boss_fleet:
                            if not _fbp.alive:
                                continue
                            _fbpd = _seg_dist(_fbp.x, _fbp.y, beam.x1, beam.y1, beam.x2, beam.y2)
                            if _fbpd < _fbp.size + 4:
                                if _fbp.take_phaser_damage():
                                    score += BossEnemy.SCORE
                                    power = min(max_power, power + 50)
                                    explosions.append(
                                        Explosion(_fbp.x, _fbp.y, (0, 255, 80), n=40, big=True))
                                    play_oneshot('big_explode')

                elif weapon == 'torpedo':
                    if power >= TORPEDO_COST:
                        power -= TORPEDO_COST
                        torp = PhotonTorpedo(mx, my)
                        torpedoes.append(torp)
                        play_oneshot('torpedo')

        # ── Update ────────────────────────────────────────────────────────────
        if not game_over and not paused:

            # ── Power regen ──
            _regen = POWER_REGEN * (3.0 if warp_active else (2.0 if not shields_on else 1.0))
            power = min(max_power, power + _regen * dt)

            # Wave 10: weapons power stays full
            if wave10_mode:
                power = max_power

            # ── Shield drain ──
            if shields_on:
                if not wave10_mode:
                    power -= SHIELD_DRAIN * dt
                    if power <= 0:
                        power = 0.0
                        shields_on = False   # auto-shutoff
                else:
                    # Wave 10: shields drain on their own (Borg ECM disruption)
                    shields -= 1.5 * dt
                    if shields <= 0:
                        shields = 0
                        shields_on = False
                        shield_restore_timer = 5.0   # auto-restore in 5s

            # Wave 10: auto-restore shields when restore timer expires
            if wave10_mode and not shields_on and shield_restore_timer > 0:
                shield_restore_timer -= dt
                if shield_restore_timer <= 0:
                    shield_restore_timer = 0.0
                    shields_on = True
                    shields = min(max_shields, shields + 40)  # partial restore

            # ── Manual red alert drain ──
            if red_alert_manual:
                power -= ALERT_DRAIN * dt
                power = max(0.0, power)

            # ── red_alert flag: boss wave OR manual ──
            red_alert = red_alert_manual or (boss is not None and boss.alive)

            # ── Cooldown timers ──
            if intruder_cd > 0: intruder_cd = max(0, intruder_cd - dt)
            if warp_cd     > 0: warp_cd     = max(0, warp_cd     - dt)
            if tractor_cd  > 0: tractor_cd  = max(0, tractor_cd  - dt)
            if photon_cd   > 0: photon_cd   = max(0, photon_cd   - dt)

            # ── Intruder alert duration ──
            if intruder_active:
                intruder_timer -= dt
                if intruder_timer <= 0: intruder_active = False

            # ── Warp boost: triple regen while active ──
            if warp_active:
                warp_timer -= dt
                if warp_timer <= 0: warp_active = False

            # ── Tractor beam duration ──
            if tractor_active:
                tractor_timer -= dt
                if tractor_timer <= 0: tractor_active = False

            # ── Auto-lock: countdown + auto-fire ──
            if auto_lock_active:
                auto_lock_timer  -= dt
                auto_lock_fire_t -= dt
                if auto_lock_timer <= 0:
                    auto_lock_active = False
                    auto_lock_timer  = 0.0
                elif auto_lock_fire_t <= 0:
                    auto_lock_fire_t = 0.18   # fire every 0.18s
                    # Pick nearest target (boss first, then closest enemy)
                    target = None
                    if boss and boss.alive:
                        target = (boss.x, boss.y)
                    else:
                        _fl_alive = [b for b in boss_fleet if b.alive]
                        if _fl_alive:
                            _ft = min(_fl_alive, key=lambda b: math.hypot(b.x - CX, b.y - CY))
                            target = (_ft.x, _ft.y)
                        elif enemies:
                            nearest = min(enemies, key=lambda e: math.hypot(e.x - CX, e.y - CY))
                            target = (nearest.x, nearest.y)
                    if target:
                        ab = PhaserBeam(target[0], target[1])
                        hit_e, hit_b = ab.check_hits(enemies, boss)
                        play_oneshot('phaser')
                        beams.append(ab)
                        for e in hit_e:
                            if e.hit(1):
                                score += Enemy.SCORES[e.kind]
                                power  = min(max_power, power + 10)
                                explosions.append(Explosion(e.x, e.y, e.color, n=20, big=(e.kind=='borg')))
                                play_oneshot('explode')
                        if hit_b and boss and boss.alive:
                            if boss.take_phaser_damage():
                                score += BossEnemy.SCORE
                                power  = min(max_power + 10, power + 50)
                                max_power = min(150, max_power + 10)
                                explosions.append(Explosion(boss.x, boss.y, (0,255,80), n=40, big=True))
                                play_oneshot('big_explode')
                                stop_klaxon()
                                red_alert = False; red_alert_manual = False
                                speak("Hostile vessel destroyed. Stand down from Red Alert.")
                                boss = None
                        # Boss fleet auto-lock hits
                        for _fba in boss_fleet:
                            if not _fba.alive:
                                continue
                            _fbd = _seg_dist(_fba.x, _fba.y, ab.x1, ab.y1, ab.x2, ab.y2)
                            if _fbd < _fba.size + 4:
                                if _fba.take_phaser_damage():
                                    score += BossEnemy.SCORE
                                    explosions.append(
                                        Explosion(_fba.x, _fba.y, (0,255,80), n=40, big=True))
                                    play_oneshot('big_explode')

            # ── Shield slow regen (always on when shields_on, not wave10 mode) ──
            if shields_on and shields < max_shields and not wave10_mode and not all_weapons_active:
                shields = min(max_shields, shields + 1.5 * dt)

            # ── ALL WEAPONS: dual auto-fire + fast shield regen ──
            if all_weapons_active:
                all_weapons_timer -= dt
                all_wpn_fire_t    -= dt
                all_wpn_torp_t    -= dt
                shields_on = True
                shields = min(max_shields, shields + 6.0 * dt)   # fast regen

                if all_weapons_timer <= 0:
                    all_weapons_active = False
                    all_weapons_timer  = 0.0
                else:
                    # Find target: boss fleet > single boss > nearest enemy
                    _awt = None
                    if boss and boss.alive:
                        _awt = (boss.x, boss.y)
                    else:
                        _awfl = [b for b in boss_fleet if b.alive]
                        if _awfl:
                            _awft = min(_awfl, key=lambda b: math.hypot(b.x-CX, b.y-CY))
                            _awt = (_awft.x, _awft.y)
                        elif enemies:
                            _awn = min(enemies, key=lambda e: math.hypot(e.x-CX, e.y-CY))
                            _awt = (_awn.x, _awn.y)

                    if _awt:
                        # Auto phaser burst
                        if all_wpn_fire_t <= 0:
                            all_wpn_fire_t = 0.18
                            _awb = PhaserBeam(_awt[0], _awt[1])
                            _awhe, _awhb = _awb.check_hits(enemies, boss)
                            play_oneshot('phaser')
                            beams.append(_awb)
                            for _awe in _awhe:
                                if _awe.hit(1):
                                    score += Enemy.SCORES[_awe.kind]
                                    power  = min(max_power, power + 10)
                                    explosions.append(Explosion(_awe.x, _awe.y, _awe.color, n=20, big=(_awe.kind=='borg')))
                                    play_oneshot('explode')
                            if _awhb and boss and boss.alive:
                                if boss.take_phaser_damage():
                                    score += BossEnemy.SCORE; power = min(max_power, power+50)
                                    max_power = min(150, max_power+10)
                                    explosions.append(Explosion(boss.x, boss.y, (0,255,80), n=40, big=True))
                                    play_oneshot('big_explode'); stop_klaxon()
                                    red_alert = False; red_alert_manual = False; boss = None
                            for _awfl2 in boss_fleet:
                                if not _awfl2.alive: continue
                                if _seg_dist(_awfl2.x,_awfl2.y,_awb.x1,_awb.y1,_awb.x2,_awb.y2) < _awfl2.size+4:
                                    if _awfl2.take_phaser_damage():
                                        score += BossEnemy.SCORE
                                        explosions.append(Explosion(_awfl2.x,_awfl2.y,(0,255,80),n=40,big=True))
                                        play_oneshot('big_explode')

                        # Auto torpedo burst
                        if all_wpn_torp_t <= 0:
                            all_wpn_torp_t = 0.55
                            torpedoes.append(PhotonTorpedo(_awt[0], _awt[1]))
                            play_oneshot('torpedo')

            # ── Wave management ──
            if boss_wave:
                if wave10_mode:
                    wave_done = bool(boss_fleet) and all(not b.alive for b in boss_fleet)
                else:
                    wave_done = (boss is None or not boss.alive)
            else:
                wave_done = (enemies_spawned >= wave_total and len(enemies) == 0)

            if wave_done:
                wave_clear_timer += dt
                if wave_clear_timer >= 2.2:
                    wave             += 1
                    wave_clear_timer  = 0.0

                    if wave == 5:
                        # Chapter 1 Level 5: fast blue scout swarm (no Borg boss here)
                        boss_wave        = False
                        wave10_mode      = False
                        boss_fleet       = []
                        enemies     = []
                        boss_plasma = []
                        torpedoes   = []
                        enemies_per_wave = 15
                        wave_total       = 15
                        enemies_spawned  = 0
                        spawn_timer      = 0.35   # rapid spawn

                    elif wave % 10 == 0:
                        # Chapter-final wave: Borg FLEET assault (wave 10, 20, 30…)
                        enemies     = []
                        boss_plasma = []
                        torpedoes   = []
                        boss_wave       = True
                        wave10_mode     = True
                        wave_total      = 1
                        enemies_spawned = 1
                        shield_restore_timer = 0.0
                        boss_fleet  = []
                        _vid = (wave // 10) * 2 - 1   # vid 1 @ wave10, 3 @ wave20 …
                        play_cutscene(_vid)
                        _fleet_xs = [PANEL_W + 120, SCREEN_W - PANEL_W - 120]
                        boss_fleet = [BossEnemy(wave, start_x=_fx, start_y=CY - 200)
                                      for _fx in _fleet_xs]
                        red_alert = True
                        play_oneshot('boss_appear')
                        play_klaxon()

                    elif wave % 5 == 0:
                        # Mid-chapter boss: single Borg cube (wave 15, 25, 35…)
                        enemies     = []
                        boss_plasma = []
                        torpedoes   = []
                        boss_wave       = True
                        wave10_mode     = False
                        boss_fleet      = []
                        wave_total      = 1
                        enemies_spawned = 1
                        boss = BossEnemy(wave)
                        red_alert = True
                        play_oneshot('boss_appear')
                        play_klaxon()
                        speak("Red Alert! Red Alert! All hands to battle stations! "
                              "The Borg are here!")

                    else:
                        boss_wave        = False
                        wave10_mode      = False
                        boss_fleet       = []
                        # New chapter start (wave 11, 21, 31…): play chapter intro video
                        if wave % 10 == 1 and wave > 1:
                            _ch_vid = (wave // 10) * 2   # vid 2 @ wave11, 4 @ wave21 …
                            play_cutscene(_ch_vid)
                        enemies_per_wave = 6 + wave * 2
                        wave_total       = enemies_per_wave
                        enemies_spawned  = 0
                        spawn_timer      = 1.5

                    wave_announce        = 2.5
                    auto_lock_charges   += 1   # earn 1 charge every wave clear
                    all_weapons_charges += 1   # earn 1 ALL WEAPONS charge every wave clear
            else:
                wave_clear_timer = 0.0

            wave_announce = max(0.0, wave_announce - dt)

            # ── Spawn regular enemies ──
            if not boss_wave:
                spawn_timer -= dt
                if spawn_timer <= 0 and enemies_spawned < wave_total:
                    if wave == 5:
                        _spawn_kinds = ['scout']          # fast blue swarm
                        _next_t      = 0.35               # rapid spawn
                    elif wave < 10:
                        _spawn_kinds = ['warbird', 'klingon']   # no Borg in Ch.1
                        _next_t      = max(0.4, spawn_interval - wave * 0.18)
                    else:
                        _spawn_kinds = ENEMY_TYPES
                        _next_t      = max(0.4, spawn_interval - wave * 0.18)
                    enemies.append(Enemy(wave, kinds=_spawn_kinds))
                    enemies_spawned += 1
                    spawn_timer = _next_t

            # ── Update boss ──
            if boss is not None and boss.alive:
                _orig_s = boss.strafe_speed
                boss.strafe_speed *= (0.35 if tractor_active else 1.0)
                result = boss.update(dt)
                boss.strafe_speed = _orig_s
                if result == 'fire':
                    boss_plasma.append(BossPlasma(boss.x, boss.y))

            # ── Update boss fleet (wave 10) ──
            for _fb in boss_fleet:
                if not _fb.alive:
                    continue
                _orig_sf = _fb.strafe_speed
                _fb.strafe_speed *= (0.35 if tractor_active else 1.0)
                _res_f = _fb.update(dt)
                _fb.strafe_speed = _orig_sf
                if _res_f == 'fire':
                    boss_plasma.append(BossPlasma(_fb.x, _fb.y))

            # ── Update boss plasma bolts ──
            next_bp = []
            for bp in boss_plasma:
                hit_ent = bp.update()
                if hit_ent:
                    if shields_on and shields > 0:
                        shields -= BossPlasma.DAMAGE     # 15 absorbed by shields
                        hull    -= 3.0                   # small bleed through
                    else:
                        hull    -= 18.0                  # full hull impact when unshielded
                    shields = max(0, shields)
                    play_oneshot('shield_hit')
                    explosions.append(
                        Explosion(CX, CY, (0, 200, 50), n=16, big=False))
                    if hull <= 0:
                        hull = 0.0
                        game_over = True
                        game_over_reason = 'hull'
                elif bp.alive:
                    next_bp.append(bp)
            boss_plasma = next_bp

            # ── Update regular enemies ──
            next_enemies = []
            _spd_mod = 0.35 if tractor_active else 1.0
            for e in enemies:
                _orig = e.speed
                e.speed *= _spd_mod
                hit_center = e.update(dt)
                e.speed = _orig
                if hit_center:
                    if shields_on and shields > 0:
                        shields -= 10    # absorbed by shields
                        hull    -= 4.0   # small bleed through
                    else:
                        hull    -= 14.0  # direct hull impact
                    shields = max(0, shields)
                    play_oneshot('shield_hit')
                    explosions.append(
                        Explosion(CX, CY, LCARS_RED, n=22, big=True))
                    if hull <= 0:
                        hull = 0.0
                        game_over = True
                        game_over_reason = 'hull'
                elif e.alive:
                    next_enemies.append(e)
            enemies = next_enemies

            # ── Update phaser beams (fade only, hits already applied) ──
            for b in beams:
                b.update(dt)
            beams = [b for b in beams if b.alive]

            # ── Update photon torpedoes ──
            next_torps = []
            for torp in torpedoes:
                # Proximity check before moving (also check fleet)
                _fleet_prox = any(
                    _fb.alive and math.hypot(torp.x - _fb.x, torp.y - _fb.y) < _fb.size + 8
                    for _fb in boss_fleet
                )
                if torp.proximity_check(enemies, boss) or _fleet_prox:
                    torp.alive    = False
                    torp.exploded = True
                    torp.update()   # advance one step for position
                    # Apply AoE
                    gained, hit_boss_flag = torp.aoe_check(enemies, boss)
                    score += gained
                    # Fleet AoE
                    for _fbt in boss_fleet:
                        if _fbt.alive and math.hypot(torp.x - _fbt.x, torp.y - _fbt.y) < torp.AOE_R:
                            _fbt.hp -= 3; _fbt.flash = 0.15
                            if _fbt.hp <= 0:
                                _fbt.hp = 0; _fbt.alive = False
                                score += BossEnemy.SCORE
                                explosions.append(Explosion(_fbt.x, _fbt.y, (0,255,80), n=40, big=True))
                                play_oneshot('big_explode')
                    # Power bonus for kills from AoE
                    for e in enemies:
                        if not e.alive:
                            power = min(max_power, power + 8)
                    explosions.append(
                        Explosion(torp.x, torp.y, (255, 120, 0), n=30, big=True))
                    play_oneshot('big_explode')
                    if hit_boss_flag and boss is not None and not boss.alive:
                        score += BossEnemy.SCORE
                        power = min(max_power, power + 50)
                        max_power = min(150, max_power + 10)
                        explosions.append(
                            Explosion(boss.x, boss.y, (0, 255, 80), n=40, big=True))
                        stop_klaxon()
                        red_alert_manual = False
                        red_alert = False
                        speak("Hostile vessel destroyed. Stand down from Red Alert.")
                        boss = None
                    # Explosion for dead enemies
                    for e in enemies:
                        if not e.alive:
                            explosions.append(
                                Explosion(e.x, e.y, e.color, n=16,
                                          big=(e.kind == 'borg')))
                            play_oneshot('explode')
                    continue

                torp.update()

                if torp.exploded:
                    # Reached target point
                    gained, hit_boss_flag = torp.aoe_check(enemies, boss)
                    score += gained
                    # Fleet AoE at target
                    for _fbt2 in boss_fleet:
                        if _fbt2.alive and math.hypot(torp.x - _fbt2.x, torp.y - _fbt2.y) < torp.AOE_R:
                            _fbt2.hp -= 3; _fbt2.flash = 0.15
                            if _fbt2.hp <= 0:
                                _fbt2.hp = 0; _fbt2.alive = False
                                score += BossEnemy.SCORE
                                explosions.append(Explosion(_fbt2.x, _fbt2.y, (0,255,80), n=40, big=True))
                                play_oneshot('big_explode')
                    for e in enemies:
                        if not e.alive:
                            power = min(max_power, power + 8)
                    explosions.append(
                        Explosion(torp.x, torp.y, (255, 120, 0), n=30, big=True))
                    play_oneshot('big_explode')
                    if hit_boss_flag and boss is not None and not boss.alive:
                        score += BossEnemy.SCORE
                        power = min(max_power, power + 50)
                        max_power = min(150, max_power + 10)
                        explosions.append(
                            Explosion(boss.x, boss.y, (0, 255, 80), n=40, big=True))
                        stop_klaxon()
                        red_alert_manual = False
                        red_alert = False
                        speak("Hostile vessel destroyed. Stand down from Red Alert.")
                        boss = None
                    for e in enemies:
                        if not e.alive:
                            explosions.append(
                                Explosion(e.x, e.y, e.color, n=16,
                                          big=(e.kind == 'borg')))
                            play_oneshot('explode')
                elif torp.alive:
                    next_torps.append(torp)

            torpedoes = next_torps
            enemies   = [e for e in enemies if e.alive]

            # ── Update explosions ──
            for ex in explosions:
                ex.update(dt)
            explosions = [ex for ex in explosions if ex.alive]

            # Hull slow recharge (0.4/s)
            hull = min(max_hull, hull + 0.4 * dt)

            # Shield / power clamp
            shields = max(0, min(max_shields, shields))
            power   = max(0.0, min(max_power, power))

        # ── Draw ──────────────────────────────────────────────────────────────
        screen.fill(BLACK)
        draw_stars(dt)

        # Shield ring — only visible when shields are on
        if shields_on:
            draw_shield(shields, max_shields)

        # Enterprise-D
        draw_enterprise(CX, CY - 8)

        # Boss
        if boss is not None and boss.alive:
            boss.draw(screen)

        # Boss fleet (wave 10)
        for _fbd in boss_fleet:
            if _fbd.alive:
                _fbd.draw(screen)

        # Boss plasma bolts
        for bp in boss_plasma:
            bp.draw(screen)

        # Regular enemies
        for e in enemies:
            e.draw(screen)

        # Phaser beams
        for b in beams:
            b.draw(screen)

        # Torpedoes
        for torp in torpedoes:
            torp.draw(screen)

        # Explosions
        for ex in explosions:
            ex.draw(screen)

        # Intruder alert: amber pulsing border
        if intruder_active:
            _ia_alpha = int(80 + 80*math.sin(intruder_timer * 7))
            _ia_surf = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            for _rect in [(0,0,SCREEN_W,10),(0,SCREEN_H-10,SCREEN_W,10),
                          (0,0,10,SCREEN_H),(SCREEN_W-10,0,10,SCREEN_H)]:
                pygame.draw.rect(_ia_surf, (220, 200, 0, _ia_alpha), _rect)
            screen.blit(_ia_surf, (0,0))

        # Tractor beam: expanding blue rings from Enterprise
        if tractor_active:
            for _ri in range(3):
                _frac = ((_ri * 0.33) + (1.0 - tractor_timer / 6.0)) % 1.0
                _rr = int(_frac * 320)
                _ra = int(200 * (1.0 - _frac))
                if _rr > 0 and _ra > 0:
                    _tr_surf = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
                    pygame.draw.circle(_tr_surf, (30, 140, 255, _ra), (CX, CY), _rr, 2)
                    screen.blit(_tr_surf, (0,0))

        # Warp boost: golden shimmer on power bar area (just a small overlay near left panel)
        if warp_active:
            _wb_alpha = int(60 + 60*math.sin(warp_timer * 8))
            _wb_surf = pygame.Surface((PANEL_W, SCREEN_H), pygame.SRCALPHA)
            _wb_surf.fill((255, 160, 0, _wb_alpha))
            screen.blit(_wb_surf, (0, 0))

        # HUD — boss HP and remaining count (handles both single boss and fleet)
        if wave10_mode and boss_fleet:
            _fl_alive = [b for b in boss_fleet if b.alive]
            boss_hp     = sum(b.hp for b in _fl_alive)
            boss_max_hp = sum(b.max_hp for b in boss_fleet)
            remaining   = len(_fl_alive)
        else:
            boss_hp     = boss.hp     if boss else 0
            boss_max_hp = boss.max_hp if boss else 1
            remaining = (wave_total - enemies_spawned) + len(enemies)
            if boss_wave and boss is not None and boss.alive:
                remaining = 1
            elif boss_wave and (boss is None or not boss.alive):
                remaining = 0

        # Auto-lock targeting reticles
        if auto_lock_active:
            pulse = int(180 + 75 * math.sin(auto_lock_timer * 8))
            lock_col = (0, pulse, 0)
            for e in enemies:
                if e.alive:
                    r = e.size + 10
                    cx2, cy2 = int(e.x), int(e.y)
                    pygame.draw.circle(screen, lock_col, (cx2, cy2), r, 2)
                    pygame.draw.line(screen, lock_col, (cx2-r-6, cy2), (cx2-r+4, cy2), 2)
                    pygame.draw.line(screen, lock_col, (cx2+r-4, cy2), (cx2+r+6, cy2), 2)
                    pygame.draw.line(screen, lock_col, (cx2, cy2-r-6), (cx2, cy2-r+4), 2)
                    pygame.draw.line(screen, lock_col, (cx2, cy2+r-4), (cx2, cy2+r+6), 2)
            if boss and boss.alive:
                r = boss.SIZE + 14
                bx2, by2 = int(boss.x), int(boss.y)
                pygame.draw.rect(screen, (0, 255, 0),
                                 (bx2-r, by2-r, r*2, r*2), 2)
                pygame.draw.line(screen, (0,255,0), (bx2-r-8,by2),(bx2-r+6,by2), 2)
                pygame.draw.line(screen, (0,255,0), (bx2+r-6,by2),(bx2+r+8,by2), 2)
                pygame.draw.line(screen, (0,255,0), (bx2,by2-r-8),(bx2,by2-r+6), 2)
                pygame.draw.line(screen, (0,255,0), (bx2,by2+r-6),(bx2,by2+r+8), 2)
            # Fleet reticles (wave 10)
            for _fbr in boss_fleet:
                if _fbr.alive:
                    _rr = _fbr.SIZE + 14
                    _rx2, _ry2 = int(_fbr.x), int(_fbr.y)
                    pygame.draw.rect(screen, (0,255,0), (_rx2-_rr,_ry2-_rr,_rr*2,_rr*2), 2)
                    pygame.draw.line(screen,(0,255,0),(_rx2-_rr-8,_ry2),(_rx2-_rr+6,_ry2),2)
                    pygame.draw.line(screen,(0,255,0),(_rx2+_rr-6,_ry2),(_rx2+_rr+8,_ry2),2)
                    pygame.draw.line(screen,(0,255,0),(_rx2,_ry2-_rr-8),(_rx2,_ry2-_rr+6),2)
                    pygame.draw.line(screen,(0,255,0),(_rx2,_ry2+_rr-6),(_rx2,_ry2+_rr+8),2)

        draw_hud(shields, max_shields, score, wave,
                 max(0, remaining), wave_total,
                 weapon, red_alert, boss_hp, boss_max_hp,
                 power, max_power, shields_on, red_alert_manual,
                 auto_lock_active, auto_lock_charges, auto_lock_timer,
                 hull=int(hull), max_hull=int(max_hull),
                 all_weapons_active=all_weapons_active,
                 all_weapons_charges=all_weapons_charges,
                 all_weapons_timer=all_weapons_timer,
                 paused=paused, sfx_on=sfx_on,
                 specials={
                     'intruder': {'active': intruder_active, 'timer': intruder_timer, 'cd': intruder_cd},
                     'warp':     {'active': warp_active,     'timer': warp_timer,     'cd': warp_cd},
                     'photon':   {'cd': photon_cd},
                     'tractor':  {'active': tractor_active,  'timer': tractor_timer,  'cd': tractor_cd},
                 })

        # Red alert border overlay
        if red_alert:
            draw_red_alert_border(dt)

        # Wave announce banner
        if wave_announce > 0 and not game_over:
            fade = min(1.0, wave_announce, 2.5 - wave_announce) * 2
            fade = min(1.0, fade)
            _ch_ann = (wave - 1) // 10 + 1
            _cl_ann = ((wave - 1) % 10) + 1
            if boss_wave:
                if wave10_mode:
                    msg1 = font_huge.render("BORG FLEET INCOMING", True, (255, 60, 60))
                    msg2 = font_med.render(f"CH.{_ch_ann}  FINAL BATTLE — ALL HANDS TO BATTLE STATIONS", True, LCARS_RED)
                else:
                    msg1 = font_huge.render("!! THE BORG !!", True, (255, 60, 60))
                    msg2 = font_med.render("RESISTANCE IS FUTILE", True, LCARS_RED)
            elif wave == 5:
                msg1 = font_huge.render("INCOMING FIGHTERS", True, (80, 180, 255))
                msg2 = font_med.render("15 SCOUT SHIPS DETECTED — BRACE FOR IMPACT", True, LCARS_BLUE)
            elif _cl_ann == 1 and wave > 1:
                msg1 = font_huge.render(f"CHAPTER  {_ch_ann}", True, LCARS_ORA)
                msg2 = font_med.render("NEW CHAPTER — ENGAGE!", True, LCARS_GOLD)
            else:
                msg1 = font_huge.render(f"CHAPTER {_ch_ann}  LEVEL {_cl_ann}", True, LCARS_ORA)
                msg2 = font_med.render("INCOMING HOSTILES DETECTED", True, LCARS_GOLD)
            mid_y = (TOP_H + SCREEN_H - BOT_H) // 2
            x1 = SCREEN_W // 2 - msg1.get_width() // 2
            x2 = SCREEN_W // 2 - msg2.get_width() // 2
            screen.blit(msg1, (x1, mid_y - 60))
            screen.blit(msg2, (x2, mid_y + 10))

        # Wave clear message
        if wave_clear_timer > 0 and not game_over:
            msg = font_large.render("SECTOR CLEAR \u2014 STAND BY", True, LCARS_TEAL)
            mid_y = (TOP_H + SCREEN_H - BOT_H) // 2
            screen.blit(msg, (SCREEN_W // 2 - msg.get_width() // 2, mid_y - 25))

        # Pause overlay
        if paused and not game_over:
            ov = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            ov.fill((0, 0, 0, 160))
            screen.blit(ov, (0, 0))
            pt1 = font_huge.render("PAUSED", True, LCARS_ORA)
            pt2 = font_med.render("TAP  PAUSE  TO  RESUME", True, LCARS_GOLD)
            mid_y = (TOP_H + SCREEN_H - BOT_H) // 2
            screen.blit(pt1, (SCREEN_W // 2 - pt1.get_width() // 2, mid_y - 50))
            screen.blit(pt2, (SCREEN_W // 2 - pt2.get_width() // 2, mid_y + 30))

        # Game Over overlay
        if game_over:
            ov = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            ov.fill((0, 0, 0, 170))
            screen.blit(ov, (0, 0))

            if game_over_reason == 'hull':
                t1 = font_huge.render("HULL BREACHED", True, LCARS_RED)
            else:
                t1 = font_huge.render("SHIELDS DEPLETED", True, LCARS_RED)
            t2 = font_large.render("USS ENTERPRISE DESTROYED", True, LCARS_ORA)
            t3 = font_med.render(f"FINAL SCORE:  {score:,}", True, LCARS_GOLD)
            t4 = font_small.render("TAP SCREEN OR PRESS ANY KEY TO RETRY", True, WHITE)

            screen.blit(t1, (SCREEN_W // 2 - t1.get_width() // 2, SCREEN_H // 2 - 130))
            screen.blit(t2, (SCREEN_W // 2 - t2.get_width() // 2, SCREEN_H // 2 -  65))
            screen.blit(t3, (SCREEN_W // 2 - t3.get_width() // 2, SCREEN_H // 2 +   5))
            screen.blit(t4, (SCREEN_W // 2 - t4.get_width() // 2, SCREEN_H // 2 +  80))

        pygame.display.flip()

# ── Entry point ────────────────────────────────────────────────────────────────
def _android_main():
    _init_display()
    while True:
        run_game()

if __name__ == "__main__":
    _android_main()

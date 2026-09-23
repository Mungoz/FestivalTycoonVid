"""Festival Tycoon - quirky/eerie teaser trailer generator.

Everything (pixel art, UI, music, SFX) is generated procedurally.
Run:  uv run --no-project --with pillow --with numpy --with scipy python make_trailer.py
Needs ffmpeg on PATH.
"""
import math
import random
import subprocess
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from scipy.signal import butter, sosfilt

OUT = sys.argv[1] if len(sys.argv) > 1 else "festival_tycoon_trailer.mp4"
W, H = 320, 180          # world pixel-art resolution (visible slice)
WW = 420                 # world width (camera pans across it)
OW, OH = 1280, 720       # output resolution
FPS = 24
BPM = 128
BEAT = 60 / BPM

# timeline (seconds)
T_S2, T_S3, T_S4, T_S5 = 4.5, 8.5, 10.0, 14.0
CUT = 1.65
T_S6 = T_S5 + 5 * CUT     # 22.25
T_S7 = T_S6 + 4.5       # 26.75
DUR = T_S7 + 5.25        # 32.0
NF = int(round(DUR * FPS))

FD = "C:/Windows/Fonts/"
_fc = {}


def font(name, size):
    k = (name, size)
    if k not in _fc:
        _fc[k] = ImageFont.truetype(FD + name, size)
    return _fc[k]


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def lerp(a, b, x):
    return a + (b - a) * x


def rgb_lerp(a, b, x):
    return tuple(int(a[i] + (b[i] - a[i]) * x) for i in range(3))


# ---------------------------------------------------------------- world data
MODES = {
    "day": dict(sky=((105, 185, 250), (200, 235, 255)), hill=(120, 185, 110), tree=(50, 125, 65),
                grass=(100, 190, 80), grass2=(92, 178, 72), dark=False),
    "night": dict(sky=((6, 6, 18), (28, 18, 44)), hill=(18, 24, 34), tree=(8, 12, 16),
                  grass=(14, 26, 20), grass2=(12, 22, 18), dark=True),
    "overcast": dict(sky=((110, 115, 125), (165, 165, 165)), hill=(95, 120, 90), tree=(45, 80, 50),
                     grass=(110, 110, 70), grass2=(100, 96, 60), dark=False),
    "neon": dict(sky=((20, 4, 36), (70, 16, 84)), hill=(30, 10, 45), tree=(18, 6, 28),
                 grass=(30, 14, 40), grass2=(26, 12, 36), dark=True),
    "sunset": dict(sky=((70, 50, 120), (255, 150, 90)), hill=(110, 90, 100), tree=(60, 50, 70),
                   grass=(90, 120, 70), grass2=(84, 110, 66), dark=False),
}

R = random.Random(7)
TREES = [(x, R.randint(74, 79), R.randint(5, 8)) for x in range(-4, WW + 8, 7)]
STARS = [(R.randrange(WW), R.randrange(70), R.random() * 6.28) for _ in range(90)]
CLOUDS = [(R.randrange(WW), R.randint(8, 40), R.randint(14, 30)) for _ in range(6)]
MUD = [(R.randrange(WW), R.randint(100, 178), R.randint(6, 16)) for _ in range(18)]
SHIRTS = [(230, 60, 70), (250, 200, 60), (70, 160, 230), (240, 120, 200), (120, 220, 120),
          (250, 250, 250), (255, 140, 40), (150, 90, 220), (40, 40, 50)]
SKINS = [(255, 220, 190), (230, 185, 150), (190, 140, 100), (140, 95, 65), (95, 65, 45)]
HAIRS = [(40, 30, 20), (90, 60, 30), (220, 190, 90), (20, 20, 20), (160, 60, 30), (200, 200, 200)]
GLOWS = [(80, 255, 120), (255, 80, 200), (80, 200, 255)]


def make_crowd(seed, n):
    r = random.Random(seed)
    out = []
    for _ in range(n):
        if r.random() < 0.7:
            x, y = r.uniform(150, 300), r.uniform(106, 176)
        else:
            x, y = r.uniform(5, WW - 5), r.uniform(114, 176)
        out.append(dict(x=x, y=y, shirt=r.choice(SHIRTS), skin=r.choice(SKINS), hair=r.choice(HAIRS),
                        ph=r.random() * 6.28, phone=r.random() < 0.12,
                        glow=r.choice(GLOWS) if r.random() < 0.15 else None, hp=r.choice(GLOWS)))
    return out


CROWD = make_crowd(3, 230)


# ------------------------------------------------------------ Mr. Waternoose
EYES = [(-5.5, -45.0, 1.9), (0.0, -46.5, 2.1), (5.5, -45.0, 1.9), (-2.9, -41.0, 1.5), (2.9, -41.0, 1.5)]


def draw_wn(d, x, y, s, style="color", eyes=1.0, smile=0.0, dim=1.0, pupils=(0.0, 0.0),
            headphones=False, pupil_size=0.45):
    """Hunched, crab-legged, five-eyed CEO in a suit. (x, y) = feet centre."""
    def P(px, py):
        return (x + px * s, y + py * s)

    def C(c):
        return tuple(int(v * dim) for v in c)

    if style == "shadow":
        skin = skin_dk = suit = shirt = tie = hair = leg = mouth = (4, 3, 8)
    else:
        skin, skin_dk = C((128, 108, 148)), C((96, 80, 114))
        suit, shirt, tie = C((48, 44, 62)), C((225, 225, 230)), C((140, 28, 40))
        hair, leg, mouth = C((236, 236, 242)), C((96, 80, 114)), C((40, 18, 36))
    lw = max(1, int(round(s * 1.3)))
    for side in (-1, 1):
        for hx, kx, ky, fx in ((4, 14, -27, 18), (7, 21, -23, 25), (10, 26, -18, 30)):
            d.line([P(side * hx, -15), P(side * kx, ky), P(side * fx, 0)], fill=leg, width=lw, joint="curve")
    d.ellipse([*P(-12, -21), *P(12, -9)], fill=skin_dk)
    d.polygon([P(-11, -15), P(11, -15), P(9, -35), P(-9, -35)], fill=suit)
    d.polygon([P(-3.5, -35), P(3.5, -35), P(0, -24)], fill=shirt)
    d.polygon([P(-1, -33), P(1, -33), P(1.6, -26), P(0, -24), P(-1.6, -26)], fill=tie)
    for side in (-1, 1):
        d.line([P(side * 9, -33), P(side * 13, -24), P(side * 11, -16)], fill=suit,
               width=max(1, int(round(s * 2.2))), joint="curve")
        d.ellipse([*P(side * 11 - 1.8, -17.8), *P(side * 11 + 1.8, -14.2)], fill=skin)
    # head
    d.ellipse([*P(-12, -51), *P(12, -32)], fill=skin)
    if s > 3 and style != "shadow":   # close-up shading + wrinkles
        d.chord([*P(-12, -51), *P(12, -32)], 20, 160, fill=skin_dk)
        d.ellipse([*P(-11, -49), *P(11, -35)], fill=skin)
        for k in range(3):
            d.arc([*P(-6 + k, -52 + k * 0.8), *P(6 - k, -48 + k * 0.8)], 200, 340, fill=skin_dk,
                  width=max(1, int(s * 0.3)))
    d.ellipse([*P(-14.5, -46), *P(-9, -38)], fill=hair)
    d.ellipse([*P(9, -46), *P(14.5, -38)], fill=hair)
    d.ellipse([*P(-4, -53), *P(4, -49)], fill=hair)
    mw = 6 + smile * 2.5
    d.arc([*P(-mw, -40 - smile * 1.5), *P(mw, -34.5 + smile * 1.5)], 15, 165, fill=mouth,
          width=max(1, int(round(s * 0.7))))
    if headphones:
        hc = (80, 255, 200)
        d.arc([*P(-12, -55), *P(12, -40)], 180, 360, fill=(30, 30, 40), width=max(1, int(s)))
        d.rectangle([*P(-13.5, -45), *P(-11, -40)], fill=hc)
        d.rectangle([*P(11, -45), *P(13.5, -40)], fill=hc)
    ev = eyes if isinstance(eyes, (list, tuple)) else [eyes] * 5
    for (ex, ey, er), o in zip(EYES, ev):
        cx, cy = P(ex, ey)
        glow = style == "shadow"
        col = (255, 225, 80) if glow else (248, 242, 215)
        if o <= 0.03:
            if s > 3 and not glow:
                d.line([P(ex - er, ey), P(ex + er, ey)], fill=mouth, width=max(1, int(s * 0.4)))
            continue
        if s < 0.8:
            d.point((round(cx), round(cy)), fill=col)
            continue
        rx, ry = er * s, max(0.5, er * s * o)
        d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=col)
        if not glow:
            pr = max(0.6, rx * pupil_size)
            px, py = cx + pupils[0] * rx * 0.45, cy + pupils[1] * ry * 0.45
            if pr < 1.2:
                d.point((round(px), round(py)), fill=(10, 8, 12))
            else:
                d.ellipse([px - pr, py - min(pr, ry), px + pr, py + min(pr, ry)], fill=(10, 8, 12))


# ------------------------------------------------------------ world drawing
def draw_person(d, p, t, mode, bob, headphones=False):
    x, y = int(p["x"]), int(p["y"])
    arms = False
    if bob > 0:
        v = abs(math.sin(math.pi * t / BEAT + p["ph"]))
        y -= int(round(v * 2 * bob))
        arms = v > 0.75 and p["ph"] > 3
    dark = MODES[mode]["dark"]
    if dark:
        sil = (10, 8, 16) if mode == "night" else (26, 10, 40)
        body = head = hair = legs = sil
    else:
        body, head, hair, legs = p["shirt"], p["skin"], p["hair"], (50, 50, 70)
    d.rectangle([x - 1, y - 9, x + 1, y - 7], fill=head)
    d.line([x - 1, y - 9, x + 1, y - 9], fill=hair)
    d.rectangle([x - 2, y - 6, x + 2, y - 2], fill=body)
    d.point([(x - 1, y - 1), (x + 1, y - 1), (x - 1, y), (x + 1, y)], fill=legs)
    if arms:
        d.point([(x - 3, y - 7), (x - 3, y - 8), (x + 3, y - 7), (x + 3, y - 8)], fill=head)
    if headphones:
        d.point([(x - 2, y - 8), (x + 2, y - 8)], fill=p["hp"])
        d.line([x - 1, y - 10, x + 1, y - 10], fill=(40, 40, 50))
    if dark and p["phone"]:
        d.point((x + 2, y - 7), fill=(220, 230, 255))
    if dark and p["glow"] and not headphones:
        d.line([x + 3, y - 9, x + 3, y - 11], fill=p["glow"])


def draw_bg(d, t, mode):
    m = MODES[mode]
    top, bot = m["sky"]
    for y in range(0, 90):
        d.line([0, y, WW, y], fill=rgb_lerp(top, bot, min(1, y / 80)))
    if mode == "day":
        d.ellipse([30, 8, 50, 28], fill=(255, 240, 150))
        for cx, cy, cw in CLOUDS:
            x = (cx + t * 3) % (WW + 40) - 20
            d.ellipse([x, cy, x + cw, cy + 7], fill=(255, 255, 255))
            d.ellipse([x + cw * 0.3, cy - 4, x + cw * 0.8, cy + 5], fill=(255, 255, 255))
    if mode in ("night", "neon"):
        for sx, sy, ph in STARS:
            if math.sin(t * 2 + ph) > -0.3:
                d.point((sx, sy), fill=(200, 200, 230))
        if mode == "night":
            d.ellipse([52, 12, 64, 24], fill=(220, 220, 200))
            d.ellipse([56, 10, 68, 22], fill=top)
    if mode == "sunset":
        d.ellipse([280, 52, 320, 92], fill=(255, 200, 110))
    pts = [(0, 90)] + [(x, 66 + 6 * math.sin(x * 0.02 + 1) + 4 * math.sin(x * 0.051))
                       for x in range(0, WW + 1, 4)] + [(WW, 90)]
    d.polygon(pts, fill=m["hill"])


def draw_trees(d, mode):
    col = MODES[mode]["tree"]
    for x, y, r in TREES:
        d.ellipse([x - r, y - r, x + r, y + r + 6], fill=col)


def draw_ground(d, mode):
    m = MODES[mode]
    d.rectangle([0, 86, WW, H], fill=m["grass"])
    for i in range(0, WW, 16):
        d.rectangle([i, 86, i + 7, H], fill=m["grass2"])
    if mode == "overcast":
        for mx, my, mr in MUD:
            d.ellipse([mx - mr, my - mr // 3, mx + mr, my + mr // 3], fill=(92, 70, 45))


def draw_stage(d, t, mode, screen="bars", band_bob=1.0):
    dark = MODES[mode]["dark"]
    truss = (150, 150, 160) if not dark else (40, 40, 50)
    d.rectangle([166, 36, 274, 43], fill=truss)
    for x0 in (168, 264):
        d.rectangle([x0, 36, x0 + 7, 100], outline=truss)
        for yy in range(36, 100, 7):
            d.line([x0, yy, x0 + 7, yy + 7], fill=truss)
            d.line([x0 + 7, yy, x0, yy + 7], fill=truss)
    d.rectangle([176, 44, 263, 92], fill=(18, 16, 24))
    sx0, sy0, sx1, sy1 = 188, 52, 251, 80
    if screen == "bars":
        for i in range(8):
            h = int((math.sin(t * 6 + i * 1.3) * 0.5 + 0.5) * (sy1 - sy0 - 4)) + 2
            col = [(255, 80, 120), (255, 200, 60), (80, 220, 255), (160, 100, 255)][i % 4]
            if dark:
                col = tuple(c // 2 for c in col)
            bx = sx0 + 3 + i * 8
            d.rectangle([bx, sy1 - h, bx + 5, sy1 - 1], fill=col)
    elif screen == "eyes":
        for ox, oy in ((-6, -2), (0, -3), (6, -2), (-3, 2), (3, 2)):
            d.point((220 + ox, 66 + oy), fill=(150, 120, 40))
    d.rectangle([sx0, sy0, sx1, sy1], outline=(60, 60, 70))
    d.rectangle([164, 92, 276, 101], fill=(55, 52, 62))
    for x0 in (152, 277):
        d.rectangle([x0, 66, x0 + 10, 101], fill=(25, 25, 30))
        for yy in (70, 80, 90):
            d.ellipse([x0 + 2, yy, x0 + 8, yy + 6], fill=(60, 60, 70))
    for i, bx in enumerate((200, 220, 240)):
        p = dict(x=bx, y=92, shirt=SHIRTS[i + 1], skin=SKINS[i], hair=HAIRS[i], ph=i * 1.1,
                 phone=False, glow=None, hp=GLOWS[0])
        draw_person(d, p, t, "day" if not dark else mode, band_bob)


def ferris_points(t):
    cx, cy, r = 365, 50, 30
    ang = t * 0.35
    return [(cx + r * math.cos(ang + k * math.pi / 4), cy + r * math.sin(ang + k * math.pi / 4))
            for k in range(8)]


def draw_ferris(d, t, mode, wn_gondola=None):
    cx, cy, r = 365, 50, 30
    dark = MODES[mode]["dark"]
    col = (235, 235, 240) if not dark else (45, 45, 60)
    d.line([cx, cy, cx - 18, 100], fill=col, width=2)
    d.line([cx, cy, cx + 18, 100], fill=col, width=2)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=col)
    pts = ferris_points(t)
    for px, py in pts:
        d.line([cx, cy, px, py], fill=col)
    gcols = [(230, 70, 80), (250, 200, 60), (70, 160, 230), (120, 210, 120)]
    for k, (px, py) in enumerate(pts):
        if k == wn_gondola:
            draw_wn(d, px, py + 6, 0.36, eyes=1.0)
        gc = gcols[k % 4] if not dark else (30, 30, 45)
        d.line([px, py, px, py + 2], fill=col)
        d.rectangle([px - 4, py + 2, px + 4, py + 7], fill=gc)


def draw_tent(d, x, y, w, h, c1, c2, dark):
    if dark:
        c1, c2 = (24, 20, 30), (18, 15, 24)
    for i in range(0, w, 3):
        d.rectangle([x + i, y - h // 2, min(x + i + 2, x + w - 1), y], fill=c1 if (i // 3) % 2 == 0 else c2)
    d.polygon([(x - 2, y - h // 2), (x + w // 2, y - h), (x + w + 1, y - h // 2)], fill=c1)
    d.rectangle([x + w // 2 - 2, y - 6, x + w // 2 + 2, y], fill=(20, 15, 15))
    d.line([x + w // 2, y - h, x + w // 2, y - h - 5], fill=(80, 80, 80))
    d.rectangle([x + w // 2 + 1, y - h - 5, x + w // 2 + 4, y - h - 3], fill=c2)


def draw_truck(d, x, y, dark, flash=False):
    body = (250, 220, 80) if not dark else (35, 32, 26)
    d.rectangle([x, y - 14, x + 30, y - 3], fill=body)
    d.rectangle([x + 4, y - 12, x + 18, y - 7], fill=(40, 40, 50) if not dark else (110, 90, 40))
    d.rectangle([x + 3, y - 17, x + 20, y - 14], fill=(230, 60, 70) if not dark else (40, 20, 20))
    d.ellipse([x + 3, y - 5, x + 9, y + 1], fill=(30, 30, 30))
    d.ellipse([x + 21, y - 5, x + 27, y + 1], fill=(30, 30, 30))
    if flash:
        d.rectangle([x - 2, y - 19, x + 32, y + 2], outline=(255, 255, 255))


LOO_X = [298, 308, 318, 328, 338]


def draw_loo(d, x, y, dark, open_door=False, eyes=1.0):
    c = (40, 110, 210) if not dark else (14, 26, 50)
    edge = (25, 80, 160) if not dark else (8, 16, 32)
    d.rectangle([x, y - 16, x + 8, y], fill=c)
    d.rectangle([x - 1, y - 18, x + 9, y - 16], fill=(225, 230, 240) if not dark else (30, 36, 50))
    if open_door:
        d.rectangle([x + 1, y - 15, x + 7, y], fill=(0, 0, 0))
        if eyes > 0:
            for ex, ey in ((2, -11), (4, -12), (6, -11), (3, -9), (5, -9)):
                d.point((x + ex, y + ey), fill=(255, 225, 80))
        d.polygon([(x + 7, y - 15), (x + 11, y - 17), (x + 11, y + 1), (x + 7, y)], fill=c)
    else:
        d.rectangle([x + 1, y - 15, x + 7, y], outline=edge)
        d.point((x + 6, y - 8), fill=(200, 200, 210))
        d.point((x + 4, y - 13), fill=edge)


def render_world(t, mode, cam, bob=1.0, wn=None, screen="bars", loo_open=None, loo_eyes=1.0,
                 gondola=None, headphones=False, beams=False, truck=True, extra_loo=False,
                 truck_flash=False, loo_flash=False):
    img = Image.new("RGB", (WW, H))
    d = ImageDraw.Draw(img, "RGBA")
    dark = MODES[mode]["dark"]
    draw_bg(d, t, mode)
    draw_trees(d, mode)
    if wn and wn["where"] == "tree":
        draw_wn(d, wn["x"], wn["y"], wn["s"], style=wn.get("style", "color"), eyes=wn.get("eyes", 1.0),
                dim=wn.get("dim", 1.0))
    draw_ground(d, mode)
    draw_tent(d, 18, 92, 26, 22, (230, 70, 80), (250, 240, 240), dark)
    draw_tent(d, 52, 94, 30, 24, (70, 160, 230), (250, 240, 240), dark)
    draw_tent(d, 90, 92, 24, 20, (250, 200, 60), (250, 240, 240), dark)
    draw_ferris(d, t, mode, wn_gondola=gondola)
    draw_stage(d, t, mode, screen=screen, band_bob=bob)
    if truck:
        draw_truck(d, 118, 102, dark, flash=truck_flash)
    if wn and wn["where"] == "loos":
        draw_wn(d, wn["x"], wn["y"], wn["s"], style=wn.get("style", "shadow"), eyes=wn.get("eyes", 1.0))
    for i, lx in enumerate(LOO_X):
        draw_loo(d, lx, 114, dark, open_door=(i == loo_open), eyes=loo_eyes)
    if extra_loo:
        draw_loo(d, 287, 114, dark)
        if loo_flash:
            d.rectangle([285, 94, 297, 116], outline=(255, 255, 255))
    items = [(p["y"], 0, p) for p in CROWD]
    if wn and wn["where"] == "crowd":
        items.append((wn["y"], 1, None))
    items.sort(key=lambda it: (it[0], it[1]))
    for _, kind, p in items:
        if kind == 0:
            draw_person(d, p, t, mode, bob, headphones)
        else:
            draw_wn(d, wn["x"], wn["y"], wn["s"], style=wn.get("style", "color"), eyes=wn.get("eyes", 1.0),
                    dim=wn.get("dim", 1.0), headphones=wn.get("headphones", False))
    if beams:
        cols = [(150, 60, 220, 38), (220, 40, 80, 30), (150, 60, 220, 38)]
        for i, bx in enumerate((182, 220, 258)):
            gx = bx + 70 * math.sin(t * 0.6 + i * 2.1)
            d.polygon([(bx - 1, 44), (bx + 1, 44), (gx + 14, 178), (gx - 14, 178)], fill=cols[i])
    if mode == "overcast":
        rr = random.Random(int(t * 24))
        for _ in range(120):
            rx, ry = rr.randrange(WW), rr.randrange(H)
            d.line([rx, ry, rx - 2, ry + 5], fill=(200, 205, 220, 120))
    cx, cy, cw = cam
    ch = cw * 9 / 16
    x0 = clamp(cx - cw / 2, 0, WW - cw)
    y0 = clamp(cy - ch / 2, 0, H - ch)
    return img.resize((OW, OH), Image.NEAREST, box=(x0, y0, x0 + cw, y0 + ch)), (x0, y0, cw)


def w2s(camb, wx, wy):
    x0, y0, cw = camb
    k = OW / cw
    return (wx - x0) * k, (wy - y0) * k


# --------------------------------------------------------------------- UI
def text_img(text, fnt, fill, stroke_w=0, stroke_fill=None):
    bb = fnt.getbbox(text, stroke_width=stroke_w)
    im = Image.new("RGBA", (bb[2] - bb[0] + 4, bb[3] - bb[1] + 4), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((2 - bb[0], 2 - bb[1]), text, font=fnt, fill=fill,
                            stroke_width=stroke_w, stroke_fill=stroke_fill)
    return im


def paste_center(base, im, cx, cy, scale=1.0, alpha=1.0):
    if scale != 1.0:
        im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.BILINEAR)
    if alpha < 1.0:
        im = im.copy()
        im.putalpha(im.getchannel("A").point(lambda v: int(v * alpha)))
    base.paste(im, (int(cx - im.width / 2), int(cy - im.height / 2)), im)


def ui_topbar(img, cash, guests, mood, day, paused=False):
    d = ImageDraw.Draw(img, "RGBA")
    d.rounded_rectangle([16, 12, OW - 16, 66], radius=14, fill=(20, 18, 40, 205),
                        outline=(255, 255, 255, 90), width=2)
    items = [("CASH", f"£{cash:,}", (255, 210, 80)), ("GUESTS", f"{guests:,}", (120, 220, 255)),
             ("MOOD", f"{mood}% :)" if mood > 50 else f"{mood}% :(", (140, 240, 140)),
             ("DAY", str(day), (255, 160, 220))]
    cw = (OW - 64) / 4
    for i, (lab, val, col) in enumerate(items):
        x = 40 + i * cw
        d.text((x, 28), lab, font=font("consolab.ttf", 18), fill=(*col, 200))
        d.text((x + 16 + len(lab) * 10, 21), val, font=font("consolab.ttf", 30), fill=(255, 255, 255, 240))
    if paused:
        d.rounded_rectangle([OW / 2 - 110, 84, OW / 2 + 110, 136], radius=10, fill=(0, 0, 0, 170))
        d.rectangle([OW / 2 - 90, 96, OW / 2 - 82, 124], fill=(255, 255, 255))
        d.rectangle([OW / 2 - 76, 96, OW / 2 - 68, 124], fill=(255, 255, 255))
        d.text((OW / 2 - 56, 94), "PAUSED", font=font("consolab.ttf", 32), fill=(255, 255, 255))


def ui_toast(img, text, age, dur=2.0, color=(255, 200, 60), jitter=0, rng=None):
    if age < 0 or age > dur:
        return
    k = min(ease(age / 0.22), ease((dur - age) / 0.22))
    f = font("consolab.ttf", 26)
    if jitter and rng is not None:
        chars = list(text)
        for i in range(len(chars)):
            if chars[i] != " " and rng.random() < jitter:
                chars[i] = rng.choice(list("#%&@?!/█▓░"))
        text = "".join(chars)
    d = ImageDraw.Draw(img, "RGBA")
    w = d.textlength(text, font=f) + 96
    h = 60
    x = -w + (w + 24) * k
    y = OH - h - 28
    d.rounded_rectangle([x, y, x + w, y + h], radius=12, fill=(15, 14, 32, 225), outline=(*color, 255), width=3)
    d.ellipse([x + 14, y + 12, x + 50, y + 48], fill=color)
    d.text((x + 26, y + 13), "!", font=font("consolab.ttf", 30), fill=(15, 14, 32))
    ox = rng.integers(-3, 4) if (jitter and rng is not None) else 0
    d.text((x + 66 + ox, y + 16), text, font=f, fill=(255, 255, 255))


def ui_bigword(img, text, age, dur, size=150, color=(255, 255, 255), y=OH * 0.42):
    if age < 0 or age > dur:
        return
    sc = 1.0 + 0.6 * math.exp(-age * 18) * math.cos(age * 30)
    alpha = clamp((dur - age) / 0.15)
    im = text_img(text, font("impact.ttf", size), color, stroke_w=8, stroke_fill=(30, 12, 50))
    paste_center(img, im, OW / 2, y, scale=max(0.3, sc), alpha=alpha)


def ui_pill(img, text, alpha, y, size=34):
    if alpha <= 0:
        return
    d = ImageDraw.Draw(img, "RGBA")
    f = font("consolab.ttf", size)
    w = d.textlength(text, font=f)
    d.rounded_rectangle([OW / 2 - w / 2 - 24, y - 10, OW / 2 + w / 2 + 24, y + size + 14], radius=24,
                        fill=(20, 18, 40, int(200 * alpha)))
    d.text((OW / 2 - w / 2, y), text, font=f, fill=(255, 255, 255, int(255 * alpha)))


def ui_eerie(img, text, alpha, y=OH * 0.78, size=46):
    if alpha <= 0:
        return
    im = text_img(text, font("georgiai.ttf", size), (232, 224, 255, 255), stroke_w=3, stroke_fill=(0, 0, 0, 200))
    paste_center(img, im, OW / 2, y, alpha=alpha)


def ui_cursor(img, x, y, click_age=None):
    d = ImageDraw.Draw(img, "RGBA")
    if click_age is not None and 0 <= click_age < 0.35:
        r = 10 + click_age * 140
        d.ellipse([x - r, y - r, x + r, y + r], outline=(255, 255, 255, int(255 * (1 - click_age / 0.35))), width=4)
    pts = [(0, 0), (0, 34), (9, 26), (15, 40), (21, 37), (15, 24), (26, 24)]
    d.polygon([(x + px, y + py) for px, py in pts], fill=(255, 255, 255), outline=(0, 0, 0), width=3)


def ui_float(img, text, age, x, y, color):
    if age < 0 or age > 1.0:
        return
    im = text_img(text, font("consolab.ttf", 34), color, stroke_w=3, stroke_fill=(0, 0, 0))
    paste_center(img, im, x, y - age * 70, alpha=clamp((1 - age) / 0.3))


def ui_cctv(img, label, t):
    d = ImageDraw.Draw(img, "RGBA")
    f = font("consolab.ttf", 28)
    d.text((44, 34), label, font=f, fill=(255, 255, 255, 235), stroke_width=2, stroke_fill=(0, 0, 0, 200))
    if int(t * 2.5) % 2 == 0:
        d.ellipse([OW - 150, 40, OW - 128, 62], fill=(230, 30, 30))
    d.text((OW - 118, 34), "REC", font=f, fill=(255, 255, 255, 235), stroke_width=2, stroke_fill=(0, 0, 0, 200))
    d.text((OW - 214, 74), f"03:14:{int((t - T_S5) * 9) % 60:02d} AM", font=font("consolab.ttf", 22),
           fill=(255, 255, 255, 200), stroke_width=2, stroke_fill=(0, 0, 0, 200))
    L, c = 50, (255, 255, 255, 170)
    for (cx, cy, sx, sy) in ((24, 24, 1, 1), (OW - 24, 24, -1, 1), (24, OH - 24, 1, -1), (OW - 24, OH - 24, -1, -1)):
        d.line([cx, cy, cx + L * sx, cy], fill=c, width=4)
        d.line([cx, cy, cx, cy + L * sy], fill=c, width=4)


def star(d, cx, cy, r, fill):
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    d.polygon(pts, fill=fill)


# ----------------------------------------------------------------- scenes
def fx_default():
    return dict(grain=0.02, vig=0.25, desat=0.0, chroma=0, scan=0.0, bloom=0.0, bright=1.0, glitch=0, light=None, after=None)


WN_TREE = dict(where="tree", x=120, y=92, s=0.55, style="color", dim=0.65)


def scene1(t, fx, rng):
    img, _ = render_world(t, "day", (160 + ease(t / T_S2) * 50, 90, 320), bob=1.0, wn=WN_TREE)
    ui_topbar(img, int(12000 + t * 140), int(800 + t * 95), 92, 3)
    for w, st, c in (("BUILD.", BEAT, (255, 220, 80)), ("BOOK.", 3 * BEAT, (120, 220, 255)),
                     ("BOOGIE.", 5 * BEAT, (255, 120, 200))):
        ui_bigword(img, w, t - st, 2 * BEAT - 0.04, color=c)
    ui_pill(img, "The music festival management sim", clamp((t - 7 * BEAT) / 0.2), OH * 0.4)
    return img


def cam_s2(t):
    lt = t - T_S2
    if t < 7.3:
        return (lerp(210, 200, ease(lt / 2.8)), 95, lerp(320, 300, ease(lt / 1.0)))
    k = ease((t - 7.3) / 1.2)
    if t < T_S3:
        return (lerp(200, 120, k), lerp(95, 76, k), lerp(300, 140, k))
    k2 = clamp((t - T_S3) / 1.35) ** 1.6
    return (120, 76, lerp(140, 70, k2))


def scene2(t, fx, rng):
    lt = t - T_S2
    cam = cam_s2(t)
    wn = dict(WN_TREE)
    img, camb = render_world(t, "day", cam, bob=1.0, wn=wn, truck=lt >= 0.55, truck_flash=0.55 <= lt < 0.7,
                             extra_loo=lt >= 1.75, loo_flash=1.75 <= lt < 1.9)
    cash = 14000 - (2000 if lt >= 0.55 else 0) - (400 if lt >= 1.75 else 0) + int(lt * 300)
    guests = int(1230 + lt * 260)
    ui_topbar(img, cash, guests, 94, 3)
    ui_bigword(img, "BOOK HEADLINERS", lt - 0.05, 1.3, size=96, color=(255, 220, 80), y=OH * 0.3)
    ui_bigword(img, "SELL £9 CIDER", lt - 1.45, 1.3, size=96, color=(120, 255, 170), y=OH * 0.3)
    tx, ty = w2s(camb, 133, 92)
    lx, ly = w2s(camb, 291, 106)
    if lt < 0.55:
        k = ease(lt / 0.5)
        ui_cursor(img, lerp(900, tx, k), lerp(620, ty, k))
    elif lt < 1.75:
        k = ease((lt - 1.2) / 0.5)
        ui_cursor(img, lerp(tx, lx, k), lerp(ty, ly, k), click_age=lt - 0.55)
    elif lt < 2.6:
        ui_cursor(img, lx, ly, click_age=lt - 1.75)
    ui_float(img, "-£2,000", lt - 0.55, tx, ty - 60, (255, 90, 90))
    ui_float(img, "-£400", lt - 1.75, lx, ly - 60, (255, 90, 90))
    ui_toast(img, "Taco truck built! Guests are thrilled.", lt - 0.6, 1.1)
    ui_toast(img, "Porta-loo placed. It is already occupied.", lt - 1.8, 1.0)
    ui_toast(img, "A new guest has arrived.", t - 7.3, 2.6, color=(200, 160, 255))
    if t > 7.3:
        fx["desat"] = 0.25 * ease((t - 7.3) / 1.2)
        fx["vig"] = 0.25 + 0.2 * ease((t - 7.3) / 1.2)
    return img


def scene3(t, fx, rng):
    lt = t - T_S3
    if lt > 1.35:
        return Image.new("RGB", (OW, OH))
    wn = dict(WN_TREE)
    wn["eyes"] = 0.0 if 0.7 < lt < 0.82 else 1.0
    img, _ = render_world(T_S3, "day", cam_s2(t), bob=0.0, wn=wn)
    ui_topbar(img, 14750, 2270 + (1 if lt > 0.5 else 0), 94 - int(lt * 40), 3, paused=True)
    ui_toast(img, "A new guest has arrived.", 1.0, 2.6, color=(200, 160, 255), jitter=clamp(lt / 1.2) * 0.4, rng=rng)
    k = ease(lt / 1.3)
    fx.update(desat=0.25 + 0.6 * k, chroma=int(1 + 7 * k), grain=0.02 + 0.07 * k, vig=0.45 + 0.35 * k,
              glitch=int(k * 6) if rng.random() < 0.5 else 0, scan=0.1 * k)
    return img


def scene4(t, fx, rng):
    lt = t - T_S4
    flick = 2.0 <= lt < 2.18
    if lt < 2.0:
        wn = dict(where="loos", x=333, y=112, s=0.8, style="shadow",
                  eyes=0.0 if 1.2 < lt < 1.3 else 1.0)
    else:
        wn = dict(where="crowd", x=292, y=160, s=1.05, style="shadow",
                  eyes=0.0 if 3.55 < lt < 3.68 else 1.0)
    cam = (lerp(230, 250, ease(lt / 4)), 110, lerp(320, 270, ease(lt / 4)))
    img, _ = render_world(t, "night", cam, bob=0.0, wn=wn, screen="eyes" if lt > 1.0 else "bars", beams=True)
    ui_eerie(img, "Every festival needs a crowd.", clamp(lt / 0.4) * clamp((1.9 - lt) / 0.3))
    ui_eerie(img, "Some guests never go home.", clamp((lt - 2.3) / 0.4) * clamp((3.95 - lt) / 0.3))
    fx.update(grain=0.06, vig=0.6, desat=0.25, bloom=0.9, scan=0.08, chroma=1,
              bright=(0.08 if flick else (0.85 + 0.15 * math.sin(t * 37) * (rng.random() < 0.15))))
    if lt < 0.15:
        fx["bright"] *= lt / 0.15
    return img


def scene_stats(lt, rng):
    img = Image.new("RGB", (OW, OH), (14, 10, 26))
    d = ImageDraw.Draw(img, "RGBA")
    for gx in range(0, OW, 40):
        d.line([gx, 0, gx, OH], fill=(40, 30, 70, 60))
    for gy in range(0, OH, 40):
        d.line([0, gy, OW, gy], fill=(40, 30, 70, 60))
    sh = int(rng.integers(-4, 5)) if lt > 0.7 else 0
    d.rounded_rectangle([170 + sh, 60, 1110 + sh, 600], radius=18, fill=(26, 22, 48, 245),
                        outline=(120, 110, 200), width=3)
    d.text((210 + sh, 88), "END OF DAY REPORT  ·  DAY 13", font=font("consolab.ttf", 40), fill=(255, 210, 80))
    rows = [("GUESTS", "12,044 (+1)"), ("HAPPINESS", "3%"), ("CIDER SOLD", "9,120 pints"),
            ("SHOES LOST", "41"), ("SCREAM ENERGY", "")]
    f = font("consolab.ttf", 32)
    for i, (k, v) in enumerate(rows):
        y = 170 + i * 72
        d.text((210 + sh, y), k, font=f, fill=(200, 195, 230))
        d.text((560 + sh, y), v, font=f, fill=(255, 255, 255))
    d.rounded_rectangle([760 + sh, 244, 1070 + sh, 270], radius=6, outline=(120, 110, 200), width=2)
    d.rectangle([764 + sh, 248, 774 + sh, 266], fill=(230, 60, 60))
    p = clamp(lt / 0.6)
    y = 170 + 4 * 72
    d.rounded_rectangle([560 + sh, y, 1070 + sh, y + 36], radius=8, outline=(255, 90, 90), width=3)
    flash = p >= 1 and int(lt * 10) % 2 == 0
    d.rectangle([566 + sh, y + 6, 566 + sh + (498 * p), y + 30], fill=(255, 255, 255) if flash else (230, 40, 60))
    if p >= 1:
        d.text((560 + sh, y + 50), "!! RECORD HIGH !!", font=font("consolab.ttf", 38),
               fill=(255, 60, 60) if int(lt * 8) % 2 else (255, 230, 230))
    return img


CUTS = [
    dict(label="CAM 01 · MUDSTOCK '26", toast="Mr. Waternoose bought a VIP wristband."),
    dict(label="CAM 02 · SILENT DISCO", toast="Mr. Waternoose is enjoying the silent disco. Silently."),
    dict(label="CAM 03 · BIG WHEEL", toast="Ride capacity exceeded: 1 guest, 6 legs."),
    dict(label="CAM 04 · TOILET BLOCK C", toast="Porta-loo #3 has been occupied for 9 days."),
    dict(label="", toast="Staff member Gary has quit. Reason: \"the legs\"."),
]


def scene5(t, fx, rng):
    k = min(4, int((t - T_S5) / CUT))
    lt = (t - T_S5) - k * CUT
    push = ease(lt / CUT)
    if k == 0:
        wn = dict(where="crowd", x=232, y=150, s=0.9, style="color", eyes=1.0)
        img, _ = render_world(t, "overcast", (232, 128, lerp(175, 150, push)), bob=0.8, wn=wn)
    elif k == 1:
        wn = dict(where="crowd", x=212, y=148, s=0.9, style="color", eyes=1.0, headphones=True)
        img, _ = render_world(t, "neon", (212, 126, lerp(175, 150, push)), bob=1.0, wn=wn, headphones=True,
                              screen="none", beams=True)
    elif k == 2:
        gx, gy = ferris_points(t)[5]
        img, _ = render_world(t, "sunset", (gx, gy + 2, lerp(110, 90, push)), bob=0.6, gondola=5)
    elif k == 3:
        img, _ = render_world(t, "night", (322, 104, lerp(80, 64, push)), bob=0.0, loo_open=2,
                              loo_eyes=0.0 if 0.55 < lt < 0.66 else 1.0)
    else:
        img = scene_stats(lt, rng)
    if CUTS[k]["label"]:
        ui_cctv(img, CUTS[k]["label"], t)
    ui_toast(img, CUTS[k]["toast"], lt - 0.08, CUT - 0.02, color=(255, 90, 90) if k == 4 else (255, 200, 60))
    fx.update(grain=0.07, scan=0.12, vig=0.5, desat=0.2, chroma=2, bloom=0.6 if k == 3 else 0.2)
    if lt < 2 / FPS:
        fx.update(bright=2.2, glitch=8, chroma=10)
    return img


def scene6(t, fx, rng):
    lt = t - T_S6
    if lt > 4.35:
        return Image.new("RGB", (OW, OH))
    c = Image.new("RGB", (W, H), (6, 4, 12))
    d = ImageDraw.Draw(c, "RGBA")
    for i, (bx, by, col) in enumerate(((40, 40, (150, 60, 220)), (280, 30, (220, 40, 80)),
                                       (60, 150, (60, 120, 220)), (270, 140, (150, 60, 220)))):
        r = 10 + 3 * math.sin(t * 2 + i)
        d.ellipse([bx - r, by - r, bx + r, by + r], fill=(*col, 40))
    opens = [0.9, 1.35, 1.7, 1.95, 2.1]
    order = [1, 0, 2, 3, 4]
    eyes = [0.0] * 5
    for oi, st in zip(order, opens):
        eyes[oi] = ease((lt - st) / 0.12)
    snap = 2.6
    pupils = (-0.9, 0.35) if lt < snap else (0.0, 0.0)
    smile = ease((lt - 2.9) / 0.9)
    draw_wn(d, 160, 432, 8, style="color", eyes=eyes, pupils=pupils, smile=smile,
            pupil_size=0.45 if lt < snap else 0.28)
    cw = lerp(320, 262, ease(lt / 4.3))
    sh = (rng.normal(0, 1.2) if lt > snap else 0.0)
    ch = cw * 9 / 16
    x0 = clamp(160 + sh - cw / 2, 0, W - cw)
    y0 = clamp(104 + sh - ch / 2, 0, H - ch)
    img = c.resize((OW, OH), Image.NEAREST, box=(x0, y0, x0 + cw, y0 + ch))
    def review(img):
        if lt <= 2.9:
            return
        a = ease((lt - 2.9) / 0.25)
        dd = ImageDraw.Draw(img, "RGBA")
        y = OH - 122 + (1 - a) * 80
        dd.rounded_rectangle([230, y, OW - 230, y + 104], radius=16, fill=(250, 248, 240, int(235 * a)),
                             outline=(40, 30, 60, int(255 * a)), width=3)
        for i in range(5):
            star(dd, 290 + i * 40, y + 30, 15, (255, 190, 30, int(255 * a)))
        dd.text((500, y + 15), "GUEST REVIEW", font=font("consolab.ttf", 26), fill=(90, 80, 110, int(255 * a)))
        dd.text((270, y + 54), "\u201cWonderful screams. See you next year.\u201d  \u2014 H.J.W.",
                font=font("georgiai.ttf", 30), fill=(30, 20, 40, int(255 * a)))
    fx["after"] = review
    light = clamp(0.12 + lt / 2.4) * (0.9 + 0.1 * math.sin(t * 29))
    fx.update(grain=0.06, vig=0.7, bloom=0.5, chroma=2 if lt > snap else 1, scan=0.05,
              light=(light, 380, 220 + lt * 170))
    return img


TITLE_COLS = [(255, 80, 110), (255, 200, 60), (90, 210, 255), (170, 110, 255), (120, 230, 130), (255, 140, 50)]


def scene7(t, fx, rng):
    lt = t - T_S7
    img = Image.new("RGB", (OW, OH))
    d = ImageDraw.Draw(img, "RGBA")
    if lt < 3.75:
        for y in range(0, OH, 4):
            d.rectangle([0, y, OW, y + 4], fill=rgb_lerp((10, 6, 24), (34, 12, 44), y / OH))
        for sx, sy, ph in STARS[:60]:
            if math.sin(t * 2 + ph) > 0:
                d.rectangle([sx * 3, sy * 3, sx * 3 + 2, sy * 3 + 2], fill=(200, 200, 230, 150))
        sway = math.sin(t * 1.3) * 6
        pts = [(x, 70 + 40 * math.sin(math.pi * x / OW) + sway * math.sin(math.pi * x / OW)) for x in range(0, OW + 1, 64)]
        d.line(pts, fill=(200, 200, 210), width=2)
        for i, (x, y) in enumerate(pts[:-1]):
            d.polygon([(x + 6, y), (x + 58, y + 2), (x + 32, y + 40)], fill=TITLE_COLS[i % 6])
        bobbing = lt < 1.85
        drain = ease((lt - 1.85) / 1.0)
        slam = 1.0 + 0.5 * math.exp(-lt * 14)
        f = font("impact.ttf", 170)
        for li, (word, yc) in enumerate((("FESTIVAL", 250), ("TYCOON", 410))):
            widths = [f.getlength(ch) + 6 for ch in word]
            x = OW / 2 - sum(widths) / 2 * slam
            for i, ch in enumerate(word):
                col = TITLE_COLS[(i + li * 3) % 6]
                g = sum(col) // 3
                col = rgb_lerp(col, (g, g, g), drain * 0.7)
                off = -abs(math.sin(math.pi * t / BEAT + i * 0.45)) * 14 if bobbing else drain * (i % 3) * 3
                im = text_img(ch, f, col, stroke_w=9, stroke_fill=(20, 8, 36))
                paste_center(img, im, x + widths[i] * slam / 2, yc + off, scale=slam)
                x += widths[i] * slam
        ui_eerie(img, "He's already got a ticket.", clamp((lt - 1.3) / 0.5), y=548, size=46)
        a = clamp((lt - 2.4) / 0.4)
        if a > 0:
            im = text_img("COMING SOON TO A FIELD NEAR YOU", font("consolab.ttf", 30), (190, 180, 215))
            paste_center(img, im, OW / 2, 630, alpha=a)
        fx["bright"] = 1 - ease((lt - 3.45) / 0.3)
        if lt < 0.08:
            fx["bright"] = 2.5
        if 1.85 < lt < 2.1 or (lt > 2.1 and rng.random() < 0.06):
            fx.update(chroma=6, glitch=4)
        fx.update(grain=0.04, vig=0.4, desat=0.0)
    else:
        if lt > 4.0:
            o = ease((lt - 4.0) / 0.15)
            if 4.6 < lt < 4.72:
                o = 0.0
            draw_wn(d, OW / 2, 360 + 44 * 6, 6, style="shadow", eyes=o)
        fx.update(grain=0.05, vig=0.5, bloom=1.2)
    return img


# ------------------------------------------------------------------ post
YY, XX = np.mgrid[0:OH, 0:OW].astype(np.float32)
VIG = np.clip(((XX - OW / 2) / (OW / 2)) ** 2 * 0.55 + ((YY - OH / 2) / (OH / 2)) ** 2 * 0.55, 0, 1)


def post(img, fx, rng):
    a = np.asarray(img).astype(np.float32) / 255
    if fx["light"] is not None:
        inten, lx, rad = fx["light"]
        dist = np.sqrt((XX - OW / 2) ** 2 + (YY - lx) ** 2)
        m = np.clip(1 - dist / rad, 0, 1) ** 1.5 * inten + 0.03
        a *= np.clip(m, 0, 1)[..., None]
    if fx["bloom"] > 0:
        small = Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8)).resize((320, 180), Image.BILINEAR)
        s = np.asarray(small).astype(np.float32) / 255
        br = np.clip((s.max(axis=2, keepdims=True) - 0.6) / 0.4, 0, 1) * s
        bl = Image.fromarray((br * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(5)).resize((OW, OH), Image.BILINEAR)
        a += np.asarray(bl).astype(np.float32) / 255 * fx["bloom"]
    if fx["desat"] > 0:
        g = a.mean(axis=2, keepdims=True)
        a = a * (1 - fx["desat"]) + g * fx["desat"]
    if fx["chroma"]:
        c = int(fx["chroma"])
        a[:, :, 0] = np.roll(a[:, :, 0], c, axis=1)
        a[:, :, 2] = np.roll(a[:, :, 2], -c, axis=1)
    for _ in range(fx["glitch"]):
        y0 = int(rng.integers(0, OH - 10))
        y1 = y0 + int(rng.integers(4, 40))
        a[y0:y1] = np.roll(a[y0:y1], int(rng.integers(-60, 60)), axis=1)
    a *= fx["bright"]
    if fx["scan"] > 0:
        a[::3] *= 1 - fx["scan"]
    if fx["vig"] > 0:
        a *= (1 - fx["vig"] * VIG)[..., None]
    if fx["grain"] > 0:
        g = rng.normal(0, fx["grain"], (OH // 2, OW // 2, 1)).astype(np.float32)
        a += g.repeat(2, axis=0).repeat(2, axis=1)
    return (np.clip(a, 0, 1) * 255).astype(np.uint8)


def frame(fi):
    t = fi / FPS
    rng = np.random.default_rng(fi)
    fx = fx_default()
    if t < T_S2:
        img = scene1(t, fx, rng)
    elif t < T_S3:
        img = scene2(t, fx, rng)
    elif t < T_S4:
        img = scene3(t, fx, rng)
    elif t < T_S5:
        img = scene4(t, fx, rng)
    elif t < T_S6:
        img = scene5(t, fx, rng)
    elif t < T_S7:
        img = scene6(t, fx, rng)
    else:
        img = scene7(t, fx, rng)
    arr = post(img.convert("RGB"), fx, rng)
    if fx["after"]:
        im = Image.fromarray(arr)
        fx["after"](im)
        arr = np.asarray(im)
    return arr


# ----------------------------------------------------------------- audio
SR = 44100
ARNG = np.random.default_rng(42)
AR = random.Random(5)


def tt(d):
    return np.arange(int(d * SR)) / SR


def noise(d):
    return ARNG.standard_normal(int(d * SR))


def lp(x, f, o=4):
    return sosfilt(butter(o, f, "low", fs=SR, output="sos"), x)


def hp(x, f, o=4):
    return sosfilt(butter(o, f, "high", fs=SR, output="sos"), x)


def bp(x, f1, f2, o=2):
    return sosfilt(butter(o, [f1, f2], "band", fs=SR, output="sos"), x)


def mtof(m):
    return 440 * 2 ** ((m - 69) / 12)


def put(buf, sig, t0, g=1.0):
    i = int(t0 * SR)
    j = min(len(buf), i + len(sig))
    if j > i >= 0:
        buf[i:j] += sig[: j - i] * g


def env(n, a=0.004, r=0.05):
    e = np.ones(n)
    na = max(1, min(n, int(a * SR)))
    e[:na] = np.linspace(0, 1, na)
    nr = max(1, min(n, int(r * SR)))
    e[-nr:] *= np.linspace(1, 0, nr)
    return e


def square(f, d, duty=0.5):
    return np.where((tt(d) * f) % 1 < duty, 1.0, -1.0)


def tri(f, d):
    return 2 * np.abs(2 * ((tt(d) * f) % 1) - 1) - 1


def saw_var(freq):
    ph = np.cumsum(freq) / SR
    return 2 * (ph % 1) - 1


def kick():
    t = tt(0.25)
    return np.sin(2 * np.pi * np.cumsum(45 + 110 * np.exp(-t * 30)) / SR) * np.exp(-t * 12)


def snare():
    t = tt(0.2)
    return bp(noise(0.2), 1000, 7000) * np.exp(-t * 20) + np.sin(2 * np.pi * 185 * t) * np.exp(-t * 30) * 0.4


def hat():
    t = tt(0.06)
    return hp(noise(0.06), 7000) * np.exp(-t * 70)


def boom(d=1.6, f0=95, f1=28):
    t = tt(d)
    s = np.sin(2 * np.pi * np.cumsum(f1 + (f0 - f1) * np.exp(-t * 5)) / SR) * np.exp(-t * 2.2)
    return s + lp(noise(d), 300) * np.exp(-t * 7) * 0.8


def crash(d=2.5):
    t = tt(d)
    return hp(noise(d), 4000) * np.exp(-t * 2.2)


def screech(d=0.8, base=1150):
    t = tt(d)
    s = 0
    for k, r in enumerate((1, 1.059, 1.122, 1.19)):
        s = s + saw_var(base * r * (1 + 0.012 * np.sin(2 * np.pi * (6 + k) * t)))
    return lp(s, 3800) * np.minimum(1, t / 0.015) * np.exp(-t * 3) / 4


def thump():
    t = tt(0.22)
    return np.sin(2 * np.pi * np.cumsum(42 + 35 * np.exp(-t * 20)) / SR) * np.exp(-t * 16)


def squelch(d=0.15):
    t = tt(d)
    tone = np.sin(2 * np.pi * np.cumsum(300 + 1400 * t / d) / SR) * np.exp(-t * 22) * 0.5
    return tone + bp(noise(d), 800, 3000) * np.exp(-t * 30) * 0.7


def creak(d, r0=18, r1=55):
    t = tt(d)
    rate = r0 + (r1 - r0) * (0.5 - 0.5 * np.cos(np.pi * t / d)) + 6 * np.sin(2 * np.pi * 1.3 * t)
    ph = np.cumsum(rate) / SR
    imp = np.diff(np.floor(ph), prepend=0.0)
    s = bp(imp, 500, 1800, 2) + bp(imp, 1300, 1500, 2) * 2
    s /= np.abs(s).max() + 1e-9
    return s * np.minimum(1, t / 0.05) * np.minimum(1, (d - t) / 0.1)


def echo(x, delay=0.3, fb=0.45, taps=5):
    dn = int(delay * SR)
    out = np.concatenate([x, np.zeros(dn * taps)])
    for k in range(1, taps + 1):
        out[dn * k: dn * k + len(x)] += x * fb ** k
    return out


def drone(d, freqs, cutoff=400):
    t = tt(d)
    s = sum(saw_var(f * (1 + 0.003 * np.sin(2 * np.pi * 0.13 * t + i))) for i, f in enumerate(freqs))
    return lp(s, cutoff) / len(freqs)


def fade(x, fi=0.3, fo=0.3):
    n = len(x)
    e = np.ones(n)
    a, b = int(fi * SR), int(fo * SR)
    if a:
        e[:a] = np.linspace(0, 1, a)
    if b:
        e[-b:] *= np.linspace(1, 0, b)
    return x * e


def varispeed(src, rate):
    pos = np.concatenate([[0.0], np.cumsum(rate)[:-1]])
    return np.interp(pos, np.arange(len(src)), src, right=0.0)


MEL = [76, 79, 84, 79, 76, 79, 81, 79, 74, 79, 83, 79, 74, 79, 81, 83,
       72, 76, 81, 76, 72, 76, 79, 76, 77, 81, 84, 81, 79, 77, 76, 74]
ROOTS = [36, 43, 45, 41]


def music_box(notes, spacing, cents, d_total):
    buf = np.zeros(int(d_total * SR))
    for i, m in enumerate(notes):
        f = mtof(m + 12) * 2 ** ((cents + AR.uniform(-18, 18)) / 1200)
        t = tt(1.6)
        s = (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t * 4)
             + 0.15 * np.sin(2 * np.pi * 3.01 * f * t) * np.exp(-t * 6)) * np.exp(-t * 2.2) * np.minimum(1, t / 0.003)
        put(buf, s, i * spacing)
    return echo(buf, 0.33, 0.4, 5)


def build_chip():
    chip = np.zeros(int(12 * SR))
    E = BEAT / 2
    for bar in range(6):
        b0 = bar * 4 * BEAT
        for i in range(8):
            d = E * 0.9
            n = int(d * SR)
            s = square(mtof(MEL[(bar % 4) * 8 + i]), d, 0.25) * env(n, 0.003, 0.04) * np.exp(-tt(d) * 3)
            put(chip, s, b0 + i * E, 0.14)
            s2 = square(mtof(MEL[(bar % 4) * 8 + i] - 12), d, 0.125) * env(n, 0.003, 0.04) * np.exp(-tt(d) * 5)
            put(chip, s2, b0 + i * E, 0.05)
            r = ROOTS[bar % 4] + (12 if i % 2 else 0)
            put(chip, tri(mtof(r), E * 0.95) * env(int(E * 0.95 * SR), 0.003, 0.03), b0 + i * E, 0.32)
        for bt in range(4):
            put(chip, kick(), b0 + bt * BEAT, 0.8)
            if bt % 2 == 1:
                put(chip, snare(), b0 + bt * BEAT, 0.3)
            put(chip, hat(), b0 + bt * BEAT + E, 0.14)
    return chip


def build_audio():
    N = int((DUR + 1) * SR)
    mix = np.zeros(N)
    chip = build_chip()

    # --- S1-S3: cheerful chiptune -> wobble -> tape stop
    n = int(9.9 * SR)
    t = np.arange(n) / SR
    rate = np.ones(n) + 0.04 * np.sin(2 * np.pi * 4.5 * t) * np.clip((t - 7.3) / 1.2, 0, 1)
    m = t > T_S3
    rate[m] *= np.clip(1 - (t[m] - T_S3) / 1.3, 0, 1) ** 1.6
    put(mix, varispeed(chip, rate), 0, 1.0)
    # UI click + coin sounds
    for tc, big in ((T_S2 + 0.55, True), (T_S2 + 1.75, False)):
        put(mix, square(1800, 0.02) * env(int(0.02 * SR)), tc, 0.15)
        put(mix, square(988, 0.07) * env(int(0.07 * SR)), tc + 0.02, 0.12)
        put(mix, square(1319, 0.18) * env(int(0.18 * SR)) * np.exp(-tt(0.18) * 8), tc + 0.09, 0.12)
    # "new guest arrived" chime, slightly wrong
    for i, mm in enumerate((84, 88, 91, 90)):
        put(mix, np.sin(2 * np.pi * mtof(mm) * tt(0.5)) * np.exp(-tt(0.5) * 6), 7.3 + i * 0.09, 0.18)
    # pause blip + rising rumble
    put(mix, square(660, 0.08) * env(int(0.08 * SR)), T_S3, 0.15)
    put(mix, square(440, 0.12) * env(int(0.12 * SR)), T_S3 + 0.09, 0.15)
    rum = fade(drone(1.5, [41.2, 43.7, 61.7], 250), 1.2, 0.05)
    put(mix, rum, T_S3, 0.5)

    # --- S4: night
    put(mix, boom(2.0), T_S4, 0.9)
    put(mix, fade(drone(4.2, [55, 55.4, 82.4, 58.3], 380), 0.6, 0.3), T_S4, 0.55)
    muff = lp(varispeed(chip, np.full(int(4.2 * SR), 0.94)), 380)
    put(mix, fade(echo(muff, 0.21, 0.4, 3)[: int(4.2 * SR)], 0.8, 0.3), T_S4, 0.55)
    crowd = bp(noise(4.2), 250, 900) * (0.6 + 0.4 * np.sin(2 * np.pi * 0.7 * tt(4.2)))
    put(mix, fade(crowd, 0.5, 0.3), T_S4, 0.05)
    put(mix, fade(lp(noise(4.2), 500) * (0.5 + 0.5 * np.sin(2 * np.pi * 0.25 * tt(4.2))), 0.5, 0.3), T_S4, 0.12)
    put(mix, music_box(MEL[:12], 0.3, -35, 5.0), T_S4 + 0.5, 0.22)
    buzz = lp(square(100, 0.2) + noise(0.2) * 0.5, 1500) * env(int(0.2 * SR), 0.005, 0.02)
    put(mix, buzz, T_S4 + 2.0, 0.35)
    put(mix, boom(1.2, 70, 25), T_S4 + 2.18, 0.7)
    put(mix, screech(0.9, 980), T_S4 + 2.18, 0.18)
    put(mix, squelch(), T_S4 + 3.55, 0.25)

    # --- S5: CCTV cuts
    put(mix, fade(drone(T_S6 - T_S5, [36.7, 38.9, 55], 300), 0.2, 0.2), T_S5, 0.35)
    hbt, iv = T_S5 + 0.3, 0.75
    while hbt < T_S6 - 0.2:
        put(mix, thump(), hbt, 0.7)
        put(mix, thump(), hbt + 0.19, 0.5)
        hbt += iv
        iv = max(0.36, iv * 0.9)
    for k in range(5):
        t0 = T_S5 + k * CUT
        put(mix, boom(1.0, 90, 30), t0, 0.55)
        put(mix, screech(0.7, [1150, 1290, 1080, 1360, 1220][k]), t0, 0.13)
        put(mix, bp(noise(0.09), 500, 6000) * env(int(0.09 * SR), 0.001, 0.02), t0, 0.35)
        dd = CUT
        if k == 0:
            put(mix, fade(lp(hp(noise(dd), 500), 5000), 0.05, 0.05), t0, 0.1)
        elif k == 1:
            E = BEAT / 2
            for i in range(int(dd / E) + 1):
                put(mix, hp(noise(0.05), 6000) * np.exp(-tt(0.05) * 60), t0 + i * E, 0.12)
                put(mix, hp(square(mtof(MEL[i % 8]), 0.1, 0.25), 2500) * env(int(0.1 * SR)), t0 + i * E, 0.03)
        elif k == 2:
            put(mix, creak(dd, 20, 45), t0 + 0.05, 0.18)
        elif k == 3:
            tb = tt(dd)
            fly = np.sin(2 * np.pi * np.cumsum(215 + 25 * np.sin(2 * np.pi * 3 * tb)) / SR)
            put(mix, fade(fly * (0.5 + 0.5 * np.sin(2 * np.pi * 1.7 * tb)), 0.1, 0.1), t0, 0.05)
            put(mix, squelch(), t0 + 0.55, 0.2)
        else:
            for i in range(8):
                put(mix, square(880 + i * 90, 0.06) * env(int(0.06 * SR)), t0 + 0.05 + i * 0.08, 0.08)
            tb = tt(dd)
            put(mix, fade(np.sin(2 * np.pi * np.cumsum(300 + 1400 * tb / dd) / SR), 0.05, 0.05), t0, 0.07)

    # --- S6: the close-up
    d6 = T_S7 - T_S6
    sw = drone(d6, [41.2, 43.65, 61.7, 87.3], 500) * np.linspace(0.3, 1.0, int(d6 * SR))
    cut_i = int((d6 - 0.15) * SR)
    sw[cut_i:] = 0
    put(mix, fade(sw, 0.3, 0.0), T_S6, 0.6)
    tb = tt(d6)
    clus = sum(saw_var(f * (1 + 0.008 * np.sin(2 * np.pi * (5 + i * 0.7) * tb)))
               for i, f in enumerate((440, 466.2, 493.9, 523.3, 554.4, 587.3)))
    clus = lp(clus, 3000) / 6 * np.clip((tb - 1.0) / (d6 - 1.2), 0, 1) ** 2.5
    clus[cut_i:] = 0
    put(mix, clus, T_S6, 0.35)
    for st in (0.9, 1.35, 1.7, 1.95, 2.1):
        put(mix, squelch(), T_S6 + st, 0.3)
    put(mix, screech(1.0, 1400), T_S6 + 2.6, 0.2)
    put(mix, boom(1.2, 120, 30), T_S6 + 2.6, 0.6)
    put(mix, music_box(MEL[:8], 0.42, -70, 4.0)[: int((d6 - 0.2) * SR)], T_S6 + 0.3, 0.14)

    # --- S7: title slam, jingle that dies, eyes
    put(mix, boom(2.2, 110, 28), T_S7, 1.0)
    put(mix, crash(), T_S7, 0.3)
    n = int(3.6 * SR)
    t = np.arange(n) / SR
    rate = np.ones(n)
    m = t > 1.85
    rate[m] = np.clip(1 - (t[m] - 1.85) / 1.2, 0, 1) ** 1.4 + 0.03 * np.sin(2 * np.pi * 5 * t[m])
    rate = np.clip(rate, 0, None)
    put(mix, fade(varispeed(chip, rate), 0.0, 0.4), T_S7, 0.9)
    put(mix, fade(drone(DUR - T_S7 - 1.9, [55, 58.3, 82.4], 300), 1.0, 0.3), T_S7 + 1.9, 0.35)
    put(mix, creak(1.1, 14, 40), T_S7 + 3.9, 0.12)
    put(mix, squelch(), T_S7 + 4.0, 0.3)
    put(mix, squelch(0.1), T_S7 + 4.6, 0.2)
    put(mix, squelch(0.1), T_S7 + 4.72, 0.2)

    mix = mix[: int(DUR * SR)]
    mix /= np.abs(mix).max() + 1e-9
    mix = np.tanh(mix * 1.3) / np.tanh(1.3) * 0.92
    mix = fade(mix, 0.0, 0.15)
    return mix


def write_wav(path, x):
    pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def main():
    wav = "trailer_audio.wav"
    print("synthesising audio...")
    write_wav(wav, build_audio())
    if "--audio-only" in sys.argv:
        return
    stills = [a for a in sys.argv if a.startswith("--still=")]
    if stills:
        for s in stills[0][8:].split(","):
            fi = int(float(s) * FPS)
            Image.fromarray(frame(fi)).save(f"still_{s}.png")
        return
    print(f"rendering {NF} frames...")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{OW}x{OH}",
           "-r", str(FPS), "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "slow", "-crf", "23",
           "-pix_fmt", "yuv420p", "-af", "loudnorm=I=-15:TP=-1.5:LRA=11", "-ar", "44100", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", OUT]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for fi in range(NF):
        p.stdin.write(frame(fi).tobytes())
        if fi % 48 == 0:
            print(f"  {fi}/{NF}")
    p.stdin.close()
    p.wait()
    print("done ->", OUT)


if __name__ == "__main__":
    main()

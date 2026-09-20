"""Placeholder image provider — pure-Pillow EPIC CINEMATIC scene composer.

Used until OpenMontage's local diffusion is connected, so the pipeline works
offline — but tuned to render the devotional-epic look (golden-hour ghats,
floating diyas, monumental silhouettes, god rays) and to make every scene
DIFFERENT: scene type, palette and composition are driven by the scene's own
prompt keywords (temple/ghat/mountain/ocean/night/dawn...), not a random hash.
"""
import colorsys
import hashlib
import math

from PIL import Image, ImageDraw, ImageFilter

from .base import ImageProvider


# --------------------------------------------------------------- scene read --
def _detect(prompt: str) -> dict:
    p = (prompt or "").lower()
    if any(k in p for k in ("mountain", "himala", "cliff", "peak", "summit")):
        scene = "mountain"
    elif any(k in p for k in ("ghat", "oil lamp", "diya", "river gha")):
        scene = "ghat"
    elif any(k in p for k in ("ocean", "sea", "wave", "shore", "beach")):
        scene = "ocean"
    elif any(k in p for k in ("forest", "tree", "jungle", "clearing")):
        scene = "forest"
    elif any(k in p for k in ("city", "street", "rooftop", "neon", "urban")):
        scene = "city"
    elif any(k in p for k in ("temple", "mandir", "shrine", "courtyard", "aarti")):
        scene = "temple"
    else:
        scene = "plain"
    if any(k in p for k in ("night", "dark", "moon", "star", "midnight")):
        tod = "night"
    elif any(k in p for k in ("dawn", "sunrise", "morning", "pre-dawn")):
        tod = "dawn"
    elif any(k in p for k in ("storm", "rain", "twilight")):
        tod = "dusk"
    else:
        tod = "golden"   # default & evening aarti: warm golden hour
    sacred = any(k in p for k in ("devot", "temple", "ghat", "aarti", "diya", "prayer",
                                  "hanuman", "shiv", "krishna", "divine", "sacred",
                                  "bless", "mantra", "bhajan"))
    return {"scene": scene, "tod": tod, "sacred": sacred}


_SKIES = {
    "golden": [(70, 34, 30), (172, 88, 46), (240, 148, 66), (255, 210, 132)],
    "dawn":   [(56, 42, 66), (168, 104, 104), (240, 166, 120), (255, 228, 182)],
    "dusk":   [(24, 20, 48), (74, 42, 84), (170, 84, 70), (244, 150, 92)],
    "night":  [(6, 8, 26), (12, 18, 46), (24, 34, 74), (44, 58, 104)],
}
_WATER = {"golden": (74, 44, 42), "dawn": (66, 58, 82), "dusk": (34, 24, 52), "night": (8, 12, 30)}


def _mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _digest(*parts) -> bytes:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).digest()


def render_placeholder(prompt: str, out_path, seed: int = 0, width=1280, height=720,
                       label: str = "", title_text: str = ""):
    info = _detect(prompt)
    rng = _digest(prompt, seed)
    scene, tod, sacred = info["scene"], info["tod"], info["sacred"]
    sky = _SKIES[tod]
    warm = tod in ("golden", "dawn", "dusk")

    img = Image.new("RGB", (width, height))
    dr = ImageDraw.Draw(img)

    # ---- sky: 4-stop gradient ------------------------------------------------
    horizon = int(height * (0.56 + (rng[0] / 255.0) * 0.06))
    for y in range(horizon):
        t = y / max(1, horizon)
        c = _mix(sky[0], sky[1], t / 0.45) if t < 0.45 else _mix(sky[1], sky[2], (t - 0.45) / 0.55)
        if t > 0.82:
            c = _mix(c, sky[3], (t - 0.82) / 0.18)
        dr.line([(0, y), (width, y)], fill=c)

    # ---- sun / moon + glow ---------------------------------------------------
    sun_x = width * (0.16 + (rng[1] / 255.0) * 0.55)
    sun_y = horizon * (0.42 + (rng[2] / 255.0) * 0.4)
    glow = Image.new("L", (width, height), 0)
    gd = ImageDraw.Draw(glow)
    rad = int(height * (0.5 if warm else 0.32))
    for i in range(rad, 0, -3):
        a = int((150 if warm else 95) * (1 - i / rad) ** 1.6)
        gd.ellipse([sun_x - i, sun_y - i * 0.92, sun_x + i, sun_y + i * 0.92], fill=a)
    warm_col = (255, 214, 150) if warm else (210, 220, 255)
    img = Image.composite(Image.new("RGB", (width, height), warm_col), img, glow)
    dr = ImageDraw.Draw(img)
    disc_r = int(height * (0.055 + (rng[3] / 255.0) * 0.035))
    disc = (255, 236, 190) if warm else (228, 234, 255)
    dr.ellipse([sun_x - disc_r, sun_y - disc_r, sun_x + disc_r, sun_y + disc_r], fill=disc)

    # ---- god rays ------------------------------------------------------------
    if warm:
        rays = Image.new("L", (width, height), 0)
        rd = ImageDraw.Draw(rays)
        n_rays = 9 + rng[4] % 5
        for k in range(n_rays):
            ang = -1.35 + k * (2.7 / n_rays) + (rng[5 + k % 20] / 255.0 - 0.5) * 0.12
            L = width * 1.5
            w2 = math.tan(0.028 + (rng[6 + k % 20] / 255.0) * 0.02) * L
            dx, dy = math.sin(ang) * L, math.cos(ang) * L
            rd.polygon([(sun_x, sun_y), (sun_x + dx - w2, sun_y - dy),
                        (sun_x + dx + w2, sun_y - dy)], fill=46)
        rays = rays.filter(ImageFilter.GaussianBlur(6))
        img = Image.composite(Image.new("RGB", (width, height), (255, 226, 168)), img, rays)
        dr = ImageDraw.Draw(img)

    # ---- clouds (soft warm bands) -------------------------------------------
    for k in range(4):
        cw = int(width * (0.3 + (rng[8 + k] / 255.0) * 0.4))
        cx = (rng[12 + k] / 255.0) * width
        cy = horizon * (0.18 + (rng[16 + k] / 255.0) * 0.5)
        ch = int(height * 0.028)
        cloud = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        cd = ImageDraw.Draw(cloud)
        cd.ellipse([cx - cw, cy - ch, cx + cw, cy + ch],
                   fill=_mix(sky[3], (255, 255, 255), 0.25) + (60,))
        cloud = cloud.filter(ImageFilter.GaussianBlur(14))
        img = Image.alpha_composite(img.convert("RGBA"), cloud).convert("RGB")
    dr = ImageDraw.Draw(img)

    # ---- far silhouettes per scene type --------------------------------------
    dark_far = _mix(sky[1], (8, 8, 14), 0.62)
    dark_near = _mix(sky[1], (6, 6, 12), 0.8)

    def ridge(base_y, amp, seed_i, fill, rough=1.0):
        pts = [(0, height)]
        jr = _digest(prompt, seed, "ridge", seed_i)
        phase = jr[0] / 255.0 * 6.28
        for k, x in enumerate(range(0, width + 16, 16)):
            wv = (0.55 + 0.45 * math.sin(x * 0.004 * rough + phase)
                  + 0.3 * math.sin(x * 0.011 * rough + phase * 2.3))
            pts.append((x, base_y - amp * wv + (jr[k % 30] / 255.0 - 0.5) * amp * 0.3))
        pts.append((width, height))
        dr.polygon(pts, fill=fill)

    if scene in ("mountain",):
        ridge(horizon + 6, height * 0.24, 1, dark_far, 0.7)
        ridge(horizon + 10, height * 0.16, 2, dark_near, 1.3)
    elif scene == "temple" or (sacred and scene in ("ghat", "plain")):
        # temple shikhara skyline on the left horizon
        jr = _digest(prompt, seed, "temples")
        n_t = 5 + jr[1] % 4
        x = int(width * (0.02 + jr[2] / 2550.0))
        for t_i in range(n_t):
            tw_ = int(width * (0.045 + (jr[3 + t_i] / 255.0) * 0.05))
            th_ = int(height * (0.10 + (jr[7 + t_i] / 255.0) * 0.13))
            base = horizon + 4
            steps_ = 5
            for s_i in range(steps_):  # tiered shikhara
                sw = tw_ * (1 - s_i / steps_)
                sy = base - th_ * (s_i / steps_)
                dr.polygon([(x + tw_ / 2 - sw / 2, sy), (x + tw_ / 2 + sw / 2, sy),
                            (x + tw_ / 2 + sw * 0.3, sy - th_ / steps_), (x + tw_ / 2 - sw * 0.3, sy - th_ / steps_)],
                           fill=dark_far)
            dr.ellipse([x + tw_ / 2 - 4, base - th_ - 8, x + tw_ / 2 + 4, base - th_], fill=dark_far)
            x += int(tw_ * (1.5 + jr[13 + t_i] / 510.0))
            if x > width * 0.72:
                break
        ridge(horizon + 4, height * 0.05, 3, dark_far, 0.8)
    elif scene == "forest":
        jr = _digest(prompt, seed, "trees")
        for t_i in range(26):
            tx = (jr[t_i] / 255.0) * width
            th_ = height * (0.10 + (jr[26 + t_i % 30] / 255.0) * 0.14)
            tw_ = th_ * 0.22
            base = horizon + 6
            dr.polygon([(tx - tw_ / 2, base), (tx + tw_ / 2, base), (tx, base - th_)], fill=dark_far)
        ridge(horizon + 2, height * 0.04, 4, dark_near, 1.1)
    elif scene == "city":
        jr = _digest(prompt, seed, "city")
        x = 0
        b_i = 0
        while x < width:
            bw = int(width * (0.05 + jr[b_i % 30] / 2550.0))
            bh = int(height * (0.08 + (jr[(b_i * 3) % 30] / 255.0) * 0.22))
            dr.rectangle([x, horizon + 6 - bh, x + bw, horizon + 8], fill=dark_far)
            for wx in range(x + 6, x + bw - 4, 12):
                if jr[(wx + b_i) % 30] > 140:
                    dr.rectangle([wx, horizon - bh + 8, wx + 4, horizon - bh + 12],
                                 fill=(255, 208, 130))
            x += bw + 6
            b_i += 1
    else:  # plain / ocean backdrop ridges
        ridge(horizon + 4, height * 0.07, 5, dark_far, 0.9)

    # ---- water ---------------------------------------------------------------
    if scene in ("ghat", "ocean"):
        for y in range(horizon, height):
            t = (y - horizon) / max(1, height - horizon)
            c = _mix(_WATER[tod], sky[2], max(0.0, 0.42 - t * 0.9))
            dr.line([(0, y), (width, y)], fill=c)
        # shimmer strokes
        jr = _digest(prompt, seed, "shim")
        for k in range(70):
            sy = horizon + 6 + int((jr[k % 30] / 255.0) ** 1.6 * (height - horizon - 10))
            sx = (jr[(k * 3) % 30] / 255.0) * width
            sw_ = int(width * (0.01 + (jr[(k * 7) % 30] / 255.0) * 0.03))
            a = _mix(_WATER[tod], sky[3], 0.35)
            dr.line([(sx, sy), (sx + sw_, sy)], fill=a)

    # ---- ghat steps + statue + devotee (the signature composition) -----------
    if scene == "ghat":
        step_col = _mix(dark_near, (80, 50, 34), 0.35 if warm else 0.18)
        top_y, bot_y = int(height * 0.40), height
        x0 = int(width * 0.62)
        n_steps = 9
        for s_i in range(n_steps):
            t = s_i / n_steps
            sy = top_y + (bot_y - top_y) * (t ** 1.25)
            sx = x0 - width * 0.06 * t
            sw_ = width - sx
            sh_ = (bot_y - top_y) / n_steps * (0.9 + 0.3 * t)
            dr.polygon([(sx, sy), (width, sy), (width, sy + sh_), (sx + sw_ * 0.02, sy + sh_)],
                       fill=_mix(step_col, (0, 0, 0), 0.12 * s_i / n_steps))
            # oil lamps along the step edge
            jr = _digest(prompt, seed, "steplamp", s_i)
            for L_i in range(int(6 + 10 * t)):
                lx = sx + 10 + (jr[L_i % 30] / 255.0) * max(10, width - sx - 16)
                ly = sy + sh_ * 0.72
                dr.ellipse([lx - 2, ly - 2, lx + 2, ly + 2], fill=(255, 196, 110))
        # monumental seated statue silhouette (right, fully on-canvas)
        st_x = int(width * 0.82)
        st_base = int(height * 0.72)
        u = height * 0.0027          # ~2.2px unit -> statue ~ 0.40 * height tall
        col = _mix(dark_far, (10, 6, 8), 0.5)
        # halo behind head
        halo_r = 40 * u
        hy = st_base - 78 * u
        halo = Image.new("L", (width, height), 0)
        hd = ImageDraw.Draw(halo)
        hd.ellipse([st_x - halo_r, hy - halo_r, st_x + halo_r, hy + halo_r], fill=80)
        halo = halo.filter(ImageFilter.GaussianBlur(16))
        img = Image.composite(Image.new("RGB", (width, height), (255, 208, 140)), img, halo)
        dr = ImageDraw.Draw(img)
        # crossed legs (wide base)
        dr.polygon([(st_x - 56 * u, st_base), (st_x + 56 * u, st_base),
                    (st_x + 40 * u, st_base - 26 * u), (st_x - 40 * u, st_base - 26 * u)], fill=col)
        # torso (tapered)
        dr.polygon([(st_x - 38 * u, st_base - 24 * u), (st_x + 38 * u, st_base - 24 * u),
                    (st_x + 30 * u, st_base - 82 * u), (st_x - 30 * u, st_base - 82 * u)], fill=col)
        # left arm resting on knee
        dr.polygon([(st_x - 30 * u, st_base - 76 * u), (st_x - 22 * u, st_base - 72 * u),
                    (st_x - 48 * u, st_base - 30 * u), (st_x - 60 * u, st_base - 34 * u)], fill=col)
        # right arm raised in blessing
        dr.polygon([(st_x + 26 * u, st_base - 78 * u), (st_x + 34 * u, st_base - 74 * u),
                    (st_x + 46 * u, st_base - 118 * u), (st_x + 38 * u, st_base - 121 * u)], fill=col)
        dr.ellipse([st_x + 38 * u, st_base - 132 * u, st_x + 52 * u, st_base - 118 * u], fill=col)
        # head + crown
        dr.ellipse([st_x - 20 * u, st_base - 108 * u, st_x + 20 * u, st_base - 70 * u], fill=col)
        dr.polygon([(st_x - 17 * u, st_base - 100 * u), (st_x + 17 * u, st_base - 100 * u),
                    (st_x + 9 * u, st_base - 130 * u), (st_x - 9 * u, st_base - 130 * u)], fill=col)

        # devotee with sash (centre steps, back to camera)
        dv_x, dv_base = int(width * 0.555), int(height * 0.88)
        u2 = height * 0.00185
        dcol = (14, 9, 9)
        back = Image.new("L", (width, height), 0)
        bd = ImageDraw.Draw(back)
        bd.ellipse([dv_x - 26 * u2, dv_base - 96 * u2, dv_x + 26 * u2, dv_base + 8 * u2], fill=70)
        back = back.filter(ImageFilter.GaussianBlur(10))
        img = Image.composite(Image.new("RGB", (width, height), (255, 196, 120)), img, back)
        dr = ImageDraw.Draw(img)
        dr.ellipse([dv_x - 7.5 * u2, dv_base - 92 * u2, dv_x + 7.5 * u2, dv_base - 77 * u2], fill=dcol)   # head
        dr.polygon([(dv_x - 12 * u2, dv_base - 75 * u2), (dv_x + 12 * u2, dv_base - 75 * u2),
                    (dv_x + 16 * u2, dv_base), (dv_x - 16 * u2, dv_base)], fill=dcol)                     # dhoti body
        dr.line([(dv_x + 3 * u2, dv_base - 70 * u2), (dv_x + 26 * u2, dv_base - 12 * u2)],
                fill=(150, 46, 38), width=max(2, int(4 * u2)))                                            # saffron sash
        dr.line([(dv_x - 3 * u2, dv_base - 70 * u2), (dv_x - 22 * u2, dv_base - 16 * u2)],
                fill=(150, 46, 38), width=max(2, int(4 * u2)))

    # ---- floating diyas on water (ghat) or embers -----------------------------
    jr = _digest(prompt, seed, "diya")
    n_l = 46 if scene in ("ghat", "ocean") else 24
    for k in range(n_l):
        ly = horizon + 8 + ((jr[k % 30] / 255.0) ** 1.5) * max(4, height - horizon - 14)
        lx = (jr[(k * 5 + 3) % 30] / 255.0) * width
        if scene == "ghat" and lx > width * 0.55 and ly > height * 0.45:
            continue  # keep the steps area clean
        r_ = 2 + jr[(k * 2) % 30] % 3
        gl = Image.new("L", (width, height), 0)
        gld = ImageDraw.Draw(gl)
        gld.ellipse([lx - r_ * 5, ly - r_ * 5, lx + r_ * 5, ly + r_ * 5], fill=110)
        gl = gl.filter(ImageFilter.GaussianBlur(4))
        img = Image.composite(Image.new("RGB", (width, height), (255, 186, 100)), img, gl)
        dr = ImageDraw.Draw(img)
        dr.ellipse([lx - r_, ly - r_, lx + r_, ly + r_], fill=(255, 226, 160))
        if scene == "ocean" or (scene == "ghat" and lx < width * 0.52):
            dr.line([(lx, ly + r_ + 1), (lx, ly + r_ * 3 + 6)], fill=(120, 74, 40), width=1)

    # ---- birds ----------------------------------------------------------------
    jr = _digest(prompt, seed, "birds")
    for k in range(5 + jr[0] % 4):
        bx = (jr[(k * 3) % 30] / 255.0) * width
        by = horizon * (0.2 + (jr[(k * 7) % 30] / 255.0) * 0.5)
        s_ = 3 + jr[k % 30] % 4
        dr.arc([bx - s_, by - s_ // 2, bx, by + s_ // 2], 200, 340, fill=(30, 22, 24), width=1)
        dr.arc([bx, by - s_ // 2, bx + s_, by + s_ // 2], 200, 340, fill=(30, 22, 24), width=1)

    # ---- atmosphere: mist + particles -----------------------------------------
    mist = Image.new("L", (width, height), 0)
    md = ImageDraw.Draw(mist)
    for k in range(3):
        my = horizon - height * (0.02 + k * 0.03)
        md.ellipse([-width * 0.2, my - 18, width * 1.2, my + 18], fill=52 - k * 12)
    mist = mist.filter(ImageFilter.GaussianBlur(22))
    img = Image.composite(Image.new("RGB", (width, height), (255, 226, 190) if warm else (170, 185, 220)),
                          img, mist)
    dr = ImageDraw.Draw(img)
    for i in range(110):  # stars / embers / dust
        px = (_digest(prompt, seed, "p", i)[0] / 255.0) * width
        py = (_digest(prompt, seed, "p", i)[1] / 255.0) * height * 0.85
        pr = 1 + i % 2
        col = (255, 244, 214) if tod == "night" else (255, 210, 150)
        dr.ellipse([px - pr, py - pr, px + pr, py + pr], fill=col)

    # ---- vignette + warm grade -------------------------------------------------
    vig = Image.new("L", (width, height), 0)
    vd = ImageDraw.Draw(vig)
    vd.ellipse([-width * 0.22, -height * 0.22, width * 1.22, height * 1.22], fill=255)
    vig = vig.filter(ImageFilter.GaussianBlur(110))
    img = Image.composite(img, Image.new("RGB", (width, height), (6, 5, 10)), vig)
    if warm:
        overlay = Image.new("RGB", (width, height), (255, 150, 60))
        img = Image.blend(img, overlay, 0.06)

    # ---- texts (unchanged behaviour) -------------------------------------------
    if title_text:
        try:
            from PIL import ImageFont
            from .config import SETTINGS
            font = None
            for cand in ["NotoSansDevanagari-Bold.ttf", "NotoSansDevanagari.ttf"]:
                if (SETTINGS.fonts_dir / cand).exists():
                    font = ImageFont.truetype(str(SETTINGS.fonts_dir / cand), int(height * 0.14))
                    break
            if font is None:
                font = ImageFont.load_default()
            dr = ImageDraw.Draw(img)
            bbox = dr.textbbox((0, 0), title_text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            tx, ty = (width - tw) // 2, int(height * 0.09)
            dr.text((tx + 4, ty + 4), title_text, font=font, fill=(0, 0, 0))
            dr.text((tx, ty), title_text, font=font, fill=(255, 244, 214))
        except Exception:
            pass
    if label:
        try:
            from PIL import ImageFont
            from .config import SETTINGS
            font = None
            for cand in ["NotoSans-Regular.ttf", "NotoSans-Bold.ttf",
                         "NotoSansDevanagari-Regular.ttf", "NotoSansDevanagari.ttf"]:
                if (SETTINGS.fonts_dir / cand).exists():
                    font = ImageFont.truetype(str(SETTINGS.fonts_dir / cand), int(height * 0.028))
                    break
            if font is None:
                font = ImageFont.load_default()
            dr = ImageDraw.Draw(img)
            dr.text((18, height - int(height * 0.05)), label, font=font, fill=(255, 255, 255))
        except Exception:
            pass

    out_path = str(out_path)
    if out_path.lower().endswith(".png"):
        img.save(out_path)
    else:
        img.save(out_path, quality=90)
    return out_path


class PlaceholderImageProvider(ImageProvider):
    name = "placeholder"

    def generate(self, prompt, negative, out_path, seed: int = 0, width=1280, height=720):
        return render_placeholder(prompt, out_path, seed=seed, width=width, height=height)

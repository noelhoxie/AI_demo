#!/usr/bin/env python3
"""
Generate 10 realistic automotive E-Coat inspection images.
Clean images simulate a high-quality metallic paint surface.
Defect images (003, 007) have small, subtle E-Coat adhesion failures
that are genuinely hard to spot without close inspection.
"""

from PIL import Image, ImageFilter
import numpy as np
import random
import math
import os

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "static", "img", "inspection")
os.makedirs(OUTPUT_DIR, exist_ok=True)

W, H = 320, 320

# ── Colour palette — silver-blue metallic variants ─────────────────────────────
PALETTES = [
    [0.431, 0.462, 0.539],   # Silver-blue
    [0.449, 0.473, 0.523],   # Cool silver
    [0.418, 0.453, 0.516],   # Steel blue
    [0.461, 0.469, 0.488],   # Warm silver
    [0.427, 0.465, 0.548],   # Deep blue-silver
    [0.445, 0.458, 0.511],   # Neutral grey-blue
    [0.438, 0.469, 0.531],   # Soft blue-silver
]


def make_surface(seed):
    """
    Generate a realistic metallic painted body panel surface.
    Simulates: ambient + directional lighting, clearcoat specular,
    orange-peel texture, metallic flake sparkle, paint lay lines,
    camera sensor noise.
    """
    rng = np.random.RandomState(seed)
    bc  = np.array(PALETTES[seed % len(PALETTES)])

    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    xs, ys = xx / W, yy / H   # normalised 0→1

    # ── 1. Diffuse lighting gradient ─────────────────────────────────────
    # Primary: soft overhead-left source
    light = 0.82 + 0.14 * (1 - ys) + 0.07 * (1 - xs)
    # Secondary: subtle warm fill from bottom-right
    light += 0.04 * ys * xs

    # ── 2. Specular / clearcoat highlight ───────────────────────────────
    scx = W * (0.50 + 0.14 * rng.randn())
    scy = H * (0.22 + 0.06 * rng.randn())
    sdx = np.sqrt(((xx - scx) / (W * 0.38))**2 + ((yy - scy) / (H * 0.16))**2)
    light += 0.18 * np.exp(-sdx**2)

    # ── 3. Orange-peel clearcoat texture ────────────────────────────────
    # Four overlapping sine-waves at different frequencies + angles
    op = np.zeros((H, W), dtype=np.float32)
    for freq, amp in [(6, 0.022), (10, 0.016), (17, 0.011), (28, 0.007)]:
        ang = rng.uniform(0, 2 * math.pi)
        px  = rng.uniform(0, 2 * math.pi)
        py  = rng.uniform(0, 2 * math.pi)
        op += amp * (
            np.sin(freq * (xs * math.cos(ang) + ys * math.sin(ang)) * 2 * math.pi + px) *
            np.cos(freq * (xs * math.sin(ang) - ys * math.cos(ang)) * 2 * math.pi + py)
        )
    light += op

    # ── 4. Paint lay-lines (horizontal banding from spray application) ──
    lay = np.zeros((H, W), dtype=np.float32)
    for row in range(H):
        lay[row, :] = 0.009 * math.sin(row * 0.38 + float(rng.uniform(0, 6)))
    light += lay

    # ── 5. Metallic flake sparkle ────────────────────────────────────────
    flake = np.zeros((H, W), dtype=np.float32)
    nf = rng.randint(600, 900)
    fy = rng.randint(0, H, nf)
    fx = rng.randint(0, W, nf)
    fb = rng.uniform(-0.06, 0.14, nf)   # bias bright (aluminium flakes)
    flake[fy, fx] = fb
    # Tiny 2-px blur so flakes aren't single-pixel dots
    flake_img = Image.fromarray(np.clip(flake * 255 + 128, 0, 255).astype(np.uint8)).convert('L')
    flake_img = flake_img.filter(ImageFilter.GaussianBlur(radius=0.6))
    flake = (np.array(flake_img).astype(np.float32) - 128) / 255.0

    # ── 6. Sensor / compression noise ───────────────────────────────────
    noise = rng.normal(0, 0.010, (H, W)).astype(np.float32)

    # ── Compose RGB ──────────────────────────────────────────────────────
    total = light + noise
    img_arr = np.zeros((H, W, 3), dtype=np.float32)
    for c in range(3):
        img_arr[:, :, c] = bc[c] * total
    # Metallic flakes shift hue slightly (aluminium: R+, B-)
    img_arr[:, :, 0] = np.clip(img_arr[:, :, 0] + flake * 0.55, 0, 1)
    img_arr[:, :, 1] = np.clip(img_arr[:, :, 1] + flake * 0.25, 0, 1)
    img_arr[:, :, 2] = np.clip(img_arr[:, :, 2] - flake * 0.20, 0, 1)

    return np.clip(img_arr * 255, 0, 255).astype(np.uint8)


def add_surface_imperfections(arr, seed):
    """
    Add natural surface micro-imperfections to clean panels:
    hairline scratches, dust motes, tiny panel edge reflections.
    These are NOT defects — just visual realism.
    """
    rng = np.random.RandomState(seed + 500)

    # 1–2 hairline scratches (1-px wide, partial lines)
    n_scratches = rng.randint(0, 3)
    for _ in range(n_scratches):
        x0 = rng.randint(20, W - 40)
        y0 = rng.randint(30, H - 30)
        length = rng.randint(18, 55)
        angle  = rng.uniform(-0.25, 0.25)   # nearly horizontal
        bright = rng.randint(12, 22)
        for t in range(length):
            px = int(x0 + t * math.cos(angle))
            py = int(y0 + t * math.sin(angle))
            if 0 <= px < W and 0 <= py < H:
                arr[py, px] = np.clip(arr[py, px].astype(int) + bright, 0, 255)

    # 3–6 micro dust motes (very faint dark specks, 1px)
    n_dust = rng.randint(3, 7)
    fy = rng.randint(5, H - 5, n_dust)
    fx = rng.randint(5, W - 5, n_dust)
    for i in range(n_dust):
        arr[fy[i], fx[i]] = np.clip(arr[fy[i], fx[i]].astype(int) - rng.randint(8, 18), 0, 255)

    return arr


def add_ecoat_defect(arr, cx, cy, radius, severity, seed):
    """
    Add a realistic but subtle E-Coat adhesion failure.

    The defect manifests as a small matte/flat patch in the otherwise
    glossy clearcoat — the affected area has:
      • Very slight darkening (loss of specular highlight)
      • Subtle change in texture (less orange-peel, slightly smoother)
      • 1–2 barely-visible micro-blisters (2px) at the centre
    Total affected area: ~2× radius, but the obvious visual signature
    is much smaller — genuinely hard to spot in the real image.
    """
    rng = np.random.RandomState(seed + 200)
    H_arr, W_arr = arr.shape[:2]
    yy, xx = np.mgrid[0:H_arr, 0:W_arr].astype(np.float32)

    # Normalised distance from defect centre (ellipse, slightly irregular)
    shape_rx = radius * (1.0 + 0.12 * rng.randn())
    shape_ry = radius * (1.0 + 0.12 * rng.randn())
    dist = np.sqrt(((xx - cx) / shape_rx)**2 + ((yy - cy) / shape_ry)**2)

    # ── Smooth falloff mask (1 inside, 0 outside) ───────────────────────
    # Use a gentle cubic falloff so the edge is imperceptible
    mask = np.clip(1.0 - dist, 0, 1)
    mask = mask ** 3   # very soft edge

    # ── 1. Matte effect: reduce specular highlight in the region ────────
    # Loss of gloss appears as slight darkening (~7–13 intensity units)
    dark = 9.0 if severity == "MEDIUM" else 13.0
    arr_f = arr.astype(np.float32)
    arr_f[:, :, 0] -= mask * dark * 1.10
    arr_f[:, :, 1] -= mask * dark * 1.00
    arr_f[:, :, 2] -= mask * dark * 0.82

    # ── 2. Texture change: slight smoothing (matte vs gloss) ────────────
    # Convert to PIL, blur defect region, blend back
    pil_tmp  = Image.fromarray(np.clip(arr_f, 0, 255).astype(np.uint8))
    pil_blur = pil_tmp.filter(ImageFilter.GaussianBlur(radius=1.4))
    arr_blur = np.array(pil_blur).astype(np.float32)

    blend = 0.55   # How much blur to blend in
    for c in range(3):
        arr_f[:, :, c] = (arr_f[:, :, c] * (1 - mask * blend)
                          + arr_blur[:, :, c] * (mask * blend))

    arr_f = np.clip(arr_f, 0, 255)

    # ── 3. Micro-blisters (1–2 tiny spots, 1–2px radius) ─────────────
    n_blisters = 2 if severity == "HIGH" else 1
    for _ in range(n_blisters):
        angle  = rng.uniform(0, 2 * math.pi)
        rdist  = rng.uniform(0.05, 0.50) * radius
        bx = int(cx + rdist * math.cos(angle))
        by = int(cy + rdist * math.sin(angle))
        br = rng.randint(1, 2)   # 1–2px — genuinely tiny
        for dy in range(-br - 1, br + 2):
            for dx in range(-br - 1, br + 2):
                dist_b = math.sqrt(dx**2 + dy**2)
                if dist_b <= br + 0.5:
                    bpx, bpy = bx + dx, by + dy
                    if 0 <= bpx < W_arr and 0 <= bpy < H_arr:
                        # Centre slightly lighter (gas pocket), edge slightly darker
                        delta = 10 if dist_b < br * 0.6 else -5
                        arr_f[bpy, bpx] = np.clip(arr_f[bpy, bpx] + delta, 0, 255)

    return np.clip(arr_f, 0, 255).astype(np.uint8)


# ── Image specs ────────────────────────────────────────────────────────────────
#   id, seed, defect=(cx, cy, radius, severity) or None
SPECS = [
    ("insp_001",  11, None),
    ("insp_002",  22, None),
    ("insp_003",  33, (162, 174, 18, "HIGH")),     # Small — 36×36px bbox
    ("insp_004",  44, None),
    ("insp_005",  55, None),
    ("insp_006",  66, None),
    ("insp_007",  77, (193, 108, 16, "MEDIUM")),   # Smaller — 32×32px bbox
    ("insp_008",  88, None),
    ("insp_009",  99, None),
    ("insp_010", 110, None),
]

# Pre-compute bboxes for api.py reference (cx±radius*1.2 to give a small margin)
def bbox_from_defect(cx, cy, r):
    m = int(r * 1.25)
    return [cx - m, cy - m, cx + m, cy + m]

print(f"Generating {len(SPECS)} inspection images → {OUTPUT_DIR}\n")
for img_id, seed, defect in SPECS:
    arr = make_surface(seed)

    if defect:
        cx, cy, radius, severity = defect
        arr = add_ecoat_defect(arr, cx, cy, radius, severity, seed)
        bb = bbox_from_defect(cx, cy, radius)
        status = f"DEFECT  cx={cx} cy={cy} r={radius} sev={severity}  bbox={bb}"
    else:
        arr = add_surface_imperfections(arr, seed)
        status = "CLEAN"

    Image.fromarray(arr).save(os.path.join(OUTPUT_DIR, f"{img_id}.png"))
    print(f"  {img_id}.png  [{status}]")

print(f"\nDone — {len(SPECS)} images saved.")
print("\nBbox reference for api.py INSPECTION_IMAGES:")
for img_id, seed, defect in SPECS:
    if defect:
        cx, cy, radius, severity = defect
        bb = bbox_from_defect(cx, cy, radius)
        print(f"  {img_id}: bbox={bb}  severity={severity}")

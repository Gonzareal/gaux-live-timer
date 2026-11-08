import math, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

RED = np.array([210, 5, 15]); WHITE = np.array([240, 240, 240]); BLACK = np.array([10, 10, 10])
SMOKE = np.array([42, 42, 42])
S = 1024; SS = 2; W = S * SS
yy, xx = np.mgrid[0:W, 0:W].astype(np.float32)
cx = cy = W / 2

def noise1d(n, scale, rng):
    """Ruido suave 1D de largo n con 'scale' muestras por ciclo."""
    k = max(2, int(n / scale) + 3)
    pts = rng.random(k).astype(np.float32)
    x = np.linspace(0, k - 3, n)
    i = x.astype(int); f = x - i
    f = f * f * (3 - 2 * f)
    return pts[i] * (1 - f) + pts[i + 1] * f

def stroke_alpha(u, v, rng, dry=0.55, rag=0.10, head=0.08, tail=0.22):
    """u: 0..1 a lo largo del trazo, v: -1..1 a lo ancho. Devuelve alfa de brocha seca."""
    inside = (u > -0.05) & (u < 1.05) & (np.abs(v) < 1.4)
    a = np.zeros_like(u)
    if not inside.any():
        return a
    U, V = u[inside], v[inside]
    # ancho: entra redondeado, sale afinándose y deshilachado
    w = np.ones_like(U)
    w = np.where(U < head, np.sqrt(np.clip(U / head, 0, 1)), w)
    w = np.where(U > 1 - tail, np.clip((1 - U) / tail, 0, 1) ** 0.6, w)
    # borde irregular (dos bordes distintos)
    e1 = noise1d(512, 18, rng); e2 = noise1d(512, 18, rng)
    iu = np.clip((U * 511).astype(int), 0, 511)
    edge = np.where(V > 0, e1[iu], e2[iu])
    fine = noise1d(512, 4, rng)[iu]
    lim = w * (1 - rag + rag * 2 * (edge - 0.5) * 1.6) - 0.05 * fine
    body = np.clip((lim - np.abs(V)) * 14, 0, 1)
    # fibras: rayas finas a lo largo; más secas hacia la cola
    fib = noise1d(1024, 3.2, rng)
    iv = np.clip(((V + 1.4) / 2.8 * 1023).astype(int), 0, 1023)
    f = fib[iv]
    dryness = dry * np.clip((U - 0.35) / 0.65, 0, 1) ** 1.3 + 0.12
    gaps = 0.8 * f + 0.2 * noise1d(512, 60, rng)[iu]
    keep = np.clip((gaps - dryness * (1 - np.abs(V) * 0.2)) * 8 + 0.5, 0, 1)
    keep = np.maximum(keep, (U < 0.3) * 0.9)          # el inicio sale cargado de pintura
    a[inside] = body * keep
    return a

def arc_uv(R, t, a0, a1):
    th = (np.degrees(np.arctan2(yy - cy, xx - cx)) % 360).astype(np.float32)
    r = np.hypot(xx - cx, yy - cy)
    span = (a1 - a0) % 360
    rel = (th - a0) % 360
    rel = np.where(rel > span + (360 - span) / 2, rel - 360, rel)
    return rel / span, (r - R) / (t / 2)

def line_uv(x0, y0, x1, y1, t):
    dx, dy = x1 - x0, y1 - y0
    L = math.hypot(dx, dy)
    ux, uy = dx / L, dy / L
    u = ((xx - x0) * ux + (yy - y0) * uy) / L
    v = ((xx - x0) * -uy + (yy - y0) * ux) / (t / 2)
    return u, v

def comp(base, alpha, color):
    a = alpha[..., None]
    return base * (1 - a) + color * a

def background():
    img = np.ones((W, W, 3), np.float32) * BLACK
    d = np.hypot(xx - cx, (yy - cy * 0.9)) / (W * 0.5)
    img += (SMOKE - BLACK) * np.clip(1 - d, 0, 1)[..., None] ** 2 * 0.9
    # grano sutil
    g = np.random.default_rng(3).normal(0, 2.2, (W, W, 1)).astype(np.float32)
    return img + g

def squircle():
    m = Image.new("L", (W, W), 0)
    ImageDraw.Draw(m).rounded_rectangle([100*SS, 100*SS, W-100*SS, W-100*SS], 185*SS, fill=255)
    return np.asarray(m, np.float32) / 255

def bolt_alpha(cxb, cyb, s, rot, rng):
    pts = [(40, -215), (-105, 25), (-5, 25), (-45, 215), (110, -30), (10, -30)]
    c, si = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    P = [(cxb + (x*c - y*si)*s*SS, cyb + (x*si + y*c)*s*SS) for x, y in pts]
    m = Image.new("L", (W, W), 0); ImageDraw.Draw(m).polygon(P, fill=255)
    m = m.filter(ImageFilter.GaussianBlur(2*SS))
    a = np.asarray(m, np.float32) / 255
    # bordes de brocha: ruido que muerde el contorno
    n = np.asarray(Image.fromarray((rng.random((W//12, W//12))*255).astype(np.uint8)).resize((W, W), Image.BICUBIC), np.float32)/255
    a = np.clip((a + (n - 0.5) * 0.35 - 0.5) * 6 + 0.5, 0, 1)
    return a

def logo(name, n_seg=8, done=6, seed=4, bolt_s=0.86, R0=292, T0=128, gap=0.06):
    rng = np.random.default_rng(seed)
    img = background()
    R, t = R0*SS, T0*SS
    a_start, a_end = 20, 316                      # la G abre arriba a la derecha
    span = (a_end - a_start) / n_seg
    glow = np.zeros((W, W), np.float32)
    # barra de la G: brochazo hacia adentro, justo encima de donde arranca el arco
    yb = cy + 8*SS
    u, v = line_uv(cx + R + t*0.48, yb, cx + 96*SS, yb - 4*SS, 108*SS)
    bar = stroke_alpha(u, v, rng, dry=0.7, rag=0.10, head=0.05, tail=0.34)
    img = comp(img, bar, RED); glow = np.maximum(glow, bar)
    for i in range(n_seg):
        s0 = a_start + i * span + span * gap
        s1 = a_start + (i + 1) * span - span * gap
        u, v = arc_uv(R + rng.normal(0, 2*SS), t * rng.uniform(0.93, 1.03), s0, s1)
        al = stroke_alpha(u, v, rng, dry=0.55, rag=0.09, head=0.07, tail=0.30)
        col = RED if i < done else SMOKE * 1.7
        img = comp(img, al, col)
        if i < done:
            glow = np.maximum(glow, al)
    gl = np.asarray(Image.fromarray((glow*255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(44*SS)), np.float32)/255
    img = img + (RED - img) * (gl[..., None] * 0.25)
    b = bolt_alpha(cx - 70*SS, cy - 26*SS, bolt_s, 12, rng)
    sh = np.asarray(Image.fromarray((b*255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(14*SS)), np.float32)/255
    sh = np.roll(np.roll(sh, 12*SS, 0), 9*SS, 1)
    img = comp(img, sh * 0.8, np.array([0, 0, 0]))
    img = comp(img, b, WHITE)
    m = squircle()
    rgba = np.dstack([np.clip(img, 0, 255), m * 255]).astype(np.uint8)
    out = Image.fromarray(rgba, "RGBA").resize((S, S), Image.LANCZOS)
    out.save(name)
    return out

if __name__ == "__main__":
    ims = [logo("E1.png", 8, 6, 4), logo("E2.png", 8, 6, 17), logo("E3.png", 12, 9, 21, gap=0.10)]
    sheet = Image.new("RGBA", (S*3 + 80, S + 40), (245, 245, 245, 255))
    for i, im in enumerate(ims):
        sheet.paste(im, (20 + i*(S + 20), 20), im)
    sheet.resize((sheet.width//2, sheet.height//2), Image.LANCZOS).save("brocha.png")
    print("ok")

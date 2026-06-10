from __future__ import annotations

import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "output" / "demo-video" / "lost-found-desk-demo-real.mp4"
INTRO = ROOT / "output" / "demo-video" / "lost-found-desk-demo-intro.mp4"
OUTRO = ROOT / "output" / "demo-video" / "lost-found-desk-tech-outro.mp4"
FINAL = ROOT / "output" / "demo-video" / "lost-found-desk-demo-real-hackathon.mp4"

WIDTH, HEIGHT = 1440, 900
FPS = 30
INTRO_SECONDS = 8
OUTRO_SECONDS = 30

INK = (31, 31, 30)
MUTED = (88, 86, 80)
PAPER = (248, 246, 240)
SURFACE = (255, 255, 255)
LINE = (220, 216, 206)
BLUE = (38, 102, 178)
VIOLET = (65, 61, 170)
GREEN = (36, 126, 91)
GOLD = (205, 139, 31)
ROSE = (176, 72, 96)

# Outro scene boundaries (seconds) and the cross-scene fade length.
SCENE_ENDS = (5.2, 15.2, 23.8, float(OUTRO_SECONDS))
SCENE_FADE = 0.35


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for path in [
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    ]:
        try:
            return ImageFont.truetype(path, size=size, index=1 if bold else 0)
        except Exception:
            continue
    return ImageFont.load_default(size=size)


F = {
    "hero": font(64, True),
    "h1": font(46, True),
    "h2": font(30, True),
    "body": font(23),
    "small": font(18),
    "tiny": font(15),
    "badge": font(16, True),
}


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, cwd=ROOT, check=True)


def ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def progress(t: float, start: float, seconds: float = 0.7) -> float:
    """Eased 0..1 progress for draw-on animations (bars, arrows)."""
    return ease((t - start) / seconds)


def appear(t: float, start: float, seconds: float = 0.7) -> tuple[int, int]:
    """Fade-in plus a slide-up: returns (alpha, y_offset)."""
    p = progress(t, start, seconds)
    return round(255 * p), round((1 - p) * 36)


def mix(a: tuple[int, int, int], b: tuple[int, int, int], p: float) -> tuple[int, int, int]:
    return tuple(round(a[i] * (1 - p) + b[i] * p) for i in range(3))


def rgba(c: tuple[int, int, int], alpha: int) -> tuple[int, int, int, int]:
    return c[0], c[1], c[2], alpha


def tsize(text: str, face: ImageFont.FreeTypeFont) -> tuple[int, int]:
    box = face.getbbox(text)
    return box[2] - box[0], box[3] - box[1]


def wrap(text: str, face: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = word if not current else f"{current} {word}"
        if tsize(trial, face)[0] <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    value: str,
    face: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int] = INK,
    anchor: str = "la",
    alpha: int = 255,
) -> None:
    draw.text(xy, value, font=face, fill=rgba(fill, alpha), anchor=anchor)


def paragraph(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    value: str,
    face: ImageFont.FreeTypeFont,
    max_width: int,
    fill: tuple[int, int, int] = MUTED,
    leading: float = 1.35,
    alpha: int = 255,
) -> int:
    for line in wrap(value, face, max_width):
        draw_text(draw, (x, y), line, face, fill, alpha=alpha)
        y += round(face.size * leading)
    return y


def centered_paragraph(
    draw: ImageDraw.ImageDraw,
    cx: int,
    y: int,
    value: str,
    face: ImageFont.FreeTypeFont,
    max_width: int,
    fill: tuple[int, int, int] = MUTED,
    leading: float = 1.42,
    alpha: int = 255,
) -> int:
    for line in wrap(value, face, max_width):
        draw_text(draw, (cx, y), line, face, fill, anchor="ma", alpha=alpha)
        y += round(face.size * leading)
    return y


def kicker(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    color: tuple[int, int, int] = VIOLET,
    alpha: int = 255,
    anchor: str = "la",
) -> None:
    draw_text(draw, xy, " ".join(text.upper()), F["badge"], color, anchor=anchor, alpha=alpha)


def accent_bar(draw: ImageDraw.ImageDraw, cx: int, y: int, width: int, p: float = 1.0) -> None:
    """Gradient bar that draws itself outward from the center."""
    w = round(width * p)
    if w < 4:
        return
    x = cx - w // 2
    for i in range(0, w, 2):
        c = mix(BLUE, VIOLET, i / max(1, w - 1))
        draw.rectangle((x + i, y, x + i + 2, y + 4), fill=c)


def rounded(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    radius: int,
    fill: tuple[int, int, int] | tuple[int, int, int, int],
    outline: tuple[int, int, int] | tuple[int, int, int, int] | None = None,
    width: int = 1,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def soft_shadow(img: Image.Image, box: tuple[int, int, int, int], radius: int = 18) -> None:
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle((box[0], box[1] + 10, box[2], box[3] + 10), radius=radius, fill=(0, 0, 0, 24))
    img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(18)))


def base_background() -> Image.Image:
    # RGB base: PIL only alpha-blends draws ("RGBA" draw mode) onto RGB images.
    img = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    d = ImageDraw.Draw(img, "RGBA")
    for y in range(0, HEIGHT):
        p = y / HEIGHT
        c = mix(PAPER, (238, 241, 246), p * 0.2)
        d.line((0, y, WIDTH, y), fill=c)
    for y in range(70, HEIGHT, 92):
        d.line((0, y, WIDTH, y), fill=(145, 139, 126, 24), width=1)
    for x in range(-180, WIDTH, 104):
        d.line((x, 0, x + 230, HEIGHT), fill=(145, 139, 126, 18), width=1)
    return img


def header(draw: ImageDraw.ImageDraw) -> None:
    rounded(draw, (56, 46, 282, 86), 20, rgba(SURFACE, 220), rgba(LINE, 220))
    draw_text(draw, (80, 58), "Build Small Hackathon", F["badge"], VIOLET)
    draw_text(draw, (1120, 58), "Lost & Found Desk", F["badge"], INK)


def pill_row(
    draw: ImageDraw.ImageDraw,
    cx: int,
    y: int,
    labels: list[tuple[str, tuple[int, int, int]]],
    t: float | None = None,
    start: float = 0.0,
    alpha: int = 255,
) -> None:
    """A centered pill row; with t/start, the pills cascade in one by one."""
    pad, gap, h = 15, 18, 36
    widths = [tsize(label, F["badge"])[0] + pad * 2 for label, _ in labels]
    x = cx - (sum(widths) + gap * (len(labels) - 1)) // 2
    for n, ((label, color), w) in enumerate(zip(labels, widths)):
        if t is None:
            a, dy = alpha, 0
        else:
            a, dy = appear(t, start + n * 0.14)
        rounded(
            draw,
            (x, y + dy, x + w, y + dy + h),
            18,
            rgba(mix(color, SURFACE, 0.88), a),
            rgba(mix(color, SURFACE, 0.35), a),
        )
        draw_text(draw, (x + w // 2, y + dy + 9), label, F["badge"], color, anchor="ma", alpha=a)
        x += w + gap


def scene_dots(draw: ImageDraw.ImageDraw, active: int, total: int = 4) -> None:
    cx = WIDTH // 2 - (total - 1) * 14
    for n in range(total):
        x = cx + n * 28
        if n == active:
            rounded(draw, (x - 14, HEIGHT - 46, x + 14, HEIGHT - 36), 5, rgba(VIOLET, 230))
        else:
            rounded(draw, (x - 5, HEIGHT - 46, x + 5, HEIGHT - 36), 5, rgba(MUTED, 90))


def simple_card(
    img: Image.Image,
    box: tuple[int, int, int, int],
    title: str,
    body: str,
    color: tuple[int, int, int],
    tag: str,
    alpha: int = 255,
) -> None:
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x1, y1, x2, _ = box
    fill = rgba(SURFACE, alpha)
    outline = rgba(LINE, min(alpha, 220))
    rounded(d, box, 18, fill, outline)
    rounded(d, (x1 + 22, y1 + 24, x1 + 72, y1 + 74), 14, rgba(mix(color, SURFACE, 0.82), alpha))
    draw_text(d, (x1 + 47, y1 + 38), tag, F["body"], color, anchor="ma", alpha=alpha)
    draw_text(d, (x1 + 94, y1 + 30), title, F["h2"], INK, alpha=alpha)
    paragraph(d, x1 + 94, y1 + 76, body, F["small"], x2 - x1 - 118, MUTED, alpha=alpha)
    img.paste(layer, (0, 0), layer)


def add_vignette(img: Image.Image, strength: int = 80) -> None:
    mask = Image.new("L", (WIDTH // 8, HEIGHT // 8), 0)
    d = ImageDraw.Draw(mask)
    d.ellipse(
        (-WIDTH // 20, -HEIGHT // 20, WIDTH // 8 + WIDTH // 20, HEIGHT // 8 + HEIGHT // 20),
        fill=255,
    )
    mask = mask.resize((WIDTH, HEIGHT)).filter(ImageFilter.GaussianBlur(90))
    dark = Image.new("RGBA", img.size, (24, 21, 16, strength))
    clear = Image.new("RGBA", img.size, (0, 0, 0, 0))
    img.alpha_composite(Image.composite(clear, dark, mask))


def intro_assets(path: Path) -> tuple[Image.Image, Image.Image, Image.Image]:
    """Returns (blurred photo backdrop, static white panel layer, sharp app frame)."""
    sharp = Image.open(path).convert("RGB").resize((WIDTH, HEIGHT))
    photo = sharp.convert("RGBA")
    photo = photo.filter(ImageFilter.GaussianBlur(6))
    photo = ImageEnhance.Brightness(photo).enhance(0.86)
    wash = Image.new("RGBA", photo.size, rgba(PAPER, 178))
    photo.alpha_composite(wash)
    add_vignette(photo)

    panel = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    soft_shadow(panel, (140, 120, 1300, 780), radius=30)
    pd = ImageDraw.Draw(panel)
    rounded(pd, (140, 120, 1300, 780), 30, rgba(SURFACE, 238), rgba(LINE, 230))
    return photo.convert("RGB"), panel, sharp


def render_intro_frame(
    i: int,
    photo: Image.Image,
    panel: Image.Image,
    sharp: Image.Image,
) -> Image.Image:
    t = i / FPS
    total = FPS * INTRO_SECONDS

    # Ken Burns: the blurred backdrop slowly zooms in behind the static panel.
    zoom = 1.0 + 0.05 * (i / max(1, total - 1))
    w, h = round(WIDTH / zoom), round(HEIGHT / zoom)
    x0, y0 = (WIDTH - w) // 2, (HEIGHT - h) // 2
    img = photo.crop((x0, y0, x0 + w, y0 + h)).resize((WIDTH, HEIGHT), Image.BILINEAR)
    img.paste(panel, (0, 0), panel)
    d = ImageDraw.Draw(img, "RGBA")

    a, dy = appear(t, 0.3)
    kicker(d, (WIDTH // 2, 168 + dy), "Build Small Hackathon · Backyard AI", VIOLET, alpha=a, anchor="ma")

    a, dy = appear(t, 0.55)
    draw_text(d, (WIDTH // 2, 202 + dy), "Lost & Found Desk", F["hero"], INK, anchor="ma", alpha=a)

    accent_bar(d, WIDTH // 2, 298, 140, p=progress(t, 0.95))

    a, dy = appear(t, 1.1)
    centered_paragraph(
        d,
        WIDTH // 2,
        328 + dy,
        "Every event ends the same way: a box of bottles, badges, and chargers — "
        "and one volunteer guessing which is whose.",
        F["body"],
        900,
        MUTED,
        1.42,
        alpha=a,
    )

    a, dy = appear(t, 1.7)
    draw_text(
        d,
        (WIDTH // 2, 412 + dy),
        "What follows is the real app running real models — no mock data, no cuts.",
        F["small"],
        INK,
        anchor="ma",
        alpha=a,
    )

    steps = [
        ("1", "Snap a photo", "MiniCPM-V turns one item into a searchable record.", BLUE),
        ("2", "Describe it", "A language-aware assistant asks the question that matters.", VIOLET),
        ("3", "Staff decide", "AI shortlists privately; people hand the item back.", GREEN),
    ]
    for n, (tag, title, body, color) in enumerate(steps):
        a, dy = appear(t, 2.2 + n * 0.4)
        x = 168 + n * 378
        simple_card(img, (x, 470 + dy, x + 348, 634 + dy), title, body, color, tag, alpha=a)

    pill_row(
        d,
        WIDTH // 2,
        668,
        [
            ("MiniCPM-V 4.6 + MiniCPM5-1B", BLUE),
            ("Custom Svelte UI", VIOLET),
            ("Real demo, no mocks", GREEN),
        ],
        t=t,
        start=3.5,
    )

    # Dissolve the blurred title card into the live app's first frame.
    p = ease((t - (INTRO_SECONDS - 0.6)) / 0.6)
    if p > 0:
        img = Image.blend(img, sharp, p)
    return img


def render_outro_frame(i: int, demo_last: Image.Image) -> Image.Image:
    t = i / FPS
    img = base_background()
    d = ImageDraw.Draw(img, "RGBA")

    if t < SCENE_ENDS[0]:
        scene, local = 0, t
        a, dy = appear(local, 0.1)
        kicker(d, (WIDTH // 2, 248 + dy), "Why Build Small", VIOLET, alpha=a, anchor="ma")
        a, dy = appear(local, 0.25)
        draw_text(
            d,
            (WIDTH // 2, 286 + dy),
            "This problem honestly fits small models",
            F["h1"],
            INK,
            anchor="ma",
            alpha=a,
        )
        accent_bar(d, WIDTH // 2, 364, 140, p=progress(local, 0.55))
        a, dy = appear(local, 0.7)
        centered_paragraph(
            d,
            WIDTH // 2,
            400 + dy,
            "A return desk does not need a frontier model. It needs three narrow, "
            "repeatable jobs — each small enough to run on hardware you own.",
            F["body"],
            860,
            MUTED,
            1.42,
            alpha=a,
        )
        pill_row(
            d,
            WIDTH // 2,
            562,
            [
                ("photo -> record", BLUE),
                ("chat -> claim", VIOLET),
                ("match -> shortlist", GREEN),
            ],
            t=local,
            start=1.1,
        )

    elif t < SCENE_ENDS[1]:
        scene, local = 1, t - SCENE_ENDS[0]
        a, dy = appear(local, 0.1)
        kicker(d, (80, 134 + dy), "Architecture", VIOLET, alpha=a)
        a, dy = appear(local, 0.2)
        draw_text(d, (80, 164 + dy), "One small model, one job", F["h1"], alpha=a)
        a, dy = appear(local, 0.35)
        paragraph(
            d,
            82,
            232 + dy,
            "Every row is a real transformation from the demo you just watched.",
            F["body"],
            760,
            alpha=a,
        )
        rows = [
            ("Item photo", "MiniCPM-V 4.6", "Searchable record", "One photo per item becomes a staff-only caption in seconds.", BLUE, "V"),
            ("Claimant chat", "MiniCPM5-1B", "A sharper claim", "Asks the one question that matters — and never sees the inventory.", VIOLET, "C"),
            ("Claim + items", "Nemotron Embed 1B", "Staff-only shortlist", "Multilingual embeddings retrieve; MiniCPM5 ranks. Staff eyes only.", GREEN, "R"),
        ]
        for n, (left, model, right, body, color, tag) in enumerate(rows):
            row_start = 0.5 + n * 0.3
            a, _ = appear(local, row_start)
            y = 330 + n * 150
            active = n == min(2, int(local / 3.2))
            fill = mix(color, SURFACE, 0.9) if active else SURFACE
            outline = mix(color, SURFACE, 0.35) if active else LINE
            rounded(d, (90, y, 1350, y + 112), 20, rgba(fill, a), rgba(outline, a), 2 if active else 1)
            rounded(d, (118, y + 30, 166, y + 78), 14, rgba(mix(color, SURFACE, 0.82), a))
            draw_text(d, (142, y + 43), tag, F["body"], color, anchor="ma", alpha=a)
            draw_text(d, (198, y + 24), left, F["h2"], INK, alpha=a)
            draw_text(d, (528, y + 24), model, F["h2"], color, alpha=a)
            draw_text(d, (908, y + 24), right, F["h2"], INK, alpha=a)
            paragraph(d, 198, y + 68, body, F["small"], 780, alpha=a)
            # Arrows draw themselves across once the row has landed.
            ac = rgba(color, min(a, 210))
            for ax in (446, 840):
                ap = progress(local, row_start + 0.35, 0.45)
                ln = round(48 * ap)
                if ln > 2:
                    d.line((ax, y + 56, ax + ln, y + 56), fill=ac, width=4)
                if ap > 0.9:
                    d.polygon([(ax + 48, y + 56), (ax + 34, y + 48), (ax + 34, y + 64)], fill=ac)

    elif t < SCENE_ENDS[2]:
        scene, local = 2, t - SCENE_ENDS[1]
        a, dy = appear(local, 0.1)
        kicker(d, (80, 134 + dy), "The boundary is the product", VIOLET, alpha=a)
        a, dy = appear(local, 0.2)
        draw_text(d, (80, 164 + dy), "AI narrows. People decide.", F["h1"], alpha=a)
        a, dy = appear(local, 0.35)
        paragraph(
            d,
            82,
            232 + dy,
            "Claimants never browse the inventory. Staff review candidates privately, and every handoff is confirmed in person.",
            F["body"],
            900,
            alpha=a,
        )

        a, dy = appear(local, 0.55)
        rounded(d, (92, 320 + dy, 562, 640 + dy), 26, rgba(SURFACE, a), rgba(LINE, a))
        draw_text(d, (138, 366 + dy), "Claimant side", F["h2"], BLUE, alpha=a)
        paragraph(
            d,
            138,
            422 + dy,
            "Describe the loss in your own language, answer one useful question, and wait for the desk's reply.",
            F["body"],
            350,
            alpha=a,
        )

        a, dy = appear(local, 0.7)
        rounded(d, (878, 320 + dy, 1348, 640 + dy), 26, rgba(SURFACE, a), rgba(LINE, a))
        draw_text(d, (924, 366 + dy), "Staff side", F["h2"], GREEN, alpha=a)
        paragraph(
            d,
            924,
            422 + dy,
            "Compare the claim with candidates privately, message the claimant, and log the in-person return.",
            F["body"],
            350,
            alpha=a,
        )

        a, dy = appear(local, 0.85)
        rounded(d, (616, 300 + dy, 824, 660 + dy), 32, rgba(mix(VIOLET, SURFACE, 0.9), a), rgba(mix(VIOLET, SURFACE, 0.35), a), 2)
        draw_text(d, (720, 348 + dy), "Private", F["h2"], VIOLET, anchor="ma", alpha=a)
        draw_text(d, (720, 386 + dy), "inventory", F["h2"], VIOLET, anchor="ma", alpha=a)
        d.arc((690, 452 + dy, 750, 512 + dy), 180, 360, fill=rgba(VIOLET, min(a, 240)), width=6)
        rounded(d, (688, 498 + dy, 752, 542 + dy), 10, rgba(VIOLET, min(a, 235)))
        centered_paragraph(d, 720, 572 + dy, "Never shown to claimants", F["tiny"], 170, VIOLET, alpha=a)

        pill_row(
            d,
            WIDTH // 2,
            700,
            [
                ("Claimant report", BLUE),
                ("Staff-only match", GREEN),
                ("In-person return", GOLD),
            ],
            t=local,
            start=1.1,
        )

    else:
        scene, local = 3, t - SCENE_ENDS[2]
        a, dy = appear(local, 0.15)
        draw_text(d, (WIDTH // 2, 158 + dy), "Built small, on purpose.", F["hero"], INK, anchor="ma", alpha=a)
        accent_bar(d, WIDTH // 2, 252, 140, p=progress(local, 0.45))
        a, dy = appear(local, 0.55)
        centered_paragraph(
            d,
            WIDTH // 2,
            284 + dy,
            "Two MiniCPM models and a 1B embedder behind a hand-built Svelte UI — "
            "a complete return desk with no closed API anywhere.",
            F["body"],
            880,
            MUTED,
            1.42,
            alpha=a,
        )
        pill_row(
            d,
            WIDTH // 2,
            398,
            [
                ("MiniCPM-V 4.6", BLUE),
                ("MiniCPM5-1B", VIOLET),
                ("Nemotron Embed 1B", GREEN),
                ("Custom Svelte UI", ROSE),
            ],
            t=local,
            start=0.85,
        )

        a, dy = appear(local, 1.2)
        rounded(d, (390, 462 + dy, 1050, 576 + dy), 22, rgba(SURFACE, a), rgba(mix(GOLD, SURFACE, 0.35), a), 2)
        kicker(d, (720, 486 + dy), "Try it yourself", GOLD, alpha=a, anchor="ma")
        draw_text(
            d,
            (720, 520 + dy),
            "Event code: demo  ·  Staff password: demo-pass",
            F["body"],
            INK,
            anchor="ma",
            alpha=a,
        )

        a, dy = appear(local, 1.7)
        draw_text(
            d,
            (WIDTH // 2, 636 + dy),
            "Small models. Narrow jobs. People in control.",
            F["h1"],
            INK,
            anchor="ma",
            alpha=a,
        )

    # Fade the scene's content out just before the next scene starts.
    scene_end = SCENE_ENDS[scene]
    if scene_end < OUTRO_SECONDS:
        p = ease((t - (scene_end - SCENE_FADE)) / SCENE_FADE)
        if p > 0:
            d.rectangle((0, 0, WIDTH, HEIGHT), fill=rgba(PAPER, round(255 * p)))

    # Frame chrome stays stable across scene fades.
    header(d)
    scene_dots(d, scene)

    # Ease in from the live demo's last frame.
    if t < 0.5:
        img = Image.blend(img, demo_last, 1 - ease(t / 0.5))
    return img


def write_video(path: Path, duration: int, frame_renderer) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{WIDTH}x{HEIGHT}",
        "-r",
        str(FPS),
        "-i",
        "-",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-t",
        str(duration),
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(path),
    ]
    proc = subprocess.Popen(cmd, cwd=ROOT, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    try:
        for i in range(FPS * duration):
            proc.stdin.write(frame_renderer(i).tobytes())
    finally:
        proc.stdin.close()
    if proc.wait() != 0:
        raise SystemExit(proc.returncode)


def make_intro(tmpdir: Path) -> None:
    frame = tmpdir / "intro-source.png"
    run(["ffmpeg", "-y", "-v", "error", "-ss", "0.5", "-i", str(DEMO), "-frames:v", "1", str(frame)])
    photo, panel, sharp = intro_assets(frame)
    write_video(INTRO, INTRO_SECONDS, lambda i: render_intro_frame(i, photo, panel, sharp))


def make_outro(tmpdir: Path) -> None:
    frame = tmpdir / "outro-source.png"
    run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-sseof",
            "-0.5",
            "-i",
            str(DEMO),
            "-update",
            "1",
            "-frames:v",
            "1",
            str(frame),
        ]
    )
    demo_last = Image.open(frame).convert("RGB").resize((WIDTH, HEIGHT))
    write_video(OUTRO, OUTRO_SECONDS, lambda i: render_outro_frame(i, demo_last))


def make_final() -> None:
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(INTRO),
            "-i",
            str(DEMO),
            "-i",
            str(OUTRO),
            "-filter_complex",
            (
                "[0:v]setpts=PTS-STARTPTS[v0];"
                "[1:v]setpts=PTS-STARTPTS[v1];"
                "[2:v]setpts=PTS-STARTPTS[v2];"
                "[0:a]asetpts=PTS-STARTPTS[a0];"
                "[1:a]asetpts=PTS-STARTPTS[a1];"
                "[2:a]asetpts=PTS-STARTPTS[a2];"
                "[v0][a0][v1][a1][v2][a2]concat=n=3:v=1:a=1[v][a]"
            ),
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(FINAL),
        ]
    )


def verify(path: Path) -> None:
    run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"])


def main() -> None:
    if not DEMO.exists():
        raise SystemExit(f"Missing real-mode demo: {DEMO}")
    with TemporaryDirectory() as td:
        make_intro(Path(td))
        make_outro(Path(td))
    make_final()
    verify(INTRO)
    verify(OUTRO)
    verify(FINAL)
    print(FINAL)


if __name__ == "__main__":
    main()

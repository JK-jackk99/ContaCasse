import os

from PIL import Image, ImageDraw, ImageFont

QUI = os.path.dirname(os.path.abspath(__file__))
IMGS = os.path.join(QUI, "com.jackt.contacasse.sdPlugin", "imgs")
os.makedirs(IMGS, exist_ok=True)
FONT = "C:/Windows/Fonts/ariblk.ttf" if os.path.exists("C:/Windows/Fonts/ariblk.ttf") else "C:/Windows/Fonts/arialbd.ttf"
S = 4

ORO, ORO_SCURO, LEGNO, LEGNO_SCURO, NERO = (255, 201, 60), (196, 127, 0), (166, 94, 42), (94, 47, 18), (42, 20, 6)


def cassa(dim, monocromo=None):
    n = dim * S
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    k = n / 64.0

    def P(*xy):
        return [v * k for v in xy]

    legno = monocromo or LEGNO
    legno2 = monocromo or LEGNO_SCURO
    oro = monocromo or ORO
    bordo = monocromo or NERO
    lw = max(1, int(2.5 * k))
    d.rounded_rectangle(P(8, 30, 56, 56), radius=4 * k, fill=legno2 if not monocromo else legno, outline=bordo, width=lw)
    d.pieslice(P(8, 10, 56, 52), 180, 360, fill=legno, outline=bordo, width=lw)
    d.rectangle(P(8, 30.5, 56, 31.5), fill=bordo)
    if not monocromo:
        for x in (13, 46):
            d.rectangle(P(x, 14, x + 5, 56), fill=oro, outline=ORO_SCURO, width=max(1, int(k)))
        d.rounded_rectangle(P(26.5, 25, 37.5, 39), radius=2.5 * k, fill=oro, outline=ORO_SCURO, width=max(1, int(1.5 * k)))
        d.ellipse(P(30.2, 29.7, 33.8, 33.3), fill=(74, 42, 0))
        d.rectangle(P(31.2, 32, 32.8, 36), fill=(74, 42, 0))
    else:
        d.rounded_rectangle(P(26.5, 25, 37.5, 39), radius=2.5 * k, fill=(0, 0, 0, 0), outline=bordo, width=lw)
    return im.resize((dim, dim), Image.LANCZOS)


def tasto(scritta, colore, nome, croce=False):
    for dim, suf in ((72, ""), (144, "@2x")):
        n = dim * S
        im = Image.new("RGBA", (n, n), (20, 16, 30, 255))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((3 * S * dim / 72, 3 * S * dim / 72, n - 3 * S * dim / 72, n - 3 * S * dim / 72),
                            radius=11 * S * dim / 72, outline=colore, width=int(3 * S * dim / 72))
        c = cassa(int(dim * 0.5)).resize((int(n * 0.5), int(n * 0.5)), Image.LANCZOS)
        im.alpha_composite(c, (int(n * 0.25), int(n * 0.07)))
        if croce:
            w = int(5 * S * dim / 72)
            a, b = n * 0.3, n * 0.62
            d.line((a, n * 0.1, b + n * 0.08, n * 0.52), fill=colore, width=w)
            d.line((b + n * 0.08, n * 0.1, a, n * 0.52), fill=colore, width=w)
        f = ImageFont.truetype(FONT, int(n * (0.30 if len(scritta) <= 2 else 0.19)))
        bb = d.textbbox((0, 0), scritta, font=f)
        x = (n - (bb[2] - bb[0])) / 2 - bb[0]
        y = n * 0.93 - bb[3]
        d.text((x, y), scritta, font=f, fill=colore, stroke_width=int(n * 0.018), stroke_fill=(10, 6, 16))
        im.resize((dim, dim), Image.LANCZOS).save(os.path.join(IMGS, f"{nome}{suf}.png"))


def icona_bianca(nome, dim, segno=None):
    for d0, suf in ((dim, ""), (dim * 2, "@2x")):
        im = cassa(d0, monocromo=(255, 255, 255, 255))
        if segno:
            n = d0 * S
            big = im.resize((n, n), Image.LANCZOS)
            dr = ImageDraw.Draw(big)
            f = ImageFont.truetype(FONT, int(n * 0.42))
            dr.text((n * 0.98, n * 0.98), segno, font=f, fill=(255, 255, 255, 255), anchor="rs",
                    stroke_width=int(n * 0.05), stroke_fill=(0, 0, 0, 0))
            im = big.resize((d0, d0), Image.LANCZOS)
        im.save(os.path.join(IMGS, f"{nome}{suf}.png"))


cassa(128).save(os.path.join(IMGS, "cassa.png"))
tasto("+1", (61, 220, 132), "keyPiu")
tasto("-1", (255, 95, 109), "keyMeno")
tasto("0", (255, 201, 60), "keyContatore")


def tasto_pausa(in_pausa):
    colore = (255, 159, 28) if in_pausa else (61, 220, 132)
    nome = "keyPausa" if in_pausa else "keyAttivo"
    scritta = "PAUSA" if in_pausa else "ATTIVO"
    for dim, suf in ((72, ""), (144, "@2x")):
        n = dim * S
        im = Image.new("RGBA", (n, n), (20, 16, 30, 255))
        d = ImageDraw.Draw(im)
        u = n / 72
        d.rounded_rectangle((3 * u, 3 * u, n - 3 * u, n - 3 * u), radius=11 * u, outline=colore, width=int(3 * u))
        if in_pausa:
            d.rounded_rectangle((24 * u, 12 * u, 32 * u, 40 * u), radius=2 * u, fill=colore)
            d.rounded_rectangle((40 * u, 12 * u, 48 * u, 40 * u), radius=2 * u, fill=colore)
        else:
            d.polygon([(26 * u, 12 * u), (26 * u, 40 * u), (50 * u, 26 * u)], fill=colore)
        f = ImageFont.truetype(FONT, int(n * 0.17))
        bb = d.textbbox((0, 0), scritta, font=f)
        d.text(((n - (bb[2] - bb[0])) / 2 - bb[0], n * 0.9 - bb[3]), scritta, font=f, fill=colore,
               stroke_width=int(n * 0.015), stroke_fill=(10, 6, 16))
        im.resize((dim, dim), Image.LANCZOS).save(os.path.join(IMGS, f"{nome}{suf}.png"))


tasto_pausa(False)
tasto_pausa(True)
for d0, suf in ((20, ""), (40, "@2x")):
    n = d0 * S
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    dr.rectangle((n * 0.22, n * 0.15, n * 0.42, n * 0.85), fill=(255, 255, 255, 255))
    dr.rectangle((n * 0.58, n * 0.15, n * 0.78, n * 0.85), fill=(255, 255, 255, 255))
    im.resize((d0, d0), Image.LANCZOS).save(os.path.join(IMGS, f"actionPausa{suf}.png"))
for dim, suf in ((72, ""), (144, "@2x")):
    im = Image.new("RGBA", (dim, dim), (20, 16, 30, 255))
    c = cassa(int(dim * 0.8))
    im.alpha_composite(c, (int(dim * 0.1), int(dim * 0.1)))
    im.save(os.path.join(IMGS, f"pluginIcon{suf}.png"))
icona_bianca("categoryIcon", 28)
icona_bianca("actionContatore", 20)
icona_bianca("actionPiu", 20, "+")
icona_bianca("actionMeno", 20, "-")
print("icone in", IMGS, ":", len(os.listdir(IMGS)))

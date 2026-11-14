import json
import os
import zipfile

QUI = os.path.dirname(os.path.abspath(__file__))
CARTELLA = "com.jackt.contacasse.sdPlugin"
USCITA = os.path.join(QUI, "..", "rilascio", "ContaCasse.streamDeckPlugin")
SCARTA = ()


def main():
    radice = os.path.join(QUI, CARTELLA)
    manifest = json.load(open(os.path.join(radice, "manifest.json"), encoding="utf-8"))
    citate = [manifest["Icon"], manifest["CategoryIcon"]]
    for a in manifest["Actions"]:
        citate.append(a["Icon"])
        citate += [s["Image"] for s in a["States"]]
    mancanti = [c for c in citate if not os.path.exists(os.path.join(radice, c + ".png"))]
    if mancanti:
        raise SystemExit(f"Immagini mancanti: {mancanti}")
    os.makedirs(os.path.dirname(USCITA), exist_ok=True)
    n = 0
    with zipfile.ZipFile(USCITA, "w", zipfile.ZIP_DEFLATED) as z:
        for cartella, _, file in os.walk(radice):
            for f in sorted(file):
                if f.startswith(SCARTA):
                    continue
                p = os.path.join(cartella, f)
                z.write(p, os.path.join(CARTELLA, os.path.relpath(p, radice)).replace("\\", "/"))
                n += 1
    print(f"Fatto: {os.path.abspath(USCITA)} (versione {manifest['Version']}, {n} file, "
          f"{os.path.getsize(USCITA) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()

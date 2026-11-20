import asyncio
import re
import threading
import time
from collections import deque

import cv2
import numpy as np

FPS = 10
FINESTRA_APERTURA = 2.5
SPARITA_PER = 0.3
PAUSA = 1.0
VERDE_MUNIZIONI = 0.25
ORO_MINIMO = 0.15
NERO_PER = 3.0
PAROLA = "ESAMINA"


def colori(img):
    if img is None or img.size == 0:
        return 0.0, 0.0
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    verde = (h >= 18) & (h <= 87) & (s >= 45) & (s <= 190) & (v >= 35) & (v <= 150)
    oro = (h >= 8) & (h <= 35) & (s >= 170) & (v >= 100)
    return float(verde.mean()), float(oro.mean())


def e_munizioni(verde, oro, cfg=None):
    cfg = cfg or {}
    return verde >= float(cfg.get("verde_munizioni", VERDE_MUNIZIONI)) and oro < float(cfg.get("oro_minimo", ORO_MINIMO))


def nero_su_bianco(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return cv2.cvtColor(np.where(g >= 185, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)


def simile(parola, cercata):
    if cercata in parola:
        return True
    if abs(len(parola) - len(cercata)) > 1:
        return False
    a, b = (parola, cercata) if len(parola) <= len(cercata) else (cercata, parola)
    diversi = 0
    i = j = 0
    while i < len(a) and j < len(b):
        if a[i] != b[j]:
            diversi += 1
            if diversi > 1:
                return False
            if len(a) < len(b):
                j += 1
                continue
        i += 1
        j += 1
    return diversi + (len(b) - j) <= 1


PACCHETTI_OCR = ["winrt-runtime", "winrt-Windows.Foundation", "winrt-Windows.Foundation.Collections",
                 "winrt-Windows.Globalization", "winrt-Windows.Graphics.Imaging", "winrt-Windows.Media.Ocr",
                 "winrt-Windows.Security.Cryptography", "winrt-Windows.Storage.Streams"]


def installa_ocr():
    import importlib
    import subprocess
    import sys
    if getattr(sys, "frozen", False):
        return False
    print("Installo la lettura del testo di Windows (solo la prima volta)...", flush=True)
    utente = ["--user"] if sys.prefix == sys.base_prefix else []
    r = subprocess.run([sys.executable, "-m", "pip", "install", *utente, "--disable-pip-version-check", *PACCHETTI_OCR])
    importlib.invalidate_caches()
    import site
    if site.ENABLE_USER_SITE and site.getusersitepackages() not in sys.path:
        sys.path.append(site.getusersitepackages())
    return r.returncode == 0


class Lettore:
    def __init__(self):
        self.motore = None
        self.errore = None
        try:
            try:
                from winrt.windows.media.ocr import OcrEngine
            except ImportError:
                if not installa_ocr():
                    raise
                from winrt.windows.media.ocr import OcrEngine
            self.motore = OcrEngine.try_create_from_user_profile_languages()
            if self.motore is None:
                langs = list(OcrEngine.available_recognizer_languages)
                if langs:
                    self.motore = OcrEngine.try_create_from_language(langs[0])
            if self.motore is None:
                self.errore = "Windows non ha una lingua con la lettura del testo (OCR) installata"
        except Exception as e:
            self.errore = f"lettura del testo di Windows non disponibile ({e})"

    def leggi(self, img):
        from winrt.windows.graphics.imaging import BitmapAlphaMode, BitmapPixelFormat, SoftwareBitmap
        from winrt.windows.security.cryptography import CryptographicBuffer
        bgra = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
        h, w = bgra.shape[:2]
        buf = CryptographicBuffer.create_from_byte_array(bgra.tobytes())
        bmp = SoftwareBitmap.create_copy_from_buffer(buf, BitmapPixelFormat.BGRA8, w, h, BitmapAlphaMode.PREMULTIPLIED)

        async def vai():
            return await self.motore.recognize_async(bmp)
        risultato = asyncio.run(vai())
        parole = []
        for riga in risultato.lines:
            for p in riga.words:
                r = p.bounding_rect
                parole.append((p.text, (int(r.x), int(r.y), int(r.width), int(r.height))))
        return parole


def uscite():
    try:
        import dxcam
        testo = dxcam.output_info()
    except Exception:
        testo = ""
    lista = []
    for riga in testo.splitlines():
        m = re.search(r"Device\[(\d+)\]\s*Output\[(\d+)\]:\s*Res:\((\d+),\s*(\d+)\).*Primary:\s*(\w+)", riga)
        if m:
            lista.append({"scheda": int(m.group(1)), "uscita": int(m.group(2)), "w": int(m.group(3)),
                          "h": int(m.group(4)), "principale": m.group(5) == "True"})
    lista.sort(key=lambda u: (not u["principale"], u["scheda"], u["uscita"]))
    return lista


class Cattura:
    def __init__(self, monitor):
        self.monitor = monitor
        self.cam = None
        self.sct = None
        self.ultimo = {}
        lista = uscite()
        self.uscita = lista[monitor] if 0 <= monitor < len(lista) else (lista[0] if lista else None)
        try:
            import dxcam
            if self.uscita:
                self.cam = dxcam.create(device_idx=self.uscita["scheda"], output_idx=self.uscita["uscita"],
                                        output_color="BGR")
            else:
                self.cam = dxcam.create(output_color="BGR")
            if self.cam is None:
                raise RuntimeError("dxcam non ha dato lo schermo")
        except Exception:
            self.cam = None

    def chiudi(self):
        try:
            if self.cam is not None:
                self.cam.release()
            if self.sct is not None:
                self.sct.close()
        except Exception:
            pass

    def grab(self, regione=None):
        if self.cam is None:
            return self._grab_mss(regione)
        r = None if regione is None else (regione[0], regione[1], regione[0] + regione[2], regione[1] + regione[3])
        for _ in range(10):
            f = self.cam.grab(region=r)
            if f is not None:
                self.ultimo[regione] = f
                return f
            if regione in self.ultimo:
                return self.ultimo[regione]
            time.sleep(0.02)
        try:
            f = self._grab_mss(regione)
            self.ultimo[regione] = f
            return f
        except Exception:
            return None

    def _grab_mss(self, regione):
        if self.sct is None:
            import mss
            self.sct = mss.MSS() if hasattr(mss, "MSS") else mss.mss()
        m = self._monitor_mss()
        if regione is None:
            box = m
        else:
            box = {"left": m["left"] + regione[0], "top": m["top"] + regione[1],
                   "width": regione[2], "height": regione[3]}
        return np.array(self.sct.grab(box))[:, :, :3]

    def _monitor_mss(self):
        monitori = self.sct.monitors[1:] or self.sct.monitors
        u = self.uscita
        if u:
            for m in monitori:
                if m["width"] == u["w"] and m["height"] == u["h"] and bool(m.get("is_primary")) == u["principale"]:
                    return m
            for m in monitori:
                if m["width"] == u["w"] and m["height"] == u["h"]:
                    return m
        for m in monitori:
            if m.get("is_primary"):
                return m
        return monitori[min(self.monitor, len(monitori) - 1)]

    @staticmethod
    def schermi():
        lista = uscite()
        if not lista:
            return ["principale"]
        piu_schede = len({u["scheda"] for u in lista}) > 1
        return [f"{u['w']}x{u['h']}" + (" (principale)" if u["principale"] else "")
                + (f" - scheda video {u['scheda'] + 1}" if piu_schede else "") for u in lista]


class Occhio:
    def __init__(self, app):
        self.app = app
        self.lettore = Lettore()
        self.schermo = None
        self.cattura = None
        self.errore = None
        self.attivo = False
        self.visto = None
        self.parole_viste = []
        self.visibile = False
        self.ultimo_visibile = 0.0
        self.sparita_da = 0.0
        self.attesa = None
        self.bloccato_fino = 0.0
        self.ultimo_evento = 0.0
        self.avviso_nero = 0.0
        self.nero_da = 0.0
        self.verde = 0.0
        self.oro = 0.0
        self.storia_colori = deque(maxlen=200)
        self.giro = 0
        self.trovata_prima = False

    def parola(self):
        return str(self.app.config.get("parola", PAROLA)).upper().replace(" ", "") or PAROLA

    def tasto_premuto(self, t):
        if t - self.ultimo_visibile <= 0.4:
            self.attesa = t

    def _zona(self):
        W, H = self.schermo or (2560, 1440)
        x0, x1 = int(W / 2 - 0.08 * W), int(W / 2 + 0.33 * W)
        y0, y1 = int(H / 2 - 0.32 * H), int(H / 2 + 0.22 * H)
        return max(0, x0), max(0, y0), min(W, x1) - max(0, x0), min(H, y1) - max(0, y0)

    def _mirino(self):
        W, H = self.schermo or (2560, 1440)
        r = max(20, int(60 * H / 1440))
        return W // 2 - r, H // 2 - r, 2 * r, 2 * r

    def avvia(self):
        threading.Thread(target=self._ciclo, daemon=True, name="schermo").start()

    def riavvia(self):
        self.errore = "riavvio"

    def _ciclo(self):
        while True:
            try:
                self._guarda()
            except Exception as e:
                self.attivo = False
                if str(e) != self.errore:
                    self.app.scrivi(f"Schermo: {e}", "errore")
                self.errore = str(e)
                if self.cattura is not None:
                    self.cattura.chiudi()
                    self.cattura = None
                time.sleep(2)

    def _guarda(self):
        if self.lettore.motore is None:
            raise RuntimeError(self.lettore.errore or "lettura del testo non disponibile")
        monitor = int(self.app.config.get("monitor", 0))
        self.cattura = Cattura(monitor)
        intero = self.cattura.grab(None)
        if intero is None:
            raise RuntimeError("non riesco a vedere lo schermo")
        H, W = intero.shape[:2]
        self.schermo = (W, H)
        self.errore = None
        self.attivo = True
        self.app.scrivi(f"Guardo lo schermo {monitor + 1} ({W}x{H}) e cerco la scritta {self.parola()}")
        self.app.pubblica_stato()
        while True:
            t0 = time.time()
            cfg = self.app.config
            if self.errore == "riavvio" or int(cfg.get("monitor", 0)) != monitor:
                self.errore = None
                self.cattura.chiudi()
                self.cattura = None
                return
            if cfg.get("usa_schermo", True):
                self._un_giro(t0, cfg)
            time.sleep(max(0.0, 1.0 / FPS - (time.time() - t0)))

    def _un_giro(self, adesso, cfg):
        X, Y, Wz, Hz = self._zona()
        zona = self.cattura.grab((X, Y, Wz, Hz))
        if zona is None:
            return
        self.visto = zona
        mx, my, mw, mh = self._mirino()
        self.verde, self.oro = colori(zona[my - Y:my - Y + mh, mx - X:mx - X + mw])
        self.storia_colori.append((adesso, self.verde, self.oro))
        self._controlla_nero(zona, adesso)
        H = self.schermo[1]
        k = 1.0 if H >= 1300 else 1300 / H
        immagine = zona if k == 1.0 else cv2.resize(zona, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC)
        cercata = self.parola()
        self.giro += 1
        prepara = nero_su_bianco if self.giro % 2 else (lambda x: x)
        parole = self.lettore.leggi(prepara(immagine))
        self.parole_viste = [(t, tuple(int(v / k) for v in r), simile(re.sub(r"[^A-Z]", "", t.upper()), cercata))
                             for t, r in parole]
        trovata = any(s for _, _, s in self.parole_viste)
        ora_visibile = trovata or self.trovata_prima
        self.trovata_prima = trovata
        if ora_visibile:
            self.ultimo_visibile = adesso
            self.sparita_da = 0.0
        elif self.visibile:
            self.sparita_da = adesso
        self.visibile = ora_visibile

        a = self.attesa
        if a is not None:
            sparita = (not ora_visibile and self.sparita_da and self.sparita_da >= a - 0.1
                       and adesso - self.sparita_da >= SPARITA_PER)
            if sparita and adesso - a <= FINESTRA_APERTURA + SPARITA_PER:
                self.attesa = None
                valori = [(v, o) for (t, v, o) in self.storia_colori if a - 0.5 <= t <= a + 0.2]
                if valori:
                    verde, oro = (float(x) for x in np.median(np.array(valori), axis=0))
                else:
                    verde, oro = self.verde, self.oro
                if e_munizioni(verde, oro, cfg):
                    self.app.scrivi(f"Verde sotto il mirino (verde {verde:.2f}): cassetta di munizioni, non conto")
                elif cfg.get("automatico", True) and adesso >= self.bloccato_fino:
                    self.bloccato_fino = adesso + PAUSA
                    self.app.cambia("piu", motivo=f"Cassa aperta (verde {verde:.2f}, oro {oro:.2f})")
            elif adesso - a > FINESTRA_APERTURA + SPARITA_PER:
                self.attesa = None
                if ora_visibile:
                    self.app.scrivi(f"E sulla cassa ma {cercata} e' rimasta: non aperta, non conto")

        if adesso - self.ultimo_evento >= 0.1:
            self.ultimo_evento = adesso
            self.app.bacheca.pubblica("schermo", {"vis": self.visibile, "parola": cercata,
                                                  "lette": [t for t, _, _ in self.parole_viste][:6],
                                                  "verde": round(self.verde, 2), "oro": round(self.oro, 2),
                                                  "munizioni": e_munizioni(self.verde, self.oro, self.app.config)},
                                      solo_pannello=True)

    def _controlla_nero(self, zona, adesso):
        if int(zona.max()) >= 20:
            self.nero_da = 0.0
            return
        if not self.nero_da:
            self.nero_da = adesso
            return
        if adesso - self.nero_da < NERO_PER:
            return
        self.nero_da = adesso
        if getattr(self.cattura, "cam", None) is not None:
            try:
                self.cattura.cam.release()
            except Exception:
                pass
            self.cattura.cam = None
            self.cattura.ultimo = {}
            self.app.scrivi("La cattura veloce mi da' lo schermo nero: passo a quella compatibile", "avviso")
        elif adesso - self.avviso_nero > 60:
            self.avviso_nero = adesso
            self.app.scrivi("Vedo lo schermo NERO: in Fortnite metti Modalita' finestra 'Schermo intero in "
                            "finestra', oppure scegli l'altro schermo nelle Impostazioni avanzate", "errore")

    def immagine_visto(self):
        z = self.visto
        if z is None:
            return None
        img = z.copy()
        X, Y, _, _ = self._zona()
        for testo, (x, y, w, h), giusta in self.parole_viste:
            col = (80, 220, 60) if giusta else (120, 120, 120)
            cv2.rectangle(img, (x, y), (x + w, y + h), col, 2 if giusta else 1)
        mx, my, mw, mh = self._mirino()
        no = e_munizioni(self.verde, self.oro, self.app.config)
        col = (200, 80, 200) if no else (40, 200, 255)
        cv2.rectangle(img, (mx - X, my - Y), (mx - X + mw, my - Y + mh), col, 2)
        cv2.putText(img, f"verde {self.verde:.2f}" + (" NO" if no else ""), (mx - X + 4, my - Y + mh - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, col, 1)
        return img

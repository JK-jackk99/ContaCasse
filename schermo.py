import json
import os
import threading
import time
from collections import deque

import cv2
import numpy as np

FPS = 20
FINESTRA_APERTURA = 2.5
SPARITA_PER = 0.2
PAUSA = 1.0
VERDE_MUNIZIONI = 0.25
ORO_MINIMO = 0.15
ALTEZZA_BASE = 1440


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


def prepara(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return cv2.GaussianBlur(np.where(g >= 200, 255, 0).astype(np.uint8), (3, 3), 0)


class Cattura:
    def __init__(self, monitor):
        self.monitor = monitor
        self.cam = None
        self.sct = None
        self.ultimo = {}
        try:
            import dxcam
            self.cam = dxcam.create(output_idx=monitor, output_color="BGR")
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
        m = self.sct.monitors[min(self.monitor + 1, len(self.sct.monitors) - 1)]
        if regione is None:
            box = m
        else:
            box = {"left": m["left"] + regione[0], "top": m["top"] + regione[1],
                   "width": regione[2], "height": regione[3]}
        return np.array(self.sct.grab(box))[:, :, :3]

    @staticmethod
    def schermi():
        try:
            import dxcam
            righe = [r for r in dxcam.output_info().splitlines() if "Output[" in r]
            return [r.split("Output")[1].strip() for r in righe] or ["[0]"]
        except Exception:
            return ["[0]"]


class Occhio:
    def __init__(self, app, cartella, scritta_base):
        self.app = app
        self.dir_modelli = os.path.join(cartella, "modelli")
        os.makedirs(self.dir_modelli, exist_ok=True)
        self.file_modelli = os.path.join(cartella, "modelli.json")
        self.base = cv2.imread(scritta_base, cv2.IMREAD_COLOR) if scritta_base else None
        self.schermo = None
        self.modelli = []
        self.attivi = []
        self.carica()
        self.cattura = None
        self.errore = None
        self.attivo = False
        self.richiesta_foto = None
        self.foto = None
        self.visto = None
        self.punteggio = 0.0
        self.visibile = False
        self.ultimo_visibile = 0.0
        self.sparita_da = 0.0
        self.attesa = None
        self.bloccato_fino = 0.0
        self.ultimo_evento = 0.0
        self.picco = 0.0
        self.avviso_nero = 0.0
        self.verde = 0.0
        self.oro = 0.0
        self.storia_colori = deque(maxlen=200)

    def carica(self):
        try:
            with open(self.file_modelli, "r", encoding="utf-8-sig") as f:
                lista = json.load(f)
        except Exception:
            lista = []
        modelli = []
        for m in lista:
            img = cv2.imread(os.path.join(self.dir_modelli, "colore-" + m["file"]), cv2.IMREAD_COLOR)
            if img is not None:
                m = dict(m)
                m["img"] = prepara(img)
                modelli.append(m)
        self.modelli = modelli
        self._scegli_attivi()

    def _modello_base(self, W, H):
        s = H / ALTEZZA_BASE
        img = cv2.resize(self.base, None, fx=s, fy=s, interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
        x0, y0 = int(W / 2 - 190 * s), int(H / 2 - 350 * s)
        w, h = int(810 * s), int(680 * s)
        x0, y0 = max(0, x0), max(0, y0)
        return {"file": "base", "nome": "E ESAMINA", "base": True, "w": img.shape[1], "h": img.shape[0],
                "cerca": [x0, y0, min(w, W - x0), min(h, H - y0)], "schermo": [W, H],
                "monitor": self.app.config.get("monitor", 0), "img": prepara(img)}

    def _scegli_attivi(self):
        if not self.schermo:
            self.attivi = []
            return
        W, H = self.schermo
        attivi = [m for m in self.modelli if m.get("schermo") == [W, H]]
        if self.base is not None:
            attivi.insert(0, self._modello_base(W, H))
        self.attivi = attivi

    def salva_elenco(self):
        dati = [{k: v for k, v in m.items() if k != "img"} for m in self.modelli]
        tmp = self.file_modelli + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dati, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.file_modelli)

    def pubblici(self):
        return [{k: v for k, v in m.items() if k != "img"} for m in self.attivi]

    def aggiungi_modello(self, x, y, w, h, nome):
        if self.foto is None:
            raise RuntimeError("prima cattura lo schermo")
        H, W = self.foto.shape[:2]
        x, y = max(0, int(x)), max(0, int(y))
        w, h = min(int(w), W - x), min(int(h), H - y)
        if w < 12 or h < 8:
            raise ValueError("il riquadro e' troppo piccolo")
        if w > 0.3 * W or h > 0.15 * H:
            raise ValueError("il riquadro e' troppo grande: ritaglia SOLO la scritta (il rettangolo scuro "
                             "con la E e la parola), NON la cassa")
        ritaglio = self.foto[y:y + h, x:x + w]
        if int((prepara(ritaglio) > 128).sum()) < 30:
            raise ValueError("nel riquadro non c'e' testo bianco: ritaglia la scritta con la E")
        mx, my = max(300, w), max(300, 3 * h)
        cx, cy = max(0, x - mx), max(0, y - my)
        cw, ch = min(W - cx, w + 2 * mx), min(H - cy, h + 2 * my)
        file = time.strftime("%Y%m%d-%H%M%S") + ".png"
        cv2.imwrite(os.path.join(self.dir_modelli, file), prepara(ritaglio))
        cv2.imwrite(os.path.join(self.dir_modelli, "colore-" + file), ritaglio)
        m = {"file": file, "nome": (nome or "Scritta").strip()[:40], "x": x, "y": y, "w": w, "h": h,
             "cerca": [cx, cy, cw, ch], "monitor": self.app.config.get("monitor", 0),
             "schermo": [W, H], "img": prepara(ritaglio)}
        self.modelli.append(m)
        self.salva_elenco()
        self._scegli_attivi()
        return m

    def elimina_modello(self, file):
        if file == "base":
            raise ValueError("la scritta di base non si puo' togliere")
        self.modelli = [m for m in self.modelli if m["file"] != file]
        for f in (file, "colore-" + file):
            p = os.path.join(self.dir_modelli, os.path.basename(f))
            if os.path.exists(p):
                os.remove(p)
        self.salva_elenco()
        self._scegli_attivi()

    def fai_foto(self, ritardo):
        ev = threading.Event()
        self.richiesta_foto = (time.time() + ritardo, ev)
        return ev

    def modello_png(self, file):
        if file == "base":
            return self.base
        p = os.path.join(self.dir_modelli, "colore-" + os.path.basename(file))
        return cv2.imread(p, cv2.IMREAD_COLOR) if os.path.isfile(p) else None

    def tasto_premuto(self, t):
        if t - self.ultimo_visibile <= 0.25 and self.attivi:
            self.attesa = t

    def _mirino(self):
        W, H = self.schermo or (2560, 1440)
        r = max(20, int(60 * H / ALTEZZA_BASE))
        return W // 2 - r, H // 2 - r, 2 * r, 2 * r

    def _zona_totale(self):
        ox, oy, ow, oh = self._mirino()
        X = min([m["cerca"][0] for m in self.attivi] + [ox])
        Y = min([m["cerca"][1] for m in self.attivi] + [oy])
        X2 = max([m["cerca"][0] + m["cerca"][2] for m in self.attivi] + [ox + ow])
        Y2 = max([m["cerca"][1] + m["cerca"][3] for m in self.attivi] + [oy + oh])
        return X, Y, X2, Y2

    def _colori(self, zona, X, Y):
        mx, my, mw, mh = self._mirino()
        return colori(zona[my - Y:my - Y + mh, mx - X:mx - X + mw])

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
        monitor = int(self.app.config.get("monitor", 0))
        self.cattura = Cattura(monitor)
        intero = self.cattura.grab(None)
        if intero is None:
            raise RuntimeError("non riesco a vedere lo schermo")
        H, W = intero.shape[:2]
        self.schermo = (W, H)
        self._scegli_attivi()
        self.errore = None
        self.attivo = True
        self.app.scrivi(f"Guardo lo schermo {monitor + 1} ({W}x{H})")
        self.app.pubblica_stato()
        while True:
            t0 = time.time()
            cfg = self.app.config
            if self.errore == "riavvio" or int(cfg.get("monitor", 0)) != monitor:
                self.errore = None
                self.cattura.chiudi()
                self.cattura = None
                return
            r = self.richiesta_foto
            if r is not None and t0 >= r[0]:
                self.richiesta_foto = None
                f = self.cattura.grab(None)
                self.foto = None if f is None else f.copy()
                if self.foto is not None and float(self.foto.mean()) < 3:
                    self.app.scrivi("Lo schermo catturato e' NERO: in Fortnite metti Modalita' finestra "
                                    "'Schermo intero in finestra' (o prova l'altro schermo)", "errore")
                r[1].set()
            if cfg.get("usa_schermo", True) and self.attivi:
                self._un_giro(t0, cfg)
            time.sleep(max(0.0, 1.0 / FPS - (time.time() - t0)))

    def _un_giro(self, adesso, cfg):
        X, Y, X2, Y2 = self._zona_totale()
        zona = self.cattura.grab((X, Y, X2 - X, Y2 - Y))
        if zona is None:
            return
        self.visto = zona
        self.verde, self.oro = self._colori(zona, X, Y)
        grigio = prepara(zona)
        if float(grigio.mean()) < 2 and adesso - self.avviso_nero > 30:
            self.avviso_nero = adesso
            self.app.scrivi("La zona dello schermo che guardo e' nera: Fortnite in schermo intero esclusivo? "
                            "Metti 'Schermo intero in finestra'", "avviso")
        migliore = 0.0
        for m in self.attivi:
            cx, cy, cw, ch = m["cerca"]
            pezzo = grigio[cy - Y:cy - Y + ch, cx - X:cx - X + cw]
            t = m["img"]
            if pezzo.shape[0] < t.shape[0] or pezzo.shape[1] < t.shape[1]:
                continue
            migliore = max(migliore, float(cv2.matchTemplate(pezzo, t, cv2.TM_CCOEFF_NORMED).max()))
        self.punteggio = migliore
        self.picco = max(self.picco, migliore)
        ora_visibile = migliore >= float(cfg.get("soglia_schermo", 0.8))
        if ora_visibile:
            self.storia_colori.append((adesso, self.verde, self.oro))
            self.ultimo_visibile = adesso
            self.sparita_da = 0.0
        elif self.visibile:
            self.sparita_da = adesso
        self.visibile = ora_visibile

        a = self.attesa
        if a is not None:
            sparita = (not ora_visibile and self.sparita_da and self.sparita_da >= a - 0.05
                       and adesso - self.sparita_da >= SPARITA_PER)
            if sparita and adesso - a <= FINESTRA_APERTURA + SPARITA_PER:
                self.attesa = None
                valori = [(v, o) for (t, v, o) in self.storia_colori if t >= a - 0.5]
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
                    self.app.scrivi("E sulla cassa ma la scritta e' rimasta: non aperta, non conto")

        if adesso - self.ultimo_evento >= 0.1:
            self.ultimo_evento = adesso
            self.app.bacheca.pubblica("schermo", {"s": round(self.picco, 3), "vis": self.visibile,
                                                  "verde": round(self.verde, 2), "oro": round(self.oro, 2),
                                                  "munizioni": e_munizioni(self.verde, self.oro, self.app.config)},
                                      solo_pannello=True)
            self.picco = 0.0

    def immagine_visto(self):
        z = self.visto
        if z is None or not self.attivi:
            return None
        img = z.copy()
        X, Y, X2, Y2 = self._zona_totale()
        if img.shape[1] < X2 - X or img.shape[0] < Y2 - Y:
            return img
        g = prepara(z)
        soglia = float(self.app.config.get("soglia_schermo", 0.8))
        for m in self.attivi:
            cx, cy, cw, ch = m["cerca"]
            cv2.rectangle(img, (cx - X, cy - Y), (cx - X + cw - 1, cy - Y + ch - 1), (90, 90, 90), 1)
            pezzo = g[cy - Y:cy - Y + ch, cx - X:cx - X + cw]
            t = m["img"]
            if pezzo.shape[0] >= t.shape[0] and pezzo.shape[1] >= t.shape[1]:
                _, v, _, (px, py) = cv2.minMaxLoc(cv2.matchTemplate(pezzo, t, cv2.TM_CCOEFF_NORMED))
                col = (80, 220, 60) if v >= soglia else (60, 60, 230)
                cv2.rectangle(img, (cx - X + px, cy - Y + py), (cx - X + px + t.shape[1], cy - Y + py + t.shape[0]),
                              col, 2)
                cv2.putText(img, f"{v:.2f}", (cx - X + px, max(12, cy - Y + py - 4)), cv2.FONT_HERSHEY_SIMPLEX,
                            0.5, col, 1)
        mx, my, mw, mh = self._mirino()
        vv, oo = self._colori(z, X, Y)
        no = e_munizioni(vv, oo, self.app.config)
        col = (200, 80, 200) if no else (40, 200, 255)
        cv2.rectangle(img, (mx - X, my - Y), (mx - X + mw, my - Y + mh), col, 2)
        cv2.putText(img, f"verde {vv:.2f}" + (" NO" if no else ""), (mx - X + 4, my - Y + mh - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, col, 1)
        return img

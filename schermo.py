import json
import os
import re
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
FATTORI_HUD = (0.7, 0.8, 0.9, 1.0, 1.1, 1.2)
NERO_PER = 3.0


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


def trova_scritta(frame):
    H, W = frame.shape[:2]
    cx, cy = W // 2, H // 2
    x0, x1 = max(0, cx - int(0.03 * W)), min(W, cx + int(0.28 * W))
    y0, y1 = max(0, cy - int(0.30 * H)), min(H, cy + int(0.18 * H))
    g = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    bianco = (g >= 200).astype(np.uint8)
    u = H / 1440.0
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (max(3, int(14 * u)), max(1, int(3 * u))))
    n, _, st, _ = cv2.connectedComponentsWithStats(cv2.dilate(bianco, k), 8)
    cand = []
    for i in range(1, n):
        x, y, w, h, _ = st[i]
        if not (9 * u <= h <= 30 * u and 14 * u <= w <= 0.25 * W):
            continue
        if not (0.10 <= bianco[y:y + h, x:x + w].mean() <= 0.65):
            continue
        sotto = g[y:y + h, x:x + w][bianco[y:y + h, x:x + w] == 0]
        m = int(0.6 * h)
        X0, Y0 = max(0, x - m), max(0, y - m)
        cornice = g[Y0:y + h + m, X0:x + w + m][bianco[Y0:y + h + m, X0:x + w + m] == 0]
        if sotto.size == 0 or np.median(sotto) > 95 or np.median(cornice) > 100:
            continue
        cand.append([x, y, w, h])
    cand.sort(key=lambda b: b[0])
    gruppi = []
    for b in cand:
        for gr in gruppi:
            gx, gy, gw, gh = gr
            sovr = min(gy + gh, b[1] + b[3]) - max(gy, b[1])
            if sovr > 0.5 * min(gh, b[3]) and b[0] - (gx + gw) < 4 * max(gh, b[3]):
                nx, ny = min(gx, b[0]), min(gy, b[1])
                gr[:] = [nx, ny, max(gx + gw, b[0] + b[2]) - nx, max(gy + gh, b[1] + b[3]) - ny]
                break
        else:
            gruppi.append(list(b))
    gruppi = [b for b in gruppi if b[2] >= 3 * b[3] and b[2] >= 50 * u and x0 + b[0] >= cx - 0.02 * W]
    if not gruppi:
        return None

    def dist(b):
        return ((x0 + b[0] + b[2] / 2 - cx) ** 2 + (y0 + b[1] + b[3] / 2 - cy) ** 2) ** 0.5
    x, y, w, h = min(gruppi, key=lambda b: (-min(b[2], 12 * b[3]), dist(b)))
    m = int(0.35 * h)
    return (max(0, x0 + x - m), max(0, y0 + y - m), w + 2 * m, h + 2 * m)


def somiglianza_scritte(a, b):
    grande = cv2.copyMakeBorder(a, 40, 40, 80, 80, cv2.BORDER_CONSTANT, value=0)
    if grande.shape[0] < b.shape[0] or grande.shape[1] < b.shape[1]:
        return 0.0
    return float(cv2.minMaxLoc(cv2.matchTemplate(grande, b, cv2.TM_CCOEFF_NORMED))[1])


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
        self.nero_da = 0.0
        self.varianti = []
        self.giro = 0
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

    def _variante(self, s):
        return prepara(cv2.resize(self.base, None, fx=s, fy=s, interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC))

    def _modello_base(self, W, H):
        s = H / ALTEZZA_BASE
        self.varianti = [(f, self._variante(s * f)) for f in FATTORI_HUD]
        scelta = float(self.app.config.get("scala_hud", 1.0))
        img = dict(self.varianti).get(scelta, self.varianti[FATTORI_HUD.index(1.0)][1])
        g = s * max(FATTORI_HUD)
        x0, y0 = int(W / 2 - 190 * g), int(H / 2 - 350 * g)
        w, h = int(810 * g), int(680 * g)
        x0, y0 = max(0, x0), max(0, y0)
        return {"file": "base", "nome": "E ESAMINA", "base": True, "w": img.shape[1], "h": img.shape[0],
                "cerca": [x0, y0, min(w, W - x0), min(h, H - y0)], "schermo": [W, H],
                "monitor": self.app.config.get("monitor", 0), "img": img}

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

    def configura(self, ritardo=0.0):
        if not self.fai_foto(ritardo).wait(ritardo + 5) or self.foto is None:
            raise RuntimeError("lo schermo non si riesce a catturare")
        r = trova_scritta(self.foto)
        if r is None:
            raise ValueError("non vedo la scritta per aprire la cassa: mira una cassa finche' compare e riprova")
        x, y, w, h = r
        nuova = prepara(self.foto[y:y + h, x:x + w])
        for m in self.attivi:
            if somiglianza_scritte(nuova, m["img"]) >= 0.9:
                return m, True
        return self.aggiungi_modello(x, y, w, h, "Scritta imparata"), False

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
        self._controlla_nero(zona, adesso)
        grigio = prepara(zona)
        soglia = float(cfg.get("soglia_schermo", 0.8))
        migliore = 0.0
        self.giro += 1
        for m in self.attivi:
            cx, cy, cw, ch = m["cerca"]
            pezzo = grigio[cy - Y:cy - Y + ch, cx - X:cx - X + cw]
            v = self._confronta(pezzo, m["img"])
            if m.get("base") and self.varianti:
                f, altra = self.varianti[self.giro % len(self.varianti)]
                if altra.shape != m["img"].shape:
                    v2 = self._confronta(pezzo, altra)
                    if v2 >= soglia and v2 > v + 0.03:
                        m["img"], m["w"], m["h"] = altra, altra.shape[1], altra.shape[0]
                        self.app.aggiorna_config({"scala_hud": f})
                        self.app.scrivi(f"La scritta sul tuo schermo e' al {int(f * 100)}%: mi adatto")
                        v = v2
            migliore = max(migliore, v)
        self.punteggio = migliore
        self.picco = max(self.picco, migliore)
        ora_visibile = migliore >= soglia
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

    @staticmethod
    def _confronta(pezzo, t):
        if pezzo.shape[0] < t.shape[0] or pezzo.shape[1] < t.shape[1]:
            return 0.0
        return float(cv2.matchTemplate(pezzo, t, cv2.TM_CCOEFF_NORMED).max())

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

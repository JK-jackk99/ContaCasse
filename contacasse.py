import ctypes
import json
import os
import queue
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import schermo

VERSIONE = "1.0.1"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

if getattr(sys, "frozen", False):
    RISORSE = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    QUI = os.path.dirname(os.path.abspath(sys.executable))
else:
    RISORSE = QUI = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(RISORSE, "web")
SCRITTA_BASE = os.path.join(RISORSE, "base", "esamina.png")
DATI = os.path.join(QUI, "dati")
SCHERMO = os.path.join(DATI, "schermo")
FILE_CONFIG = os.path.join(DATI, "config.json")
FILE_STATO = os.path.join(DATI, "stato.json")
FILE_TESTO = os.path.join(DATI, "contatore.txt")
PORTA = 8787

DISCORD = "https://discord.gg/NjnRuPt3hn"
CANALI = [
    {"id": "tw-jackk99", "piattaforma": "twitch", "utente": "jackk99", "nome": "jackk99",
     "url": "https://www.twitch.tv/jackk99"},
    {"id": "tw-hatehim_", "piattaforma": "twitch", "utente": "hatehim_", "nome": "hatehim_",
     "url": "https://www.twitch.tv/hatehim_"},
    {"id": "tt-jackk99.tv", "piattaforma": "tiktok", "utente": "jackk99.tv", "nome": "@jackk99.tv",
     "url": "https://www.tiktok.com/@jackk99.tv"},
    {"id": "tt-hatehim_x", "piattaforma": "tiktok", "utente": "hatehim_x", "nome": "@hatehim_x",
     "url": "https://www.tiktok.com/@hatehim_x"},
]
OGNI_QUANTO_LIVE = 600

CTRL, ALT, MAIUSC, WIN = 0x11, 0x12, 0x10, 0x5B
MODIFICATORI = (CTRL, ALT, MAIUSC, WIN)

AZIONI = {
    "piu": ("+1 cassa", [CTRL, ALT, 0x26]),
    "meno": ("-1 cassa", [CTRL, ALT, 0x28]),
    "pausa": ("Pausa / riprendi", [CTRL, ALT, 0x50]),
}

CONFIG_BASE = {
    "automatico": True,
    "usa_schermo": True,
    "soglia_schermo": 0.8,
    "monitor": 0,
    "tasto": 0x45,
    "nome_tasto": "E",
    "tasti": {a: v[1] for a, v in AZIONI.items()},
    "scorciatoie": True,
}


def scrivi_json(percorso, dati):
    tmp = percorso + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dati, f, ensure_ascii=False, indent=2)
    os.replace(tmp, percorso)


def leggi_json(percorso, base):
    try:
        with open(percorso, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return base


user32 = ctypes.windll.user32
NOMI_SPECIALI = {
    0x01: "Clic sinistro", 0x02: "Clic destro", 0x04: "Clic rotellina", 0x05: "Mouse laterale 1",
    0x06: "Mouse laterale 2", 0x20: "Spazio", 0x09: "Tab", 0x14: "Bloc Maiusc", 0x0D: "Invio",
    0x1B: "Esc", 0x08: "Backspace", CTRL: "Ctrl", ALT: "Alt", MAIUSC: "Maiusc", WIN: "Win",
    0x25: "Sinistra", 0x26: "Su", 0x27: "Destra", 0x28: "Giu", 0x2D: "Ins", 0x2E: "Canc",
    0x24: "Home", 0x23: "Fine", 0x21: "PagSu", 0x22: "PagGiu",
}
SINONIMI = {0xA0: MAIUSC, 0xA1: MAIUSC, 0xA2: CTRL, 0xA3: CTRL, 0xA4: ALT, 0xA5: ALT, 0x5C: WIN}


def nome_tasto(vk):
    if vk in NOMI_SPECIALI:
        return NOMI_SPECIALI[vk]
    if 0x70 <= vk <= 0x87:
        return f"F{vk - 0x6F}"
    sc = user32.MapVirtualKeyW(vk, 0)
    buf = ctypes.create_unicode_buffer(64)
    if sc and user32.GetKeyNameTextW(sc << 16, buf, 64):
        return buf.value
    return f"Tasto {vk:#04x}"


def nome_combinazione(vks):
    return "+".join(nome_tasto(v) for v in vks) if vks else "nessuno"


def giu(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


class Tasti:
    def __init__(self, app):
        self.app = app
        self.cattura_per = None
        self.cattura_fino = 0.0

    def avvia(self):
        threading.Thread(target=self._ciclo, daemon=True, name="tasti").start()

    def cattura(self, azione, secondi=8.0):
        if azione != "apri" and azione not in AZIONI:
            raise ValueError("azione sconosciuta")
        self.cattura_per = azione
        self.cattura_fino = time.time() + secondi

    def _fine_cattura(self, testo=None):
        azione, self.cattura_per = self.cattura_per, None
        self.cattura_fino = 0.0
        if testo:
            self.app.scrivi(testo)
        self.app.bacheca.pubblica("tasto", {"azione": azione}, solo_pannello=True)
        self.app.pubblica_stato()

    def _cattura(self, stato_prima):
        azione = self.cattura_per
        if time.time() > self.cattura_fino:
            self._fine_cattura("Nessun tasto premuto: non ho cambiato niente")
            return
        for vk in range(2, 255):
            if SINONIMI.get(vk, vk) in MODIFICATORI:
                continue
            premuto = giu(vk)
            if premuto and not stato_prima.get(vk):
                if vk == 0x1B:
                    self._fine_cattura("Cambio del tasto annullato")
                    return
                if azione == "apri":
                    self.app.aggiorna_config({"tasto": vk, "nome_tasto": nome_tasto(vk)})
                    self._fine_cattura(f"Tasto per aprire le casse: {nome_tasto(vk)}")
                else:
                    combo = [m for m in MODIFICATORI if giu(m)] + [vk]
                    tasti = dict(self.app.config.get("tasti", {}))
                    tasti[azione] = combo
                    self.app.aggiorna_config({"tasti": tasti})
                    self._fine_cattura(f"{AZIONI[azione][0]}: {nome_combinazione(combo)}")
                return
            stato_prima[vk] = premuto

    def _ciclo(self):
        prima_apri = False
        prima = {}
        stato_cattura = None
        while True:
            cfg = self.app.config
            adesso = time.time()
            if self.cattura_per:
                if stato_cattura is None:
                    stato_cattura = {vk: giu(vk) for vk in range(1, 255)}
                self._cattura(stato_cattura)
                time.sleep(0.01)
                continue
            if stato_cattura is not None:
                stato_cattura = None
                prima = {a: bool(c) and all(giu(v) for v in c) for a, c in cfg.get("tasti", {}).items()}
                prima_apri = giu(int(cfg["tasto"]))

            premuto = giu(int(cfg["tasto"]))
            if premuto and not prima_apri:
                self.app.occhio.tasto_premuto(adesso)
            prima_apri = premuto

            if cfg.get("scorciatoie", True):
                for azione, combo in cfg.get("tasti", {}).items():
                    attiva = bool(combo) and all(giu(v) for v in combo)
                    if attiva and not prima.get(azione):
                        self._esegui(azione)
                    prima[azione] = attiva
            time.sleep(0.01)

    def _esegui(self, azione):
        app = self.app
        n = nome_combinazione(app.config["tasti"].get(azione, []))
        if azione == "piu":
            app.cambia("piu", motivo=f"Tasto {n}")
        elif azione == "meno":
            app.cambia("meno", motivo=f"Tasto {n}")
        elif azione == "pausa":
            app.pausa("cambia")


class Live:
    UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/140.0 Safari/537.36"}

    def __init__(self, app):
        self.app = app
        self.stato = {c["id"]: False for c in CANALI}

    def avvia(self):
        threading.Thread(target=self._ciclo, daemon=True, name="live").start()

    def _leggi(self, url):
        with urllib.request.urlopen(urllib.request.Request(url, headers=self.UA), timeout=10) as r:
            return r.read().decode("utf-8", "replace")

    def in_live(self, c):
        if c["piattaforma"] == "twitch":
            t = self._leggi(f"https://decapi.me/twitch/uptime/{c['utente']}").strip().lower()
            return ("offline" not in t and "error" not in t and "not found" not in t
                    and any(p in t for p in ("second", "minute", "hour", "day")))
        d = json.loads(self._leggi("https://www.tiktok.com/api-live/user/room/?aid=1988&sourceType=54"
                                   f"&uniqueId={c['utente']}")).get("data") or {}
        return (d.get("liveRoom") or {}).get("status") == 2

    def pubblici(self):
        return [{**c, "live": self.stato.get(c["id"], False),
                 "link": c["url"] + ("/live" if c["piattaforma"] == "tiktok" and self.stato.get(c["id"]) else "")}
                for c in CANALI]

    def _ciclo(self):
        while True:
            cambiato = False
            for c in CANALI:
                try:
                    v = self.in_live(c)
                except Exception:
                    continue
                if v != self.stato.get(c["id"]):
                    self.stato[c["id"]] = v
                    cambiato = True
            if cambiato:
                self.app.bacheca.pubblica("live", {"canali": self.pubblici()}, solo_pannello=True)
            time.sleep(OGNI_QUANTO_LIVE)


class Bacheca:
    def __init__(self):
        self.lock = threading.Lock()
        self.iscritti = []

    def iscrivi(self, pannello):
        q = queue.Queue(maxsize=300)
        with self.lock:
            self.iscritti.append((q, pannello))
        return q

    def disiscrivi(self, q):
        with self.lock:
            self.iscritti = [x for x in self.iscritti if x[0] is not q]

    def pubblica(self, tipo, dati, solo_pannello=False):
        msg = f"event: {tipo}\ndata: {json.dumps(dati, ensure_ascii=False)}\n\n"
        with self.lock:
            for q, pannello in self.iscritti:
                if solo_pannello and not pannello:
                    continue
                try:
                    q.put_nowait(msg)
                except queue.Full:
                    pass


class App:
    def __init__(self):
        os.makedirs(SCHERMO, exist_ok=True)
        self.lock = threading.RLock()
        self.config = json.loads(json.dumps(CONFIG_BASE))
        letto = leggi_json(FILE_CONFIG, {})
        self.config.update({k: v for k, v in letto.items() if k in CONFIG_BASE})
        tasti = dict(CONFIG_BASE["tasti"])
        tasti.update({k: v for k, v in (letto.get("tasti") or {}).items() if k in AZIONI and isinstance(v, list)})
        self.config["tasti"] = tasti
        scrivi_json(FILE_CONFIG, self.config)
        self.contatore = int(leggi_json(FILE_STATO, {}).get("contatore", 0))
        self.bacheca = Bacheca()
        self.registro = deque(maxlen=60)
        self.salva_contatore()
        self.occhio = schermo.Occhio(self, SCHERMO, SCRITTA_BASE)
        self.tasti = Tasti(self)
        self.live = Live(self)

    def salva_contatore(self):
        scrivi_json(FILE_STATO, {"contatore": self.contatore})
        with open(FILE_TESTO, "w", encoding="utf-8") as f:
            f.write(str(self.contatore))

    def cambia(self, azione, valore=None, motivo=""):
        with self.lock:
            prima = self.contatore
            if azione == "piu":
                self.contatore += 1
            elif azione == "meno":
                self.contatore = max(0, self.contatore - 1)
            elif azione == "azzera":
                self.contatore = 0
            elif azione == "imposta":
                self.contatore = max(0, int(valore))
            self.salva_contatore()
            n = self.contatore
        self.bacheca.pubblica("contatore", {"valore": n, "delta": n - prima})
        if motivo:
            self.scrivi(f"{motivo}: {prima} -> {n}", "conta" if n > prima else "info")
        return n

    def scrivi(self, testo, tipo="info"):
        voce = {"ora": time.strftime("%H:%M:%S"), "testo": testo, "tipo": tipo}
        self.registro.appendleft(voce)
        print(f"[{voce['ora']}] {testo}", flush=True)
        self.bacheca.pubblica("registro", voce, solo_pannello=True)

    def aggiorna_config(self, nuovi):
        prima_auto = self.config.get("automatico", True)
        with self.lock:
            for k, v in nuovi.items():
                if k in CONFIG_BASE:
                    self.config[k] = v
            scrivi_json(FILE_CONFIG, self.config)
        if self.config.get("automatico", True) != prima_auto:
            self.bacheca.pubblica("pausa", {"pausa": not self.config["automatico"]})
            self.scrivi("Conteggio automatico ripreso" if self.config["automatico"]
                        else "Conteggio automatico in PAUSA (+1 e -1 a mano funzionano lo stesso)", "avviso")
        self.pubblica_stato()

    def pausa(self, azione="cambia"):
        in_pausa = not self.config.get("automatico", True)
        voluta = {"pausa": True, "riprendi": False}.get(azione, not in_pausa)
        if voluta != in_pausa:
            self.aggiorna_config({"automatico": not voluta})
        return voluta

    def pubblica_stato(self):
        self.bacheca.pubblica("stato", self.stato(), solo_pannello=True)

    def stato(self):
        cfg = self.config
        occhio = getattr(self, "occhio", None)
        return {
            "versione": VERSIONE,
            "contatore": self.contatore,
            "config": cfg,
            "tasti": {
                "apri": {"nome": cfg.get("nome_tasto", "E"), "etichetta": "Aprire le casse (in gioco)"},
                **{a: {"nome": nome_combinazione(cfg["tasti"].get(a, [])), "etichetta": AZIONI[a][0]}
                   for a in AZIONI},
            },
            "cattura_tasto": getattr(getattr(self, "tasti", None), "cattura_per", None),
            "schermo": {"modelli": occhio.pubblici() if occhio else [],
                        "attivo": getattr(occhio, "attivo", False),
                        "errore": getattr(occhio, "errore", None),
                        "schermi": schermo.Cattura.schermi()},
            "registro": list(self.registro),
            "file_testo": FILE_TESTO,
            "discord": DISCORD,
            "canali": self.live.pubblici() if hasattr(self, "live") else [],
        }


def crea_gestore(app):
    class Gestore(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def _invia(self, codice, corpo, tipo="application/json; charset=utf-8"):
            if isinstance(corpo, (dict, list)) or corpo is None:
                corpo = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
            elif isinstance(corpo, str):
                corpo = corpo.encode("utf-8")
            self.send_response(codice)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(corpo)

        def _file(self, nome):
            with open(os.path.join(WEB, nome), "rb") as f:
                self._invia(200, f.read(), "text/html; charset=utf-8")

        def _png(self, img):
            if img is None:
                return self._invia(404, {"errore": "niente da mostrare"})
            self._invia(200, schermo.cv2.imencode(".png", img)[1].tobytes(), "image/png")

        def do_GET(self):
            u = urlparse(self.path)
            q = parse_qs(u.query)
            if u.path in ("/", "/pannello"):
                return self._file("pannello.html")
            if u.path in ("/overlay", "/overlay.html"):
                return self._file("overlay.html")
            if u.path == "/api/stato":
                return self._invia(200, app.stato())
            if u.path == "/api/contatore":
                return self._invia(200, {"valore": app.contatore})
            if u.path == "/api/schermo/foto.jpg":
                f = app.occhio.foto
                if f is None:
                    return self._invia(404, {"errore": "nessuna foto"})
                return self._invia(200, schermo.cv2.imencode(".jpg", f, [schermo.cv2.IMWRITE_JPEG_QUALITY, 88])[1]
                                   .tobytes(), "image/jpeg")
            if u.path == "/api/schermo/visto.png":
                return self._png(app.occhio.immagine_visto())
            if u.path == "/api/schermo/modello.png":
                return self._png(app.occhio.modello_png(q.get("file", [""])[0]))
            if u.path == "/eventi":
                return self._eventi("pannello" in q)
            self._invia(404, {"errore": "non trovato"})

        def _eventi(self, pannello):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            coda = app.bacheca.iscrivi(pannello)
            try:
                primo = json.dumps({"valore": app.contatore, "delta": 0})
                pausa = json.dumps({"pausa": not app.config.get("automatico", True)})
                self.wfile.write(f"retry: 1500\nevent: contatore\ndata: {primo}\n\n"
                                 f"event: pausa\ndata: {pausa}\n\n".encode())
                self.wfile.flush()
                while True:
                    try:
                        msg = coda.get(timeout=15)
                    except queue.Empty:
                        msg = ": vivo\n\n"
                    self.wfile.write(msg.encode("utf-8"))
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                pass
            finally:
                app.bacheca.disiscrivi(coda)
                self.close_connection = True

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Private-Network", "true")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_POST(self):
            u = urlparse(self.path)
            n = int(self.headers.get("Content-Length") or 0)
            grezzo = self.rfile.read(n) if n else b""
            try:
                corpo = json.loads(grezzo or b"{}")
                if u.path == "/api/contatore":
                    v = app.cambia(corpo.get("azione"), corpo.get("valore"),
                                   motivo={"piu": "+1 a mano", "meno": "-1 a mano", "azzera": "Azzerato",
                                           "imposta": "Impostato a mano"}.get(corpo.get("azione"), ""))
                    return self._invia(200, {"valore": v})
                if u.path == "/api/non_era_cassa":
                    return self._invia(200, {"valore": app.cambia("meno", motivo="Non era una cassa")})
                if u.path == "/api/config":
                    app.aggiorna_config(corpo)
                    return self._invia(200, app.config)
                if u.path in ("/api/rileva_tasto", "/api/tasti/cattura"):
                    app.tasti.cattura(corpo.get("azione", "apri"))
                    app.pubblica_stato()
                    return self._invia(200, {"ok": True})
                if u.path == "/api/tasti/predefiniti":
                    app.aggiorna_config({"tasti": {a: v[1] for a, v in AZIONI.items()},
                                         "tasto": 0x45, "nome_tasto": "E"})
                    app.scrivi("Tasti rimessi come all'inizio")
                    return self._invia(200, {"ok": True})
                if u.path == "/api/streamdeck":
                    app.scrivi("Stream Deck collegato")
                    return self._invia(200, {"valore": app.contatore,
                                             "pausa": not app.config.get("automatico", True)})
                if u.path == "/api/pausa":
                    p = app.pausa(corpo.get("azione", "cambia"))
                    return self._invia(200, {"pausa": p, "valore": app.contatore})
                if u.path == "/api/schermo/foto":
                    ritardo = max(0.0, min(15.0, float(corpo.get("ritardo", 5))))
                    if not app.occhio.fai_foto(ritardo).wait(ritardo + 5) or app.occhio.foto is None:
                        return self._invia(500, {"errore": "lo schermo non si cattura"})
                    h, w = app.occhio.foto.shape[:2]
                    app.scrivi(f"Schermo catturato ({w}x{h}): ritaglia la scritta")
                    return self._invia(200, {"w": w, "h": h})
                if u.path == "/api/schermo/modello":
                    m = app.occhio.aggiungi_modello(corpo["x"], corpo["y"], corpo["w"], corpo["h"], corpo.get("nome"))
                    app.scrivi(f"Scritta salvata: {m['nome']} ({m['w']}x{m['h']} px)")
                    app.pubblica_stato()
                    return self._invia(200, {"ok": True})
                if u.path == "/api/schermo/elimina":
                    app.occhio.elimina_modello(str(corpo.get("file", "")))
                    app.pubblica_stato()
                    return self._invia(200, {"ok": True})
            except Exception as e:
                return self._invia(400, {"errore": str(e)})
            self._invia(404, {"errore": "non trovato"})

    return Gestore


def porta_occupata(porta):
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", porta)) == 0


def main():
    apri = "--senza-browser" not in sys.argv
    try:
        ctypes.windll.kernel32.SetConsoleTitleW("ContaCasse")
    except Exception:
        pass
    if porta_occupata(PORTA):
        print("ContaCasse e' gia' acceso: apro il pannello.")
        if apri:
            webbrowser.open(f"http://127.0.0.1:{PORTA}/")
        time.sleep(2)
        return
    app = App()
    server = ThreadingHTTPServer(("127.0.0.1", PORTA), crea_gestore(app))
    server.daemon_threads = True
    app.occhio.avvia()
    app.tasti.avvia()
    app.live.avvia()
    print("=" * 64)
    print(f"  ContaCasse {VERSIONE} acceso")
    print(f"  Pannello:  http://127.0.0.1:{PORTA}/")
    print(f"  Overlay:   http://127.0.0.1:{PORTA}/overlay.html   (OBS: Browser / TikTok Live Studio: Link)")
    print("  Fortnite va in 'Schermo intero in finestra'.")
    print("  Chiudi questa finestra per spegnerlo (il numero resta salvato).")
    print("=" * 64)
    if apri:
        threading.Timer(0.6, lambda: webbrowser.open(f"http://127.0.0.1:{PORTA}/")).start()
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

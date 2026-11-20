import ctypes
import threading
import time

try:
    import hid
except Exception:
    hid = None

NOMI = {
    "OVEST": "Quadrato / X", "SUD": "Croce / A", "EST": "Cerchio / B", "NORD": "Triangolo / Y",
    "L1": "L1 / LB", "R1": "R1 / RB", "L2": "L2 / LT", "R2": "R2 / RT", "L3": "L3 / LS", "R3": "R3 / RS",
    "SU": "Freccia su", "GIU": "Freccia giu", "SINISTRA": "Freccia sinistra", "DESTRA": "Freccia destra",
    "MENU": "Options / Menu", "VISTA": "Create / Vista",
}

XINPUT_BIT = {
    0x0001: "SU", 0x0002: "GIU", 0x0004: "SINISTRA", 0x0008: "DESTRA", 0x0010: "MENU", 0x0020: "VISTA",
    0x0040: "L3", 0x0080: "R3", 0x0100: "L1", 0x0200: "R1",
    0x1000: "SUD", 0x2000: "EST", 0x4000: "OVEST", 0x8000: "NORD",
}
FRECCE = {0: ("SU",), 1: ("SU", "DESTRA"), 2: ("DESTRA",), 3: ("GIU", "DESTRA"),
          4: ("GIU",), 5: ("GIU", "SINISTRA"), 6: ("SINISTRA",), 7: ("SU", "SINISTRA")}
FACCIA = ((0x10, "OVEST"), (0x20, "SUD"), (0x40, "EST"), (0x80, "NORD"))
SPALLE = ((0x01, "L1"), (0x02, "R1"), (0x04, "L2"), (0x08, "R2"),
          (0x10, "VISTA"), (0x20, "MENU"), (0x40, "L3"), (0x80, "R3"))

SONY = 0x054C
DUALSENSE = {0x0CE6, 0x0DF2}
DUALSHOCK = {0x05C4, 0x09CC, 0x0BA0}


def nome(pulsante):
    return NOMI.get(pulsante, "nessuno") if pulsante else "nessuno"


def tasti_sony(dualsense, r):
    if not r:
        return None
    rid, n = r[0], len(r)
    if dualsense:
        base = 8 if rid == 0x01 and n >= 30 else 9 if rid == 0x31 else 5 if rid == 0x01 else None
    else:
        base = 5 if rid == 0x01 else 7 if 0x11 <= rid <= 0x19 else None
    if base is None or n < base + 2:
        return None
    b0, b1 = r[base], r[base + 1]
    premuti = set(FRECCE.get(b0 & 0x0F, ()))
    premuti.update(n for bit, n in FACCIA if b0 & bit)
    premuti.update(n for bit, n in SPALLE if b1 & bit)
    return premuti


class _StatoXInput(ctypes.Structure):
    _fields_ = [("pacchetto", ctypes.c_uint32), ("tasti", ctypes.c_uint16),
                ("lt", ctypes.c_ubyte), ("rt", ctypes.c_ubyte),
                ("lx", ctypes.c_short), ("ly", ctypes.c_short), ("rx", ctypes.c_short), ("ry", ctypes.c_short)]


def _carica_xinput():
    for nome_dll in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
        try:
            return ctypes.WinDLL(nome_dll).XInputGetState
        except OSError:
            continue
    return None


class Pad:
    def __init__(self, scrivi=None):
        self.scrivi = scrivi or (lambda t: None)
        self.xinput = _carica_xinput()
        self.collegati_x = [False] * 4
        self.prova_x = [0.0] * 4
        self.sony = {}
        self.lock = threading.Lock()

    def avvia(self):
        if hid is not None:
            threading.Thread(target=self._cerca_sony, daemon=True, name="pad-sony").start()

    def _xinput(self, adesso):
        premuti = set()
        if self.xinput is None:
            return premuti
        for i in range(4):
            if not self.collegati_x[i] and adesso < self.prova_x[i]:
                continue
            st = _StatoXInput()
            ok = self.xinput(i, ctypes.byref(st)) == 0
            if ok != self.collegati_x[i]:
                self.collegati_x[i] = ok
                self.scrivi(f"Controller {i + 1} (Xbox / XInput) {'collegato' if ok else 'scollegato'}")
            if not ok:
                self.prova_x[i] = adesso + 2.0
                continue
            premuti.update(n for bit, n in XINPUT_BIT.items() if st.tasti & bit)
            if st.lt > 60:
                premuti.add("L2")
            if st.rt > 60:
                premuti.add("R2")
        return premuti

    def premuti(self):
        p = self._xinput(time.time())
        with self.lock:
            for s in self.sony.values():
                p |= s
        return p

    def _cerca_sony(self):
        while True:
            try:
                for d in hid.enumerate(SONY):
                    pid, percorso = d.get("product_id"), d.get("path")
                    if pid not in DUALSENSE | DUALSHOCK or percorso in self.sony:
                        continue
                    with self.lock:
                        self.sony[percorso] = set()
                    threading.Thread(target=self._leggi_sony, args=(percorso, pid in DUALSENSE),
                                     daemon=True, name="pad-sony-leggi").start()
            except Exception:
                pass
            time.sleep(3)

    def _leggi_sony(self, percorso, dualsense):
        tipo = "PS5 (DualSense)" if dualsense else "PS4 (DualShock 4)"
        dev = hid.device()
        aperto = False
        try:
            dev.open_path(percorso)
            aperto = True
            self.scrivi(f"Controller {tipo} collegato")
            while True:
                r = dev.read(128, 500)
                s = tasti_sony(dualsense, r) if r else None
                if s is not None:
                    with self.lock:
                        self.sony[percorso] = s
        except Exception:
            pass
        finally:
            try:
                dev.close()
            except Exception:
                pass
            if aperto:
                with self.lock:
                    self.sony.pop(percorso, None)
                self.scrivi(f"Controller {tipo} scollegato")
            else:
                with self.lock:
                    self.sony[percorso] = set()
                riprova = threading.Timer(30, lambda: self.sony.pop(percorso, None))
                riprova.daemon = True
                riprova.start()

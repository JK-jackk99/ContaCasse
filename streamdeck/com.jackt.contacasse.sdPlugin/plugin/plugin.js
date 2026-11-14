const SERVER = 'http://127.0.0.1:8787';
const A = {
  piu: 'com.jackt.contacasse.piu',
  meno: 'com.jackt.contacasse.meno',
  contatore: 'com.jackt.contacasse.contatore',
  nonera: 'com.jackt.contacasse.nonera',
  pausa: 'com.jackt.contacasse.pausa'
};
const TENERE_PER_AZZERARE = 2000;

let sd = null;
const tasti = new Map();
const timerAzzera = new Map();
let valore = null;
let inPausa = false;
let eventi = null;

const cassa = new Image();
cassa.src = '../imgs/cassa.png';
cassa.onload = () => ridisegnaContatori();

function send(obj) {
  if (sd && sd.readyState === 1) sd.send(JSON.stringify(obj));
}
const showOk = (c) => send({ event: 'showOk', context: c });
const showAlert = (c) => send({ event: 'showAlert', context: c });

async function post(percorso, dati) {
  const r = await fetch(SERVER + percorso, {
    method: 'POST',
    headers: { 'Content-Type': 'text/plain' },
    body: JSON.stringify(dati || {})
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.errore || ('HTTP ' + r.status));
  return j;
}

async function azione(context, percorso, dati) {
  try {
    const j = await post(percorso, dati);
    if (typeof j.valore === 'number') aggiorna(j.valore);
    showOk(context);
  } catch (e) {
    showAlert(context);
  }
}

/* ---------- il numero sul tasto ---------- */

function immagineContatore() {
  const c = document.createElement('canvas');
  c.width = c.height = 144;
  const g = c.getContext('2d');
  g.fillStyle = '#14101e';
  g.fillRect(0, 0, 144, 144);
  g.strokeStyle = valore === null ? '#55516a' : '#ffc93c';
  g.lineWidth = 6;
  g.beginPath();
  g.roundRect(5, 5, 134, 134, 22);
  g.stroke();
  if (cassa.complete && cassa.naturalWidth) {
    g.globalAlpha = valore === null ? 0.35 : 1;
    g.drawImage(cassa, 46, 12, 52, 52);
    g.globalAlpha = 1;
  }
  const testo = valore === null ? 'OFF' : String(valore);
  const dim = testo.length <= 2 ? 64 : testo.length === 3 ? 52 : 40;
  g.font = `900 ${dim}px "Arial Black", Arial, sans-serif`;
  g.textAlign = 'center';
  g.textBaseline = 'alphabetic';
  g.lineJoin = 'round';
  g.lineWidth = 8;
  g.strokeStyle = '#2a1400';
  g.strokeText(testo, 72, 128);
  const grad = g.createLinearGradient(0, 128 - dim, 0, 128);
  if (valore === null) {
    grad.addColorStop(0, '#9a98a8'); grad.addColorStop(1, '#6c6880');
  } else {
    grad.addColorStop(0, '#fff7d6'); grad.addColorStop(1, '#ffc93c');
  }
  g.fillStyle = grad;
  g.fillText(testo, 72, 128);
  if (inPausa && valore !== null) {
    g.fillStyle = '#ff9f1c';
    g.fillRect(110, 16, 7, 22);
    g.fillRect(121, 16, 7, 22);
  }
  return c.toDataURL('image/png');
}

function ridisegnaContatori() {
  const img = immagineContatore();
  for (const [context, action] of tasti) {
    if (action === A.contatore) send({ event: 'setImage', context, payload: { image: img, target: 0 } });
  }
}

function aggiorna(v) {
  if (v === valore) return;
  valore = v;
  ridisegnaContatori();
}

function aggiornaPausa(p) {
  inPausa = !!p;
  for (const [context, action] of tasti) {
    if (action === A.pausa) send({ event: 'setState', context, payload: { state: inPausa ? 1 : 0 } });
  }
  ridisegnaContatori();
}

/* ---------- collegamento a ContaCasse ---------- */

function collegaEventi() {
  if (eventi) return;
  eventi = new EventSource(SERVER + '/eventi');
  eventi.addEventListener('contatore', (e) => {
    try { aggiorna(JSON.parse(e.data).valore); } catch (err) {}
  });
  eventi.addEventListener('pausa', (e) => {
    try { aggiornaPausa(JSON.parse(e.data).pausa); } catch (err) {}
  });
  eventi.onopen = () => {
    post('/api/streamdeck').then((j) => { aggiorna(j.valore); aggiornaPausa(j.pausa); }).catch(() => {});
  };
  eventi.onerror = () => aggiorna(null);
}

/* ---------- Stream Deck ---------- */

function connectElgatoStreamDeckSocket(inPort, inUUID, inRegisterEvent) {
  sd = new WebSocket('ws://127.0.0.1:' + inPort);
  sd.onopen = () => {
    send({ event: inRegisterEvent, uuid: inUUID });
    collegaEventi();
  };
  sd.onmessage = (msg) => {
    let d;
    try { d = JSON.parse(msg.data); } catch (e) { return; }
    gestisci(d);
  };
}
window.connectElgatoStreamDeckSocket = connectElgatoStreamDeckSocket;

function gestisci(d) {
  const { event, context, action } = d;
  switch (event) {
    case 'willAppear':
      tasti.set(context, action);
      if (action === A.contatore) {
        send({ event: 'setImage', context, payload: { image: immagineContatore(), target: 0 } });
      }
      if (action === A.pausa) send({ event: 'setState', context, payload: { state: inPausa ? 1 : 0 } });
      break;
    case 'willDisappear':
      tasti.delete(context);
      clearTimeout(timerAzzera.get(context));
      timerAzzera.delete(context);
      break;
    case 'keyDown':
      if (action === A.piu) azione(context, '/api/contatore', { azione: 'piu' });
      else if (action === A.meno) azione(context, '/api/contatore', { azione: 'meno' });
      else if (action === A.nonera) azione(context, '/api/non_era_cassa');
      else if (action === A.pausa) {
        post('/api/pausa', { azione: 'cambia' })
          .then((j) => aggiornaPausa(j.pausa))
          .catch(() => showAlert(context));
      }
      else if (action === A.contatore) {
        timerAzzera.set(context, setTimeout(() => {
          timerAzzera.delete(context);
          azione(context, '/api/contatore', { azione: 'azzera' });
        }, TENERE_PER_AZZERARE));
      }
      break;
    case 'keyUp':
      if (action === A.contatore) {
        clearTimeout(timerAzzera.get(context));
        timerAzzera.delete(context);
      }
      break;
  }
}

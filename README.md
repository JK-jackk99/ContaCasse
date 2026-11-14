# ContaCasse

Il contatore automatico delle casse di Fortnite per le tue live.
Ogni volta che apri una cassa, il numero in live sale da solo.
Funziona con **OBS**, **TikTok Live Studio** e **Stream Deck**.

Creato da **Jackk99** · [Entra nel nostro Discord](https://discord.gg/NjnRuPt3hn)

## Scarica

Vai su **[Releases](../../releases/latest)** e scarica:

- `ContaCasse.exe` — il programma (un solo file, non serve installare niente)
- `ContaCasse.streamDeckPlugin` — il plugin per Stream Deck (facoltativo)

## Come si usa

1. **Metti Fortnite in "Schermo intero in finestra"** (obbligatorio).
   In Fortnite: Impostazioni → Video → Modalità finestra → *Schermo intero in finestra*.
   Con lo "Schermo intero" normale Windows non lascia vedere il gioco a nessun programma e ContaCasse non conta niente.
2. **Avvia `ContaCasse.exe`.**
   Se Windows dice *"Windows ha protetto il PC"*: clicca *Ulteriori informazioni* → *Esegui comunque* (succede con tutti i programmi nuovi non firmati).
   Si apre una finestra nera (ContaCasse acceso: chiudila per spegnerlo) e il pannello nel browser. Il numero resta salvato.
   Non c'è niente da configurare: riconosce già la scritta "E ESAMINA" delle casse, a qualunque risoluzione.
3. **Mettilo in live** con l'indirizzo `http://127.0.0.1:8787/overlay.html`
   - OBS: Fonti → + → **Browser** → incolla l'indirizzo (larghezza 500, altezza 160).
   - TikTok Live Studio: Aggiungi sorgente → **Link** → incolla lo stesso indirizzo.
   - Scritta e stile (oro, neon, bianco) si scelgono nel pannello.

## Tasti

Si cambiano tutti nel pannello, sezione **Tasti**.

| Cosa | Tasto |
|---|---|
| Aprire le casse | `E` (quello che usi in Fortnite) |
| +1 cassa | `Ctrl+Alt+Su` |
| −1 cassa | `Ctrl+Alt+Giù` |
| Pausa / riprendi (es. mentre specti qualcuno) | `Ctrl+Alt+P` |

## Stream Deck

Doppio clic su `ContaCasse.streamDeckPlugin`: Stream Deck lo installa.
Nella categoria **ContaCasse** trovi 4 tasti: +1, −1, Contatore (mostra il numero; tienilo premuto 2 secondi per azzerare) e Pausa.

## Come capisce che hai aperto una cassa

Guarda lo schermo, come fa OBS: c'è la scritta per aprire la cassa, premi il tasto, la scritta sparisce → cassa aperta.
Le cassette di munizioni hanno la stessa scritta ma niente oro, quindi non contano.

## È sicuro?

- Non tocca Fortnite: niente file del gioco, niente memoria, niente tasti mandati al gioco. Legge solo lo schermo e se premi i tasti.
- Non manda niente di tuo su internet: pannello e overlay restano sul tuo PC.
- L'unica cosa che fa su internet: ogni 10 minuti controlla se jackk99 o hatehim_ sono in live su Twitch o TikTok, per mostrarlo nel pannello.

## Non conta?

Nel pannello apri *Impostazioni avanzate* → *Cosa vedo adesso* mentre miri una cassa: la scritta deve diventare verde.
Se resta rossa, controlla il punto 1. Per tutto il resto: [Discord](https://discord.gg/NjnRuPt3hn).

## Dal codice

Serve Python 3.12 su Windows.

```
pip install -r requirements.txt
python contacasse.py
```

Per rifare i file da pubblicare (serve anche `pip install pyinstaller pillow`):

```
python crea_exe.py
python streamdeck/crea_plugin.py
```

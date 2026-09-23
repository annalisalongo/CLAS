# CLAS – Gestione Miele

App Streamlit con 3 sole sezioni: **Magazzino**, **Vendite**, **Costi & Cassa**.

## Avvio
1. Metti nella stessa cartella `app_miele.py` e `honey_seed.json`.
2. Installa Streamlit: `pip install -r requirements_miele.txt`
3. Avvia: `streamlit run app_miele.py`

Al primo avvio viene creato automaticamente `gestione_miele.db` e viene importato lo storico dal file Excel. Dal secondo avvio l'app usa solo il database.

## Logica contabile
- Gli **sconti** sono registrati separatamente dal ricavo effettivo.
- `Pagato?` determina se la vendita è incassata o ancora da incassare.
- Metodo di pagamento e `Incassato da` servono solo per le vendite pagate.
- I **prelievi personali da restituire** non sono costi dell'apiario: riducono la cassa e creano un debito personale verso la cassa.
- I costi sono attribuibili a **Estate**, **Natale** o **Generale Apiario**.
- La scorta viene scalata automaticamente dalle vendite e dagli omaggi.

## Dati iniziali
La scorta totale resta 127 kg. Per rendere coerente la divisione Estate/Natale, 4 vasetti da 1 kg già destinati all'ordine Natale sono allocati alla linea Natale; il resto dei 1 kg resta Estate. È già registrato anche il prelievo di Chiara di 50 € da reintegrare.

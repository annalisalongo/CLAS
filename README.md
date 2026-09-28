# CLAS – Gestione Miele v2

Versione preparata per Chiara e Annalisa il 25/09/2026.

## Obiettivo
Tre sole aree operative:
1. **Magazzino**
2. **Vendite**
3. **Costi & Cassa**

L'app distingue **Estate**, **Natale** e **Generale** senza duplicare i dati.

## Dati certi già incorporati
- 50 kg di miele Natale acquistati a **8 €/kg**
- 2 secchi da 25 kg
- costo effettivo: **400 €**
- i 12 vasetti da 1 kg Estate **NON vengono riconfezionati**
- prezzi vetro noti ma ancora previsionali:
  - 500 g = **0,45 €**
  - 250 g = **0,35 €**

## Novità v2
- miele sfuso gestito separatamente dai vasetti
- invasettamento = scarico kg sfusi + carico vasetti
- costi **Effettivi / Previsionali**
- cruscotti separati Estate / Natale / Generale
- storico mensile Incassi vs Costi e Risultato
- sconti tracciati separatamente
- movimenti personali separati dai costi aziendali
- simulatore Natale 500 g / 250 g / miele lasciato sfuso
- salvataggio della simulazione come costo previsionale del vetro

## Avvio
```bash
pip install -r requirements.txt
streamlit run app_miele_v2.py
```

## Importante per il database esistente
Prima di sostituire la vecchia app, fare una copia di `gestione_miele.db`.

La v2 crea le nuove tabelle/campi mancanti senza cancellare il database. L'aggiornamento reale del 25/09/2026 è protetto da un marker (`update_2026_09_25`) per evitare duplicazioni.

### Controllo da fare una sola volta
La vecchia versione conteneva una **simulazione** di seconda tranche (40 kg a 7 €/kg e vasetti ipotetici). Se quei record sono presenti nel DB già in produzione, Annalisa deve rimuovere **solo le righe previsionali/simulate**, lasciando intatto lo storico reale. La v2 registra invece il dato reale: 50 kg × 8 € = 400 €.

## Logica contabile
- Una vendita scontata conserva: listino, sconto e totale effettivo.
- Un prelievo personale NON è un costo.
- Un costo previsionale NON riduce il risultato effettivo.
- Il risultato mostrato è gestionale, non fiscale.
- Il Generale legge tutti i movimenti; non copia i riepiloghi Estate/Natale.

## Prossimi miglioramenti consigliati
1. CRUD completo: modifica/elimina riga con conferma.
2. Backup DB da interfaccia.
3. Import guidato dello storico Excel.
4. Anagrafica clienti.
5. Anagrafica lotti/fornitori e tracciabilità alimentare.
6. Dashboard annuale con confronto stagioni.
7. Export Excel/PDF dei registri.

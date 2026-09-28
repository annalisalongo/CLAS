# CLAS Gestione Miele v3

## Passaggio definitivo
Excel storico → import una tantum → database dell'app → app come fonte ufficiale.

### Prima di avviare
1. Se esiste già `gestione_miele.db`, copiarlo nella stessa cartella di `app_miele_v3.py`.
2. Farne una copia di sicurezza.
3. `pip install -r requirements.txt`
4. `streamlit run app_miele_v3.py`
5. Aprire **Import / Export / Backup** dalla sidebar.
6. Importare lo storico Excel una sola volta e controllare il risultato.

### Sicurezza
L'importatore non cancella righe. Calcola l'hash SHA-256 del file e impedisce di reimportare lo stesso identico Excel.
È volutamente prudente: se non riconosce chiaramente le colonne, non importa quelle righe.

### Dati reali già previsti
- Natale: 50 kg miele sfuso, 2 secchi da 25 kg
- costo reale miele: 8 €/kg = 400 €
- i 12 vasetti Estate da 1 kg restano integri
- vetro 500 g: 0,45 € (previsionale)
- vetro 250 g: 0,35 € (previsionale)

### Backup
Dalla sidebar si può scaricare:
- l'intero gestionale in Excel;
- il database SQLite `.db`.

Il file `.gitignore` esclude il database dal repository Git.

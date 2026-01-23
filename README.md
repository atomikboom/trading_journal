# Automatic Trading Journal

Un programma locale per monitorare e gestire automaticamente un journal di trading con aggiornamento prezzi in tempo reale tramite AlphaVantage.

## Caratteristiche
- **Dashboard Interattiva**: KPI su capitale investito, valore portafoglio, profitto netto e rendimento.
- **Grafici**: Equity curve, distribuzione P/L per tipologia e Win/Loss ratio.
- **Aggiornamento Prezzi**: Integrazione con AlphaVantage REST API.
- **Calcolo Tassazione**: Tassazione automatica al 26% sulle plusvalenze.
- **Gestione Operazioni**: Inserimento rapido e chiusura posizioni semplificata.
- **Storage Locale**: Utilizzo di SQLite per la persistenza dei dati.

## Requisiti
- Python 3.8+
- Un'API Key di [AlphaVantage](https://www.alphavantage.co/support/#api-key) (gratuita).

## Installazione

1. Clona o scarica la cartella del progetto.
2. Installa le dipendenze:
   ```bash
   pip install -r requirements.txt
   ```
3. Crea un file `.env` (puoi rinominare `.env.example`) e inserisci la tua API Key:
   ```env
   ALPHAVANTAGE_API_KEY=TUA_API_KEY
   ```

## Avvio
Per avviare l'applicazione, esegui il seguente comando nel terminale:
```bash
streamlit run app.py
```

## Struttura del Progetto
- `app.py`: Punto di ingresso dell'interfaccia Streamlit.
- `database.py`: Gestione del database SQLite tramite SQLAlchemy.
- `api.py`: Logica di recupero prezzi da AlphaVantage.
- `calculations.py`: Logica finanziaria e calcoli automatici.
- `requirements.txt`: Elenco delle librerie necessarie.
# trading_journal

import streamlit as st
import sqlite3
from datetime import date
from pathlib import Path
import pandas as pd
import io
import hashlib
from datetime import datetime

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "gestione_miele.db"

st.set_page_config(page_title="CLAS • Gestione Miele", page_icon="🍯", layout="wide")

FORMATS = {"1 kg": (1.0, 18.0), "500 g": (0.5, 10.0), "250 g": (0.25, 6.0)}
LINES = ["Estate", "Natale"]
PAY_METHODS = ["Contanti", "Bonifico", "PayPal", "Satispay", "Altro"]
PEOPLE = ["Cassa comune", "Chiara", "Annalisa"]
COST_CATS = [
    "Miele acquistato","Vasetti / invasettamento","Etichette / packaging",
    "Smielatura","Laboratorio / pulizia","Trattamenti api","Nutrizione",
    "Attrezzatura","Trasporto","Altro"
]
COST_STATUS = ["Effettivo", "Previsionale"]

st.markdown("""
<style>
.block-container{padding-top:1.1rem;padding-bottom:2rem}
[data-testid="stMetric"]{background:#fff;border:1px solid #eee7dc;padding:12px;border-radius:14px}
div[data-testid="stDataFrame"]{border:1px solid #eee7dc;border-radius:12px}
.smallnote{color:#6b7280;font-size:.86rem}
</style>
""", unsafe_allow_html=True)

def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def euro(x):
    return f"€ {float(x or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def query(sql, args=()):
    c=conn()
    rows=c.execute(sql,args).fetchall()
    c.close()
    return [dict(r) for r in rows]

def scalar(sql,args=()):
    rows=query(sql,args)
    if not rows: return 0
    return list(rows[0].values())[0] or 0

def init_db():
    c=conn()
    q=c.cursor()
    q.executescript("""
    CREATE TABLE IF NOT EXISTS app_meta(
        key TEXT PRIMARY KEY, value TEXT
    );

    CREATE TABLE IF NOT EXISTS inventory_lots(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        movement_date TEXT NOT NULL,
        line TEXT NOT NULL,
        item_type TEXT NOT NULL,
        format TEXT,
        qty_units REAL DEFAULT 0,
        kg REAL DEFAULT 0,
        movement_type TEXT NOT NULL,
        source TEXT,
        notes TEXT
    );

    CREATE TABLE IF NOT EXISTS sales(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sale_date TEXT NOT NULL,
        line TEXT NOT NULL,
        customer TEXT NOT NULL,
        format TEXT NOT NULL,
        qty INTEGER DEFAULT 0,
        gift_qty INTEGER DEFAULT 0,
        list_unit_price REAL DEFAULT 0,
        discount REAL DEFAULT 0,
        actual_total REAL DEFAULT 0,
        paid INTEGER DEFAULT 0,
        payment_method TEXT,
        collected_by TEXT,
        notes TEXT
    );

    CREATE TABLE IF NOT EXISTS costs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cost_date TEXT NOT NULL,
        line TEXT NOT NULL,
        category TEXT NOT NULL,

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

st.markdown("""
<style>
:root { --clas-border: color-mix(in srgb, var(--text-color) 18%, transparent); --clas-soft: color-mix(in srgb, var(--text-color) 7%, transparent); }
.block-container { max-width:1400px; padding-top:1.4rem; padding-bottom:3rem; }
h1,h2,h3,h4 { letter-spacing:-0.02em; }
[data-testid="stMetric"] { background:var(--clas-soft); border:1px solid var(--clas-border); border-radius:14px; padding:14px 16px; }
[data-testid="stMetricLabel"], .stCaption, [data-testid="stCaptionContainer"] { opacity:.78; }
[data-testid="stMetricValue"] { font-weight:700; }
[data-testid="stExpander"], [data-testid="stDataFrame"] { border:1px solid var(--clas-border); border-radius:12px; overflow:hidden; }
[data-testid="stForm"] { border:1px solid var(--clas-border); border-radius:14px; padding:1rem; background:var(--clas-soft); }
[data-testid="stSidebar"] { border-right:1px solid var(--clas-border); }
.stButton>button,.stDownloadButton>button,[data-testid="stFormSubmitButton"]>button { border-radius:10px; border:1px solid var(--clas-border); font-weight:600; }
[data-baseweb="input"]>div,[data-baseweb="select"]>div,[data-baseweb="textarea"]>div { border-color:var(--clas-border)!important; }
hr { border-color:var(--clas-border)!important; }
[data-testid="stAlert"] { border-radius:12px; }
@media (max-width:768px){.block-container{padding-left:1rem;padding-right:1rem}[data-testid="stMetric"]{padding:10px 12px}}
</style>
""", unsafe_allow_html=True)

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

st.markdown("""
<style>
/* CLAS dark-mode refinement: metric cards inherit the app palette */
[data-testid="stMetric"] {
    background: rgba(255,255,255,0.045) !important;
    color: var(--text-color) !important;
}
[data-testid="stMetric"] * {
    color: var(--text-color) !important;
}
[data-testid="stMetricLabel"] {
    opacity: .72 !important;
}
</style>
""", unsafe_allow_html=True)

def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def euro(x):
    return f"€ {float(x or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def safe_date(value):
    """Converte date SQLite/Excel/italiane senza mandare in crash l'interfaccia."""
    if value is None or str(value).strip()=="":
        return date.today()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s=str(value).strip()
    for fmt in ("%Y-%m-%d","%Y-%m-%d %H:%M:%S","%d/%m/%Y","%d-%m-%Y","%d.%m.%Y"):
        try:
            candidate=s[:19] if "%H" in fmt else s[:10]
            return datetime.strptime(candidate,fmt).date()
        except (ValueError,TypeError):
            pass
    try:
        parsed=pd.to_datetime(s,dayfirst=True,errors="coerce")
        if not pd.isna(parsed):
            return parsed.date()
    except Exception:
        pass
    return date.today()

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
        description TEXT NOT NULL,
        qty REAL DEFAULT 1,
        unit_cost REAL DEFAULT 0,
        total REAL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'Effettivo',
        paid_by TEXT DEFAULT 'Cassa comune',
        notes TEXT
    );

    CREATE TABLE IF NOT EXISTS cash_moves(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        move_date TEXT NOT NULL,
        person TEXT NOT NULL,
        type TEXT NOT NULL,
        amount REAL NOT NULL,
        notes TEXT
    );
    """)
    # Migrazioni compatibili con la prima versione
    cols={r[1] for r in q.execute("PRAGMA table_info(costs)").fetchall()}
    if "status" not in cols:
        q.execute("ALTER TABLE costs ADD COLUMN status TEXT NOT NULL DEFAULT 'Effettivo'")
    c.commit()
    c.close()

def meta_get(key):
    r=query("SELECT value FROM app_meta WHERE key=?",(key,))
    return r[0]["value"] if r else None

def meta_set(key,value="1"):
    c=conn()
    c.execute("INSERT OR REPLACE INTO app_meta(key,value) VALUES(?,?)",(key,value))
    c.commit(); c.close()

def apply_known_update():
    """Inserisce UNA SOLA VOLTA i dati certi comunicati il 25/09/2026."""
    if meta_get("update_2026_09_25"): return
    c=conn()
    # 50 kg Natale sfusi, 2 secchi da 25 kg
    c.execute("""INSERT INTO inventory_lots
        (movement_date,line,item_type,format,qty_units,kg,movement_type,source,notes)
        VALUES(?,?,?,?,?,?,?,?,?)""",
        ("2026-09-25","Natale","Miele sfuso",None,2,50,"Carico",
         "Acquisto","2 secchi da 25 kg"))
    # Costo reale miele: 50 kg x 8 €
    c.execute("""INSERT INTO costs
        (cost_date,line,category,description,qty,unit_cost,total,status,paid_by,notes)
        VALUES(?,?,?,?,?,?,?,?,?,?)""",
        ("2026-09-25","Natale","Miele acquistato",
         "Acquisto 50 kg miele - 2 secchi da 25 kg",50,8,400,
         "Effettivo","Cassa comune","Dato reale comunicato da Chiara"))
    c.commit(); c.close()
    meta_set("update_2026_09_25")

def jar_stock(line=None):
    """Giacenza vasetti calcolata dai movimenti di magazzino meno vendite/omaggi."""
    result=[]
    lines=LINES if line is None or line=="Tutto" else [line]
    for ln in lines:
        for fmt,(kg_each,price) in FORMATS.items():
            # Carichi e scarichi espliciti di vasetti.
            inv=query("""SELECT COALESCE(SUM(
                CASE
                    WHEN movement_type='Scarico' THEN -qty_units
                    ELSE qty_units
                END),0) q
                FROM inventory_lots
                WHERE line=? AND item_type='Vasetti' AND format=?""",(ln,fmt))[0]["q"] or 0

            sold=query("""SELECT COALESCE(SUM(qty+gift_qty),0) q
                          FROM sales WHERE line=? AND format=?""",(ln,fmt))[0]["q"] or 0

            residual=float(inv)-float(sold)
            result.append({
                "Linea":ln,
                "Formato":fmt,
                "Residuo vasetti":int(residual) if residual.is_integer() else residual,
                "Kg invasettati residui":round(residual*kg_each,2),
                "Stato":"⚠️ Da correggere" if residual < 0 else "OK"
            })
    return result

def bulk_stock(line=None):
    wh="WHERE item_type='Miele sfuso'"
    args=[]
    if line and line!="Tutto":
        wh+=" AND line=?"; args.append(line)
    return scalar(f"""SELECT COALESCE(SUM(
        CASE WHEN movement_type='Carico' THEN kg ELSE -kg END),0)
        FROM inventory_lots {wh}""",args)

def financials(line="Tutto"):
    sw="WHERE 1=1"; args=[]
    if line!="Tutto":
        sw+=" AND line=?"; args.append(line)
    s=query(f"""SELECT
        COALESCE(SUM(qty*list_unit_price),0) listino,
        COALESCE(SUM(discount),0) sconti,
        COALESCE(SUM(actual_total),0) vendite,
        COALESCE(SUM(CASE WHEN paid=1 THEN actual_total ELSE 0 END),0) incassato,
        COALESCE(SUM(CASE WHEN paid=0 THEN actual_total ELSE 0 END),0) credito
        FROM sales {sw}""",args)[0]
    eff=scalar(f"SELECT COALESCE(SUM(total),0) FROM costs {sw} AND status='Effettivo'",args)
    prev=scalar(f"SELECT COALESCE(SUM(total),0) FROM costs {sw} AND status='Previsionale'",args)
    return {**s,"costi_eff":eff,"costi_prev":prev}

def kpis(f):
    risultato=float(f["vendite"])-float(f["costi_eff"])
    a,b,c,d=st.columns(4)
    a.metric("💰 Vendite",euro(f["vendite"]))
    b.metric("✅ Incassato",euro(f["incassato"]))
    c.metric("⏳ Da incassare",euro(f["credito"]))
    d.metric("📉 Costi effettivi",euro(f["costi_eff"]))
    a,b,c=st.columns(3)
    a.metric("🏷️ Sconti",euro(f["sconti"]))
    b.metric("🧾 Costi previsti",euro(f["costi_prev"]))
    c.metric("📊 Risultato",euro(risultato))
    st.caption("Risultato gestionale = vendite registrate − costi effettivi. Non è un utile fiscale.")

def personal_balance(person):
    bal=0.0
    for r in query("SELECT type,amount FROM cash_moves WHERE person=?",(person,)):
        t=(r["type"] or "").lower(); a=float(r["amount"] or 0)
        if "prelievo" in t and "restituzione" not in t: bal+=a
        elif "restituzione prelievo" in t: bal-=a
        elif "anticipo personale" in t: bal-=a
        elif "rimborso anticipo" in t: bal+=a
        elif "rettifica +" in t: bal+=a
        elif "rettifica -" in t: bal-=a
    return bal

def edit_sale():
    rows=query("SELECT * FROM sales ORDER BY sale_date DESC,id DESC")
    if not rows: st.info("Nessuna vendita."); return
    labels={f'#{r["id"]} · {r["sale_date"]} · {r["customer"]} · {r["format"]} · {euro(r["actual_total"])}':r for r in rows}
    r=labels[st.selectbox("Seleziona vendita",list(labels),key="edit_sale_select")]
    with st.form("edit_sale_form"):
        a,b,c,d=st.columns(4)
        dt=a.date_input("Data",safe_date(r["sale_date"]))
        ln=b.selectbox("Linea",LINES,index=LINES.index(r["line"]) if r["line"] in LINES else 0)
        customer=c.text_input("Cliente",r["customer"])
        fmt=d.selectbox("Formato",list(FORMATS),index=list(FORMATS).index(r["format"]) if r["format"] in FORMATS else 0)
        a,b,c,d=st.columns(4)
        qty=a.number_input("Quantità venduta",0,1000,int(r["qty"] or 0))
        gift=b.number_input("Omaggi",0,1000,int(r["gift_qty"] or 0))
        unit=c.number_input("Prezzo unitario €",0.0,1000.0,float(r["list_unit_price"] or 0),0.5)
        discount=d.number_input("Sconto €",0.0,10000.0,float(r["discount"] or 0),0.5)
        actual=max(0,qty*unit-discount)
        paid=st.selectbox("Pagato?",["No","Sì"],index=1 if r["paid"] else 0)
        a,b=st.columns(2)
        methods=[""]+PAY_METHODS
        collectors=[""]+PEOPLE
        method=a.selectbox("Metodo",methods,index=methods.index(r["payment_method"]) if r["payment_method"] in methods else 0)
        collector=b.selectbox("Incassato da",collectors,index=collectors.index(r["collected_by"]) if r["collected_by"] in collectors else 0)
        notes=st.text_input("Note",r["notes"] or "")
        st.caption(f"Nuovo totale effettivo: {euro(actual)}")
        if st.form_submit_button("💾 Salva modifiche"):
            c=conn(); c.execute("""UPDATE sales SET sale_date=?,line=?,customer=?,format=?,qty=?,gift_qty=?,
                list_unit_price=?,discount=?,actual_total=?,paid=?,payment_method=?,collected_by=?,notes=? WHERE id=?""",
                (str(dt),ln,customer.strip(),fmt,qty,gift,unit,discount,actual,1 if paid=="Sì" else 0,method,collector,notes,r["id"]))
            c.commit(); c.close(); st.rerun()
    ok=st.checkbox("Confermo eliminazione vendita",key=f'ds_{r["id"]}')
    if st.button("🗑️ Elimina vendita",disabled=not ok,key=f'dsb_{r["id"]}'):
        c=conn(); c.execute("DELETE FROM sales WHERE id=?",(r["id"],)); c.commit(); c.close(); st.rerun()

def edit_cost():
    rows=query("SELECT * FROM costs ORDER BY cost_date DESC,id DESC")
    if not rows: st.info("Nessun costo."); return
    labels={f'#{r["id"]} · {r["cost_date"]} · {r["description"]} · {euro(r["total"])}':r for r in rows}
    r=labels[st.selectbox("Seleziona costo",list(labels),key="edit_cost_select")]
    with st.form("edit_cost_form"):
        a,b,c,d=st.columns(4)
        dt=a.date_input("Data",safe_date(r["cost_date"]),key="ecdt")
        opts=["Estate","Natale","Generale Apiario"]
        ln=b.selectbox("Attribuzione",opts,index=opts.index(r["line"]) if r["line"] in opts else 0)
        cat=c.selectbox("Categoria",COST_CATS,index=COST_CATS.index(r["category"]) if r["category"] in COST_CATS else len(COST_CATS)-1)
        status=d.selectbox("Tipo",COST_STATUS,index=COST_STATUS.index(r["status"]) if r["status"] in COST_STATUS else 0)
        desc=st.text_input("Voce",r["description"])
        a,b,c=st.columns(3)
        qty=a.number_input("Quantità",0.0,100000.0,float(r["qty"] or 0),key="ecqty")
        unit=b.number_input("Costo unitario €",0.0,100000.0,float(r["unit_cost"] or 0),key="ecunit")
        paidby=c.selectbox("Pagato da",PEOPLE,index=PEOPLE.index(r["paid_by"]) if r["paid_by"] in PEOPLE else 0)
        notes=st.text_input("Note",r["notes"] or "",key="ecnotes")
        if st.form_submit_button("💾 Salva costo"):
            c=conn(); c.execute("""UPDATE costs SET cost_date=?,line=?,category=?,description=?,qty=?,unit_cost=?,
                total=?,status=?,paid_by=?,notes=? WHERE id=?""",
                (str(dt),ln,cat,desc,qty,unit,qty*unit,status,paidby,notes,r["id"]))
            c.commit(); c.close(); st.rerun()
    ok=st.checkbox("Confermo eliminazione costo",key=f'dc_{r["id"]}')
    if st.button("🗑️ Elimina costo",disabled=not ok,key=f'dcb_{r["id"]}'):
        c=conn(); c.execute("DELETE FROM costs WHERE id=?",(r["id"],)); c.commit(); c.close(); st.rerun()

def edit_cash_move():
    rows=query("SELECT * FROM cash_moves ORDER BY move_date DESC,id DESC")
    if not rows: st.info("Nessun movimento."); return
    labels={f'#{r["id"]} · {r["move_date"]} · {r["person"]} · {r["type"]} · {euro(r["amount"])}':r for r in rows}
    r=labels[st.selectbox("Seleziona movimento",list(labels),key="edit_cash_select")]
    types=["Prelievo da restituire","Restituzione prelievo","Anticipo personale","Rimborso anticipo","Rettifica +","Rettifica -"]
    with st.form("edit_cash_form"):
        a,b,c=st.columns(3)
        dt=a.date_input("Data",safe_date(r["move_date"]),key="emdt")
        person=b.selectbox("Persona",["Chiara","Annalisa"],index=0 if r["person"]=="Chiara" else 1)
        typ=c.selectbox("Movimento",types,index=types.index(r["type"]) if r["type"] in types else 0)
        amount=st.number_input("Importo €",0.0,100000.0,float(r["amount"] or 0),1.0,key="emamt")
        notes=st.text_input("Note",r["notes"] or "",key="emnotes")
        if st.form_submit_button("💾 Salva movimento"):
            c=conn(); c.execute("UPDATE cash_moves SET move_date=?,person=?,type=?,amount=?,notes=? WHERE id=?",
                (str(dt),person,typ,amount,notes,r["id"]))
            c.commit(); c.close(); st.rerun()
    ok=st.checkbox("Confermo eliminazione movimento",key=f'dm_{r["id"]}')
    if st.button("🗑️ Elimina movimento",disabled=not ok,key=f'dmb_{r["id"]}'):
        c=conn(); c.execute("DELETE FROM cash_moves WHERE id=?",(r["id"],)); c.commit(); c.close(); st.rerun()

def edit_inventory():
    rows=query("SELECT * FROM inventory_lots ORDER BY movement_date DESC,id DESC")
    if not rows: st.info("Nessun movimento di magazzino."); return
    labels={f'#{r["id"]} · {r["movement_date"]} · {r["line"]} · {r["item_type"]} · {r["format"] or ""}':r for r in rows}
    r=labels[st.selectbox("Seleziona movimento",list(labels),key="edit_inv_select")]
    with st.form("edit_inv_form"):
        a,b,c=st.columns(3)
        dt=a.date_input("Data",safe_date(r["movement_date"]),key="eidt")
        ln=b.selectbox("Linea",LINES,index=LINES.index(r["line"]) if r["line"] in LINES else 0,key="eiln")
        typ=c.selectbox("Tipo",["Miele sfuso","Vasetti"],index=0 if r["item_type"]=="Miele sfuso" else 1,key="eityp")
        fmt=None
        if typ=="Vasetti":
            fmt=st.selectbox("Formato",list(FORMATS),index=list(FORMATS).index(r["format"]) if r["format"] in FORMATS else 0,key="eifmt")
        a,b,c=st.columns(3)
        qty=a.number_input("Quantità / unità",0.0,100000.0,float(r["qty_units"] or 0),key="eiqty")
        kg=b.number_input("Kg",0.0,100000.0,float(r["kg"] or 0),key="eikg")
        movs=["Carico","Scarico","Invasettamento"]
        movement=c.selectbox("Movimento",movs,index=movs.index(r["movement_type"]) if r["movement_type"] in movs else 0,key="eimov")
        source=st.text_input("Origine",r["source"] or "",key="eisource")
        notes=st.text_input("Note",r["notes"] or "",key="einotes")
        if st.form_submit_button("💾 Salva magazzino"):
            c=conn(); c.execute("""UPDATE inventory_lots SET movement_date=?,line=?,item_type=?,format=?,
                qty_units=?,kg=?,movement_type=?,source=?,notes=? WHERE id=?""",
                (str(dt),ln,typ,fmt,qty,kg,movement,source,notes,r["id"]))
            c.commit(); c.close(); st.rerun()
    st.warning("L'eliminazione modifica direttamente le giacenze.")
    ok=st.checkbox("Confermo eliminazione movimento magazzino",key=f'di_{r["id"]}')
    if st.button("🗑️ Elimina movimento magazzino",disabled=not ok,key=f'dib_{r["id"]}'):
        c=conn(); c.execute("DELETE FROM inventory_lots WHERE id=?",(r["id"],)); c.commit(); c.close(); st.rerun()

def reconcile_known_stock():
    """Una tantum: allinea la giacenza Estate 1 kg al residuo reale concordato di 12 vasetti."""
    marker="stock_estate_1kg_real_12_v1"
    if meta_get(marker):
        return
    sold=query("SELECT COALESCE(SUM(qty+gift_qty),0) q FROM sales WHERE line='Estate' AND format='1 kg'")[0]["q"] or 0
    inv=query("""SELECT COALESCE(SUM(CASE WHEN movement_type='Scarico' THEN -qty_units ELSE qty_units END),0) q
                 FROM inventory_lots WHERE line='Estate' AND item_type='Vasetti' AND format='1 kg'""")[0]["q"] or 0
    target_inventory=float(sold)+12.0
    delta=target_inventory-float(inv)
    if abs(delta)>0.0001:
        c=conn()
        c.execute("""INSERT INTO inventory_lots
            (movement_date,line,item_type,format,qty_units,kg,movement_type,source,notes)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (str(date.today()),"Estate","Vasetti","1 kg",abs(delta),abs(delta),
             "Carico" if delta>0 else "Scarico","Rettifica",
             "Allineamento giacenza reale concordata: 12 vasetti da 1 kg"))
        c.commit(); c.close()
    meta_set(marker,datetime.now().isoformat())


def page_magazzino():
    st.title("🍯 Magazzino")
    fl=st.segmented_control("Vista",["Tutto","Estate","Natale"],default="Tutto",key="mag_view")

    rows=jar_stock(fl)
    df=pd.DataFrame(rows)

    # Riepilogo immediato
    bulk=bulk_stock(None if fl=="Tutto" else fl)
    bulk_kg=sum(float(r["Kg residui"] or 0) for r in bulk) if bulk else 0.0
    jar_kg=sum(max(0.0,float(r["Kg invasettati residui"] or 0)) for r in rows)
    jar_count=sum(max(0.0,float(r["Residuo vasetti"] or 0)) for r in rows)
    stock_value=0.0
    for r in rows:
        if float(r["Residuo vasetti"] or 0)>0:
            stock_value += float(r["Residuo vasetti"])*FORMATS[r["Formato"]][1]

    a,b,c=st.columns(3)
    a.metric("🍯 Miele sfuso",f"{bulk_kg:.1f} kg")
    b.metric("🫙 Vasetti disponibili",f"{int(jar_count)}")
    c.metric("💶 Valore stock a listino",euro(stock_value))

    if any(float(r["Residuo vasetti"] or 0)<0 for r in rows):
        st.error("⚠️ Ci sono giacenze negative: significa che risultano più vasetti venduti/omaggiati di quelli caricati in magazzino. Le righe interessate sono evidenziate sotto.")

    show=df.copy()
    if not show.empty:
        show["Residuo vasetti"]=show["Residuo vasetti"].apply(lambda x: f"⚠️ {x}" if float(x)<0 else x)
    st.dataframe(show,hide_index=True,use_container_width=True)

    st.subheader("Miele sfuso")
    bulk_df=pd.DataFrame(bulk)
    st.dataframe(bulk_df,hide_index=True,use_container_width=True)

    with st.expander("🏺 Registra invasettamento",expanded=False):
        with st.form("bottling"):
            c1,c2,c3=st.columns(3)
            dt=c1.date_input("Data",date.today())
            ln=c2.selectbox("Linea",LINES,index=1)
            fmt=c3.selectbox("Formato",list(FORMATS.keys()),index=1)
            qty=st.number_input("Numero vasetti riempiti",min_value=1,value=10)
            kg=qty*FORMATS[fmt][0]
            st.info(f"Questa operazione userà **{kg:g} kg** di miele sfuso e caricherà **{qty} vasetti {fmt}**.")
            if st.form_submit_button("Registra invasettamento"):
                available=bulk_stock(ln)
                if kg>available:
                    st.error(f"Miele sfuso insufficiente: disponibili {available:g} kg.")
                else:
                    c=conn()
                    c.execute("""INSERT INTO inventory_lots
                    (movement_date,line,item_type,format,qty_units,kg,movement_type,source,notes)
                    VALUES(?,?,?,?,?,?,?,?,?)""",
                    (str(dt),ln,"Miele sfuso",None,0,kg,"Scarico","Invasettamento",f"{qty} x {fmt}"))
                    c.execute("""INSERT INTO inventory_lots
                    (movement_date,line,item_type,format,qty_units,kg,movement_type,source,notes)
                    VALUES(?,?,?,?,?,?,?,?,?)""",
                    (str(dt),ln,"Vasetti",fmt,qty,kg,"Invasettamento","Produzione","Da miele sfuso"))
                    c.commit(); c.close(); st.rerun()

    with st.expander("✏️ Modifica o elimina dati di magazzino",expanded=False):
        edit_inventory()

def page_vendite():
    st.title("🧾 Vendite")
    with st.expander("➕ Nuova vendita / omaggio",expanded=True):
        with st.form("sale",clear_on_submit=True):
            a,b,c,d=st.columns(4)
            dt=a.date_input("Data",date.today())
            ln=b.selectbox("Linea",LINES)
            customer=c.text_input("Cliente")
            fmt=d.selectbox("Formato",list(FORMATS))
            a,b,c,d=st.columns(4)
            qty=a.number_input("Q.tà venduta",0,1000,1)
            gift=b.number_input("Q.tà omaggio",0,1000,0)
            unit=c.number_input("Prezzo unitario €",0.0,1000.0,FORMATS[fmt][1],0.5)
            discount=d.number_input("Sconto totale €",0.0,10000.0,0.0,0.5)
            list_total=qty*unit
            actual=max(0,list_total-discount)
            st.caption(f"Listino {euro(list_total)} → sconto {euro(discount)} → totale effettivo **{euro(actual)}**")
            paid=st.selectbox("Mi ha pagato?",["No","Sì"])
            method=collected=""
            if paid=="Sì":
                x,y=st.columns(2)
                method=x.selectbox("Con che metodo?",PAY_METHODS)
                collected=y.selectbox("Incassato da",PEOPLE)
            notes=st.text_input("Note")
            if st.form_submit_button("Registra vendita"):
                available=jar_stock(ln).get((ln,fmt),0)
                needed=qty+gift
                if not customer.strip():
                    st.error("Inserisci il cliente.")
                elif needed>available:
                    st.error(f"Scorta insufficiente: disponibili {available:g} vasetti {fmt} {ln}.")
                else:
                    c=conn()
                    c.execute("""INSERT INTO sales
                    (sale_date,line,customer,format,qty,gift_qty,list_unit_price,discount,
                     actual_total,paid,payment_method,collected_by,notes)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (str(dt),ln,customer.strip(),fmt,qty,gift,unit,discount,actual,
                     1 if paid=="Sì" else 0,method,collected,notes))
                    c.commit(); c.close(); st.rerun()

    a,b,c=st.columns(3)
    fl=a.selectbox("Linea",["Tutto"]+LINES)
    status=b.selectbox("Stato",["Tutti","Pagato","Da incassare","Con sconto","Omaggi"])
    search=c.text_input("Cerca cliente")
    sql="""SELECT id,sale_date Data,line Linea,customer Cliente,format Formato,
           qty Quantità,gift_qty Omaggi,list_unit_price Prezzo_unitario,
           discount Sconto,actual_total Totale,
           CASE paid WHEN 1 THEN 'Sì' ELSE 'No' END Pagato,
           payment_method Metodo,collected_by Incassato_da,notes Note
           FROM sales WHERE 1=1"""
    args=[]
    if fl!="Tutto": sql+=" AND line=?"; args.append(fl)
    if status=="Pagato": sql+=" AND paid=1"
    elif status=="Da incassare": sql+=" AND paid=0 AND qty>0"
    elif status=="Con sconto": sql+=" AND discount>0"
    elif status=="Omaggi": sql+=" AND gift_qty>0"
    if search: sql+=" AND customer LIKE ?"; args.append("%"+search+"%")
    sql+=" ORDER BY sale_date DESC,id DESC"
    st.dataframe(pd.DataFrame(query(sql,args)),hide_index=True,use_container_width=True)
    st.subheader("Riepilogo")
    kpis(financials(fl))
    with st.expander("✏️ Modifica o elimina una vendita",expanded=False):
        edit_sale()

def cost_form():
    with st.form("cost",clear_on_submit=True):
        a,b,c,d=st.columns(4)
        dt=a.date_input("Data",date.today(),key="costdate")
        ln=b.selectbox("Attribuzione",["Estate","Natale","Generale Apiario"])
        cat=c.selectbox("Categoria",COST_CATS)
        status=d.selectbox("Tipo costo",COST_STATUS)
        desc=st.text_input("Voce di costo")
        a,b,c=st.columns(3)
        qty=a.number_input("Quantità",0.0,100000.0,1.0)
        unit=b.number_input("Costo unitario €",0.0,100000.0,0.0)
        paidby=c.selectbox("Pagato da",PEOPLE)
        notes=st.text_input("Note")
        if st.form_submit_button("Registra costo"):
            c=conn()
            c.execute("""INSERT INTO costs(cost_date,line,category,description,qty,unit_cost,total,status,paid_by,notes)
                         VALUES(?,?,?,?,?,?,?,?,?,?)""",
                      (str(dt),ln,cat,desc,qty,unit,qty*unit,status,paidby,notes))
            c.commit(); c.close(); st.rerun()

def simulator():
    st.subheader("🧪 Simulatore invasettamento Natale")
    available=bulk_stock("Natale")
    st.caption(f"Miele sfuso Natale disponibile adesso: **{available:g} kg**. Prezzi vetro noti: 500 g = €0,45; 250 g = €0,35.")
    maxkg=float(max(0,available))
    a,b=st.columns(2)
    kg500=a.number_input("Kg da destinare ai 500 g",0.0,maxkg,min(maxkg,35.0),0.5)
    remaining=max(0,maxkg-kg500)
    kg250=b.number_input("Kg da destinare ai 250 g",0.0,remaining,min(remaining,15.0),0.25)
    loose=maxkg-kg500-kg250
    n500=int(kg500/0.5)
    n250=int(kg250/0.25)
    glass=n500*0.45+n250*0.35
    revenue=n500*10+n250*6
    honey_cost=(kg500+kg250)*8
    contribution=revenue-honey_cost-glass
    a,b,c,d,e=st.columns(5)
    a.metric("500 g da comprare",n500)
    b.metric("250 g da comprare",n250)
    c.metric("Costo vetro previsto",euro(glass))
    d.metric("Ricavo potenziale",euro(revenue))
    e.metric("Miele lasciato sfuso",f"{loose:g} kg")
    st.info(f"Su questa simulazione: costo miele attribuito {euro(honey_cost)} + vetro {euro(glass)}. Margine potenziale prima di etichette/altri costi: **{euro(contribution)}**.")

    if st.button("Salva il vetro simulato come COSTO PREVISIONALE"):
        c=conn()
        today=str(date.today())
        if n500:
            c.execute("""INSERT INTO costs(cost_date,line,category,description,qty,unit_cost,total,status,paid_by,notes)
            VALUES(?,?,?,?,?,?,?,?,?,?)""",(today,"Natale","Vasetti / invasettamento",
            "Vasetti 500 g - simulazione",n500,.45,n500*.45,"Previsionale","Cassa comune","Generato dal simulatore"))
        if n250:
            c.execute("""INSERT INTO costs(cost_date,line,category,description,qty,unit_cost,total,status,paid_by,notes)
            VALUES(?,?,?,?,?,?,?,?,?,?)""",(today,"Natale","Vasetti / invasettamento",
            "Vasetti 250 g - simulazione",n250,.35,n250*.35,"Previsionale","Cassa comune","Generato dal simulatore"))
        c.commit(); c.close()
        st.success("Previsione salvata. Quando comprerete davvero i vasetti, trasformate/eliminate la previsione e registrate il costo effettivo.")

def page_cassa():
    st.title("💶 Costi & Cassa")
    tab_est,tab_nat,tab_gen,tab_hist,tab_sim=st.tabs(
        ["☀️ Estate","🎄 Natale","📊 Generale","📈 Storico & Analisi","🧪 Simulatore"]
    )

    for tab,ln in [(tab_est,"Estate"),(tab_nat,"Natale"),(tab_gen,"Tutto")]:
        with tab:
            f=financials(ln)
            kpis(f)
            if ln=="Natale":
                ancora=max(0.0,float(f["costi_eff"])-float(f["incassato"]))
                st.markdown("#### 🎄 Stato investimento Natale")
                a,b,c=st.columns(3)
                a.metric("Investimento / costi",euro(f["costi_eff"]))
                b.metric("Recuperato con incassi",euro(f["incassato"]))
                c.metric("Ancora da recuperare",euro(ancora))
            coverage=(f["incassato"]/f["costi_eff"]*100) if f["costi_eff"] else 0
            st.progress(min(1.0,coverage/100),text=f"Copertura costi effettivi con incassi reali: {coverage:.1f}%")
            st.subheader("Registro costi")
            if ln=="Tutto":
                rows=query("""SELECT id,cost_date Data,line Linea,category Categoria,description Voce,
                qty Quantità,unit_cost Costo_unitario,total Totale,status Tipo,p aid_by
                FROM costs ORDER BY cost_date DESC,id DESC""".replace("p aid_by","paid_by Pagato_da"))
            else:
                rows=query("""SELECT id,cost_date Data,line Linea,category Categoria,description Voce,
                qty Quantità,unit_cost Costo_unitario,total Totale,status Tipo,paid_by Pagato_da,notes Note
                FROM costs WHERE line=? ORDER BY cost_date DESC,id DESC""",(ln,))
            st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)

    with tab_gen:
        st.divider()
        st.subheader("➕ Nuovo costo")
        cost_form()
        st.subheader("Movimenti personali / cassa")
        with st.form("cash",clear_on_submit=True):
            a,b,c=st.columns(3)
            dt=a.date_input("Data movimento",date.today(),key="cashdate")
            person=b.selectbox("Persona",["Chiara","Annalisa"])
            typ=c.selectbox("Movimento",["Prelievo da restituire","Restituzione prelievo","Anticipo personale","Rimborso anticipo","Rettifica +","Rettifica -"])
            amount=st.number_input("Importo €",0.0,100000.0,0.0,1.0)
            notes=st.text_input("Motivo / note")
            if st.form_submit_button("Registra movimento"):
                cc=conn()
                cc.execute("INSERT INTO cash_moves(move_date,person,type,amount,notes) VALUES(?,?,?,?,?)",
                           (str(dt),person,typ,amount,notes))
                cc.commit(); cc.close(); st.rerun()
        st.dataframe(pd.DataFrame(query("""SELECT move_date Data,person Persona,type Movimento,amount Importo,notes Note
                                          FROM cash_moves ORDER BY move_date DESC,id DESC""")),
                     hide_index=True,use_container_width=True)
        st.subheader("Situazione personale")
        a,b=st.columns(2)
        a.metric("Chiara · saldo movimenti",euro(personal_balance("Chiara")))
        b.metric("Annalisa · saldo movimenti",euro(personal_balance("Annalisa")))
        st.caption("Positivo = importo da restituire alla cassa. Negativo = anticipo personale ancora da rimborsare.")
        with st.expander("✏️ Modifica o elimina un costo",expanded=False):
            edit_cost()
        with st.expander("✏️ Modifica o elimina un movimento personale",expanded=False):
            edit_cash_move()

    with tab_hist:
        st.subheader("Andamento mensile")
        sales=pd.DataFrame(query("""SELECT substr(sale_date,1,7) Mese,
             SUM(actual_total) Vendite,
             SUM(CASE WHEN paid=1 THEN actual_total ELSE 0 END) Incassi,
             SUM(discount) Sconti
             FROM sales WHERE length(sale_date)>=7 GROUP BY 1 ORDER BY 1"""))
        costs=pd.DataFrame(query("""SELECT substr(cost_date,1,7) Mese,
             SUM(CASE WHEN status='Effettivo' THEN total ELSE 0 END) Costi
             FROM costs WHERE length(cost_date)>=7 GROUP BY 1 ORDER BY 1"""))
        if not sales.empty or not costs.empty:
            hist=pd.merge(sales,costs,on="Mese",how="outer").fillna(0).sort_values("Mese")
            hist["Risultato"]=hist["Vendite"]-hist["Costi"]
            st.line_chart(hist.set_index("Mese")[["Incassi","Costi"]])
            st.bar_chart(hist.set_index("Mese")[["Risultato"]])
            st.dataframe(hist,hide_index=True,use_container_width=True)
        else:
            st.info("Servono date valide nello storico per costruire i grafici.")

        st.subheader("Indicatori per migliorare")
        fmt=pd.DataFrame(query("""SELECT format Formato,SUM(qty) Vasetti,
          SUM(qty*list_unit_price) Listino,SUM(discount) Sconti,SUM(actual_total) Ricavi
          FROM sales GROUP BY format ORDER BY Vasetti DESC"""))
        if not fmt.empty: st.dataframe(fmt,hide_index=True,use_container_width=True)
        st.caption("Questi indicatori sono descrittivi: servono a capire quali formati girano, quanto pesano gli sconti e come evolve la copertura dei costi.")

    with tab_sim:
        simulator()


def file_hash(data: bytes):
    return hashlib.sha256(data).hexdigest()

def export_excel_bytes():
    bio=io.BytesIO()
    with pd.ExcelWriter(bio,engine="openpyxl") as w:
        pd.DataFrame(query("""SELECT sale_date Data,line Linea,customer Cliente,format Formato,
        qty Quantità,gift_qty Omaggi,list_unit_price Prezzo_unitario,discount Sconto,
        actual_total Totale,paid Pagato,payment_method Metodo,collected_by Incassato_da,notes Note
        FROM sales ORDER BY sale_date,id""")).to_excel(w, sheet_name="Vendite", index=False)
        pd.DataFrame(query("""SELECT cost_date Data,line Linea,category Categoria,description Voce,
        qty Quantità,unit_cost Costo_unitario,total Totale,status Tipo,paid_by Pagato_da,notes Note
        FROM costs ORDER BY cost_date,id""")).to_excel(w, sheet_name="Costi e Cassa", index=False)
        pd.DataFrame(query("""SELECT movement_date Data,line Linea,item_type Tipo,format Formato,
        qty_units Quantità,kg Kg,movement_type Movimento,source Origine,notes Note
        FROM inventory_lots ORDER BY movement_date,id""")).to_excel(w, sheet_name="Magazzino", index=False)
        pd.DataFrame(query("""SELECT move_date Data,person Persona,type Movimento,amount Importo,notes Note
        FROM cash_moves ORDER BY move_date,id""")).to_excel(w, sheet_name="Movimenti personali", index=False)
    return bio.getvalue()

def norm(s):
    return str(s).strip().lower().replace("\\n"," ").replace("_"," ")

def col(df,*names):
    m={norm(c):c for c in df.columns}
    for n in names:
        if norm(n) in m: return m[norm(n)]
    return None

def import_history(upload):
    """Importatore specifico per Gestione_vendita_miele_completa.xlsm."""
    data=upload.getvalue()
    h=file_hash(data)
    marker="clas_excel_specific_"+h

    if meta_get(marker):
        return False,"Questo identico Excel CLAS è già stato importato."

    try:
        xls=pd.ExcelFile(io.BytesIO(data), engine="openpyxl")
    except Exception as e:
        return False,f"Impossibile leggere l'Excel: {e}"

    required={"Vendite","Costi","Cassa","Magazzino"}
    missing=required-set(xls.sheet_names)
    if missing:
        return False,"Mancano i fogli richiesti: "+", ".join(sorted(missing))

    db=conn()
    try:
        report=[]

        # ---------- VENDITE ----------
        # Il file reale ha le intestazioni alla riga Excel 2.
        vend=pd.read_excel(xls,"Vendite",header=1)
        expected={"Cliente / destinatario","Formato","Quantità venduta",
                  "Quantità omaggio","Prezzo unitario","Totale ordine",
                  "Metodo pagamento","Pagato?","Contanti","Satispay","PayPal",
                  "Incassato da","Note"}
        if not expected.issubset(set(vend.columns)):
            raise ValueError("Struttura del foglio Vendite diversa da quella CLAS attesa.")

        n_sales=0
        for idx,r in vend.iterrows():
            customer=str(r.get("Cliente / destinatario","")).strip()
            fmt=str(r.get("Formato","")).strip()
            if not customer or customer.lower()=="nan" or fmt not in FORMATS:
                continue

            def num(v):
                try:
                    if pd.isna(v): return 0.0
                    return float(v)
                except: return 0.0

            qty=int(num(r.get("Quantità venduta")))
            gift=int(num(r.get("Quantità omaggio")))
            if qty<=0 and gift<=0:
                continue

            unit=num(r.get("Prezzo unitario")) or FORMATS[fmt][1]
            order_total=num(r.get("Totale ordine"))
            paid_txt=str(r.get("Pagato?","")).strip().lower()
            is_paid=1 if paid_txt in ("sì","si","yes","true","1") else 0

            cash=num(r.get("Contanti"))
            satis=num(r.get("Satispay"))
            paypal=num(r.get("PayPal"))
            received=cash+satis+paypal

            # Francesca Rocchi e qualsiasi altro caso analogo:
            # se il pagamento reale è inferiore al totale ordine, la differenza è sconto.
            actual_total=received if is_paid and received>0 else order_total
            list_total=qty*unit
            discount=max(0.0,list_total-actual_total)

            method=str(r.get("Metodo pagamento","")).strip()
            if method.lower()=="nan": method=""
            if not method and is_paid:
                used=[]
                if cash: used.append("Contanti")
                if satis: used.append("Satispay")
                if paypal: used.append("PayPal")
                method=" + ".join(used)

            collector=str(r.get("Incassato da","")).strip()
            if collector.lower()=="nan": collector=""

            note=str(r.get("Note","")).strip()
            if note.lower()=="nan": note=""

            # Le righe esplicitamente annotate "Natale" restano Natale;
            # tutte le altre appartengono allo storico Estate.
            line="Natale" if "natale" in note.lower() else "Estate"

            fp=f"CLASXLS:{h[:12]}:V:{idx}"
            db.execute("""INSERT INTO sales
                (sale_date,line,customer,format,qty,gift_qty,list_unit_price,
                 discount,actual_total,paid,payment_method,collected_by,notes)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                ("2026-09-25",line,customer,fmt,qty,gift,unit,discount,
                 actual_total,is_paid,method,collector,
                 (note+" | " if note else "")+fp))
            n_sales+=1
        report.append(f"Vendite: {n_sales}")

        # ---------- COSTI ESTATE ----------
        # Intestazioni reali alla riga Excel 3.
        costs=pd.read_excel(xls,"Costi",header=2,usecols="A:D")
        n_costs=0
        for idx,r in costs.iterrows():
            desc=str(r.iloc[0]).strip() if not pd.isna(r.iloc[0]) else ""
            if not desc or desc.lower()=="nan": continue
            try:
                qty=float(r.iloc[1]) if not pd.isna(r.iloc[1]) else 1.0
                unit=float(r.iloc[2]) if not pd.isna(r.iloc[2]) else 0.0
                total=float(r.iloc[3]) if not pd.isna(r.iloc[3]) else qty*unit
            except: continue
            fp=f"CLASXLS:{h[:12]}:C:{idx}"
            db.execute("""INSERT INTO costs
                (cost_date,line,category,description,qty,unit_cost,total,status,paid_by,notes)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                ("2026-09-25","Estate","Altro",desc,qty,unit,total,
                 "Effettivo","Cassa comune",fp))
            n_costs+=1
        report.append(f"Costi Estate: {n_costs}")

        # ---------- MOVIMENTI PERSONALI / CASSA ----------
        # La tabella movimenti parte dalla riga Excel 10.
        cash=pd.read_excel(xls,"Cassa",header=9,usecols="A:F")
        n_cash=0
        for idx,r in cash.iterrows():
            person=str(r.iloc[0]).strip() if not pd.isna(r.iloc[0]) else ""
            movement=str(r.iloc[1]).strip() if not pd.isna(r.iloc[1]) else ""
            if person not in ("Chiara","Annalisa") or not movement:
                continue
            try: amount=float(r.iloc[2])
            except: continue

            if movement.lower().startswith("anticipo"):
                typ="Anticipo personale"
            elif movement.lower().startswith("rimborso"):
                typ="Rimborso anticipo"
            else:
                typ="Rettifica +"

            descr=str(r.iloc[4]).strip() if not pd.isna(r.iloc[4]) else ""
            note=str(r.iloc[5]).strip() if not pd.isna(r.iloc[5]) else ""
            fp=f"CLASXLS:{h[:12]}:M:{idx}"
            db.execute("""INSERT INTO cash_moves(move_date,person,type,amount,notes)
                          VALUES(?,?,?,?,?)""",
                       ("2026-09-25",person,typ,amount,
                        " | ".join(x for x in [descr,note,fp] if x)))
            n_cash+=1
        report.append(f"Movimenti personali: {n_cash}")

        # ---------- MAGAZZINO ESTATE ----------
        # Importiamo SOLO la base Estate. La vecchia simulazione Natale viene ignorata.
        mag=pd.read_excel(xls,"Magazzino",header=1,usecols="A:K")
        n_inv=0
        current_section=None
        for idx,r in mag.iterrows():
            first=str(r.iloc[0]).strip() if not pd.isna(r.iloc[0]) else ""
            if first=="Miele Estate": current_section="Estate"
            elif first=="Miele Natale": current_section="Natale"

            if current_section!="Estate": continue
            fmt=str(r.iloc[1]).strip() if not pd.isna(r.iloc[1]) else ""
            if fmt not in FORMATS: continue
            try: available=float(r.iloc[3])
            except: continue

            fp=f"CLASXLS:{h[:12]}:I:{idx}"
            db.execute("""INSERT INTO inventory_lots
                (movement_date,line,item_type,format,qty_units,kg,movement_type,source,notes)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                ("2026-09-25","Estate","Vasetti",fmt,available,
                 available*FORMATS[fmt][0],"Carico","Storico Excel",fp))
            n_inv+=1

        # Decisione successiva all'Excel: i vasetti Estate da 1 kg realmente residui sono 12.
        # Con lo storico Excel (45 iniziali - 21 venduti = 24) serve una rettifica tracciata di -12.
        db.execute("""INSERT INTO inventory_lots
            (movement_date,line,item_type,format,qty_units,kg,movement_type,source,notes)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            ("2026-09-25","Estate","Vasetti","1 kg",12,12,
             "Scarico","Rettifica",
             f"Rettifica concordata: residuo reale 12 vasetti da 1 kg | CLASXLS:{h[:12]}:RETT1KG"))
        report.append(f"Righe magazzino Estate: {n_inv} + rettifica 1 kg")

        # Natale del vecchio Excel NON viene importato:
        # resta il dato reale dell'app: 50 kg sfusi, 2 secchi da 25 kg, costo €400.
        db.commit()
        meta_set(marker,datetime.now().isoformat())
        report.append("Natale vecchio Excel ignorato; mantenuti i 50 kg sfusi reali")
        return True," | ".join(report)

    except Exception as e:
        db.rollback()
        return False,f"Importazione annullata senza modifiche: {e}"
    finally:
        db.close()

def data_admin():
    st.write("**Storico CLAS**")
    st.success("Migrazione storico completata. Il database è ora la fonte ufficiale dei dati.")
    st.caption("L'importazione dello storico Excel è stata disattivata per evitare duplicazioni.")

    st.divider()
    st.write("**Export e backup**")

    if st.button("Prepara export Excel", key="prepare_excel_export"):
        try:
            st.session_state["excel_export_bytes"] = export_excel_bytes()
            st.success("Export Excel pronto.")
        except Exception as e:
            st.error(f"Impossibile preparare l'export Excel: {e}")

    if st.session_state.get("excel_export_bytes"):
        st.download_button(
            "⬇️ Scarica gestionale in Excel",
            data=st.session_state["excel_export_bytes"],
            file_name=f"CLAS_export_{date.today()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_excel_export"
        )

    if DB_PATH.exists():
        st.download_button(
            "🗄️ Backup database",
            data=DB_PATH.read_bytes(),
            file_name=f"gestione_miele_{date.today()}.db",
            mime="application/octet-stream",
            key="download_db_backup"
        )

    st.caption("Il codice va su Git. Il database operativo va salvato con backup, non versionato nel repository.")

def sidebar_admin():
    st.sidebar.title("CLAS 🍯")
    st.sidebar.caption("Gestione miele • obiettivo: apiario autosufficiente")
    with st.sidebar.expander("⚙️ Dati iniziali / migrazione"):
        st.write("Dato certo 25/09/2026:")
        st.write("• 50 kg miele Natale")
        st.write("• 2 secchi da 25 kg")
        st.write("• €8/kg = €400 effettivi")
        if not meta_get("update_2026_09_25"):
            if st.button("Applica aggiornamento reale 25/09"):
                apply_known_update(); st.rerun()
        else:
            st.success("Aggiornamento 25/09 già applicato.")
    with st.sidebar.expander("📦 Import / Export / Backup"):
        data_admin()

init_db()
# Per un DB nuovo applica subito i dati reali; su DB esistente il marker evita duplicati.
apply_known_update()
sidebar_admin()

reconcile_known_stock()

page=st.sidebar.radio("Sezione",["Magazzino","Vendite","Costi & Cassa"])
if page=="Magazzino": page_magazzino()
elif page=="Vendite": page_vendite()
else: page_cassa()

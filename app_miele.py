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
    wh="WHERE item_type='Vasetti'"
    args=[]
    if line and line!="Tutto":
        wh+=" AND line=?"; args.append(line)
    moves=query(f"""SELECT line,format,
        SUM(CASE WHEN movement_type IN ('Carico','Invasettamento') THEN qty_units ELSE -qty_units END) stock
        FROM inventory_lots {wh}
        GROUP BY line,format""",args)
    stock={(r["line"],r["format"]):float(r["stock"] or 0) for r in moves}
    # scala vendite/omaggi
    swh="WHERE 1=1"; sargs=[]
    if line and line!="Tutto":
        swh+=" AND line=?"; sargs.append(line)
    sold=query(f"""SELECT line,format,SUM(qty+gift_qty) used
                   FROM sales {swh} GROUP BY line,format""",sargs)
    for r in sold:
        k=(r["line"],r["format"])
        stock[k]=stock.get(k,0)-float(r["used"] or 0)
    return stock

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
    cols=st.columns(7)
    data=[
        ("Vendite effettive",f["vendite"]),
        ("Sconti",f["sconti"]),
        ("Incassato",f["incassato"]),
        ("Da incassare",f["credito"]),
        ("Costi effettivi",f["costi_eff"]),
        ("Costi previsti",f["costi_prev"]),
        ("Risultato*",f["vendite"]-f["costi_eff"])
    ]
    for c,(lab,val) in zip(cols,data): c.metric(lab,euro(val))
    st.caption("* Risultato gestionale semplice: vendite registrate meno costi effettivi. Non è un utile fiscale.")

def page_magazzino():
    st.title("🍯 Magazzino")
    line=st.segmented_control("Vista",["Tutto","Estate","Natale"],default="Tutto")
    bulk=bulk_stock(line)
    stock=jar_stock(line)
    a,b,c=st.columns(3)
    a.metric("Miele sfuso disponibile",f"{bulk:g} kg")
    c.metric("Vasetti disponibili",int(sum(max(0,v) for v in stock.values())))
    kg_jars=sum(max(0,v)*FORMATS.get(fmt,(0,0))[0] for (ln,fmt),v in stock.items())
    b.metric("Miele già invasettato",f"{kg_jars:g} kg")

    rows=[]
    for (ln,fmt),qty in sorted(stock.items()):
        rows.append({"Linea":ln,"Formato":fmt,"Residuo vasetti":qty,
                     "Kg invasettati residui":qty*FORMATS.get(fmt,(0,0))[0]})
    if rows:
        st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)

    st.subheader("Miele sfuso")
    lots=query("""SELECT movement_date Data,line Linea,qty_units Secchi,kg Kg,
                  movement_type Movimento,source Origine,notes Note
                  FROM inventory_lots WHERE item_type='Miele sfuso'
                  ORDER BY id DESC""")
    st.dataframe(pd.DataFrame(lots),hide_index=True,use_container_width=True)

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
    kpis(financials(fl))

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
    data=upload.getvalue()
    h=file_hash(data)
    if meta_get("excel_import_"+h):
        return False,"Questo identico Excel è già stato importato."
    xls=pd.ExcelFile(io.BytesIO(data))
    report=[]
    db=conn()
    try:
        # Importa vendite solo da un foglio chiaramente riconoscibile.
        vs=next((s for s in xls.sheet_names if "vend" in s.lower()),None)
        if vs:
            df=pd.read_excel(xls,vs)
            customer=col(df,"Cliente","Nominativo")
            linec=col(df,"Linea","Stagione")
            datec=col(df,"Data","Data vendita")
            paidc=col(df,"Pagato","Incassato")
            methodc=col(df,"Metodo","Metodo pagamento","Pagamento")
            collectc=col(df,"Incassato da")
            fmtc=col(df,"Formato")
            qtyc=col(df,"Quantità","Q.tà","Qta")
            q1=col(df,"1 kg","1kg")
            q5=col(df,"500 g","500gr")
            q25=col(df,"250 g","250gr")
            inserted=0
            if customer:
                for idx,r in df.iterrows():
                    cust=str(r.get(customer,"")).strip()
                    if not cust or cust.lower()=="nan": continue
                    ln=str(r.get(linec,"Estate")).strip() if linec else "Estate"
                    if ln not in LINES: ln="Estate"
                    dt=str(r.get(datec,date.today()))[:10] if datec else str(date.today())
                    paidtxt=str(r.get(paidc,"")).strip().lower() if paidc else ""
                    ispaid=1 if paidtxt in ("si","sì","1","true","pagato","yes") else 0
                    method=str(r.get(methodc,"")) if methodc else ""
                    collector=str(r.get(collectc,"")) if collectc else ""
                    items=[]
                    if fmtc:
                        f=str(r.get(fmtc,"")).strip()
                        try:q=int(float(r.get(qtyc,1) or 0)) if qtyc else 1
                        except:q=0
                        items=[(f,q)]
                    else:
                        for cc,f in [(q1,"1 kg"),(q5,"500 g"),(q25,"250 g")]:
                            if cc:
                                try:q=int(float(r.get(cc,0) or 0))
                                except:q=0
                                if q:items.append((f,q))
                    for f,q in items:
                        if f not in FORMATS or q<=0:continue
                        fp=f"IMPORT:{h[:10]}:{idx}:{f}"
                        if db.execute("SELECT 1 FROM sales WHERE notes LIKE ?",("%"+fp+"%",)).fetchone():continue
                        total=q*FORMATS[f][1]
                        db.execute("""INSERT INTO sales
                        (sale_date,line,customer,format,qty,gift_qty,list_unit_price,discount,
                        actual_total,paid,payment_method,collected_by,notes)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (dt,ln,cust,f,q,0,FORMATS[f][1],0,total,ispaid,method,collector,fp))
                        inserted+=1
                report.append(f"Vendite importate: {inserted}")
            else: report.append("Vendite non importate: colonne non riconosciute.")

        cs=next((s for s in xls.sheet_names if "cost" in s.lower() or "cassa" in s.lower()),None)
        if cs:
            df=pd.read_excel(xls,cs)
            desc=col(df,"Voce di costo","Voce","Descrizione")
            totalc=col(df,"Totale","Importo","Costo")
            linec=col(df,"Linea","Stagione")
            datec=col(df,"Data")
            inserted=0
            if desc and totalc:
                for idx,r in df.iterrows():
                    d=str(r.get(desc,"")).strip()
                    if not d or d.lower()=="nan":continue
                    try:val=float(r.get(totalc,0) or 0)
                    except:continue
                    if val==0:continue
                    ln=str(r.get(linec,"Generale Apiario")).strip() if linec else "Generale Apiario"
                    if ln not in ["Estate","Natale","Generale Apiario"]:ln="Generale Apiario"
                    dt=str(r.get(datec,date.today()))[:10] if datec else str(date.today())
                    fp=f"IMPORT:{h[:10]}:{idx}"
                    if db.execute("SELECT 1 FROM costs WHERE notes LIKE ?",("%"+fp+"%",)).fetchone():continue
                    db.execute("""INSERT INTO costs
                    (cost_date,line,category,description,qty,unit_cost,total,status,paid_by,notes)
                    VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (dt,ln,"Altro",d,1,val,val,"Effettivo","Cassa comune",fp))
                    inserted+=1
                report.append(f"Costi importati: {inserted}")
            else: report.append("Costi non importati: colonne non riconosciute.")
        db.commit()
        meta_set("excel_import_"+h,datetime.now().isoformat())
        return True," | ".join(report) if report else "File letto; nessun foglio riconosciuto."
    except Exception as e:
        db.rollback()
        return False,f"Importazione annullata senza modifiche: {e}"
    finally:
        db.close()

def data_admin():
    st.write("**Migrazione dello storico**")
    up=st.file_uploader("Excel storico (.xlsx / .xlsm / .xls)",type=["xlsx","xlsm","xls"])
    if up and st.button("Importa storico Excel"):
        ok,msg=import_history(up)
        (st.success if ok else st.warning)(msg)
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
        st.download_button("🗄️ Backup database",DB_PATH.read_bytes(),
            file_name=f"gestione_miele_{date.today()}.db",mime="application/octet-stream")
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

page=st.sidebar.radio("Sezione",["Magazzino","Vendite","Costi & Cassa"])
if page=="Magazzino": page_magazzino()
elif page=="Vendite": page_vendite()
else: page_cassa()

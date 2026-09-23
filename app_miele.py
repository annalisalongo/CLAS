import streamlit as st
import sqlite3, json, os
from datetime import date
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / 'gestione_miele.db'
SEED_PATH = APP_DIR / 'honey_seed.json'

st.set_page_config(page_title='CLAS • Gestione Miele', page_icon='🍯', layout='wide')
st.markdown('''<style>
.block-container{padding-top:1.25rem;padding-bottom:2rem}.kpi{background:#fff;border:1px solid #e8e1d6;border-radius:14px;padding:14px 16px;box-shadow:0 1px 4px #0000000a}.small{color:#6b7280;font-size:.86rem}.big{font-size:1.55rem;font-weight:750}.estate{border-left:5px solid #d99a00}.natale{border-left:5px solid #a61b1b}.ok{color:#18794e}.warn{color:#b45309}.bad{color:#b91c1c}
[data-testid="stMetric"]{background:#fff;border:1px solid #eee7dc;padding:12px;border-radius:14px}
</style>''', unsafe_allow_html=True)

FORMATS = {'1 kg': (1.0,18.0), '500 g':(0.5,10.0), '250 g':(0.25,6.0)}
LINES = ['Estate','Natale']
PAY_METHODS = ['Contanti','PayPal','Satispay','Bonifico','Altro']
PEOPLE = ['Cassa comune','Chiara','Annalisa']
COST_CATS = ['Miele acquistato','Vasetti / invasettamento','Etichette / packaging','Smielatura','Laboratorio / pulizia','Trattamenti api','Nutrizione','Attrezzatura','Trasporto','Altro']

def conn():
    c=sqlite3.connect(DB_PATH)
    c.row_factory=sqlite3.Row
    return c

def init_db():
    c=conn(); q=c.cursor()
    q.executescript('''
    CREATE TABLE IF NOT EXISTS inventory(id INTEGER PRIMARY KEY, line TEXT, format TEXT, weight_kg REAL, opening_qty INTEGER, note TEXT, UNIQUE(line,format));
    CREATE TABLE IF NOT EXISTS sales(id INTEGER PRIMARY KEY, sale_date TEXT, line TEXT, customer TEXT, format TEXT, qty INTEGER DEFAULT 0, gift_qty INTEGER DEFAULT 0, list_unit_price REAL, discount REAL DEFAULT 0, actual_total REAL, paid INTEGER DEFAULT 0, payment_method TEXT, collected_by TEXT, notes TEXT);
    CREATE TABLE IF NOT EXISTS costs(id INTEGER PRIMARY KEY, cost_date TEXT, line TEXT, category TEXT, description TEXT, qty REAL DEFAULT 1, unit_cost REAL DEFAULT 0, total REAL DEFAULT 0, paid_by TEXT DEFAULT 'Cassa comune', notes TEXT);
    CREATE TABLE IF NOT EXISTS cash_moves(id INTEGER PRIMARY KEY, move_date TEXT, person TEXT, type TEXT, amount REAL, notes TEXT);
    ''')
    c.commit()
    if q.execute('select count(*) n from inventory').fetchone()['n']==0:
        seed(c)
    c.close()

def num(v, default=0.0):
    try: return float(v) if v not in ('',None) else default
    except: return default

def seed(c):
    # Allocation keeps total 127 kg and makes Estate/Natale stock internally coherent.
    inv=[('Estate','1 kg',1,29,'Dopo riclassificazione: 4 vasetti da 1 kg destinati a Natale'),('Estate','500 g',.5,72,''),('Estate','250 g',.25,24,''),('Natale','1 kg',1,4,'4 vasetti della scorta esistente destinati all’ordine Natale'),('Natale','500 g',.5,72,'Seconda tranche; include miele riconfezionato'),('Natale','250 g',.25,64,'Seconda tranche')]
    c.executemany('insert into inventory(line,format,weight_kg,opening_qty,note) values(?,?,?,?,?)',inv)
    if SEED_PATH.exists():
        data=json.load(open(SEED_PATH,encoding='utf-8'))
        for r in data.get('Vendite',[]):
            if r['row']<2: continue
            x=r['cells']; customer=str(x.get('B','')).strip()
            if not customer: continue
            line=x.get('A','Estate') or 'Estate'; fmt=x.get('C','500 g'); qty=int(num(x.get('D'),0)); gift=int(num(x.get('E'),0)); listp=num(x.get('F'),FORMATS.get(fmt,(0,0))[1]); listed=num(x.get('G'),qty*listp)
            paidtxt=str(x.get('I','')).strip().lower(); paid=1 if paidtxt in ('sì','si') else 0
            method=str(x.get('H','')).strip(); collected=str(x.get('M','')).strip(); notes=str(x.get('N','')).strip()
            received=num(x.get('J'))+num(x.get('K'))+num(x.get('L'))
            actual=received if paid and received>0 else listed
            discount=max(0, listed-actual) if paid else 0
            c.execute('''insert into sales(sale_date,line,customer,format,qty,gift_qty,list_unit_price,discount,actual_total,paid,payment_method,collected_by,notes) values(?,?,?,?,?,?,?,?,?,?,?,?,?)''',('',line,customer,fmt,qty,gift,listp,discount,actual,paid,method,collected,notes))
        for r in data.get('Costi e Cassa',[]):
            if 4<=r['row']<=17:
                x=r['cells']; desc=str(x.get('A','')).strip()
                if not desc: continue
                qty=num(x.get('B'),1); unit=num(x.get('C')); total=num(x.get('D'),qty*unit)
                line='Natale' if r['row']>=15 else 'Estate'
                dl=desc.lower()
                cat='Miele acquistato' if 'miele' in dl else ('Vasetti / invasettamento' if 'vasett' in dl or 'invasett' in dl or 'barattol' in dl else ('Smielatura' if 'smiel' in dl else ('Laboratorio / pulizia' if 'pulizia' in dl else 'Altro')))
                c.execute('insert into costs(cost_date,line,category,description,qty,unit_cost,total,paid_by,notes) values(?,?,?,?,?,?,?,?,?)',('',line,cat,desc,qty,unit,total,'Cassa comune','Importato dallo storico Excel'))
    # Current personal cash position requested by user: Chiara took €50 and must return it.
    c.execute("insert into cash_moves(move_date,person,type,amount,notes) values(?,?,?,?,?)",(str(date.today()),'Chiara','Prelievo da restituire',50,'Prelievo personale dalla cassa da reintegrare'))
    c.commit()

def df_rows(rows): return [dict(r) for r in rows]
def euro(x): return f"€ {x:,.2f}".replace(',', 'X').replace('.', ',').replace('X','.')
def query(sql,args=()):
    c=conn(); rows=c.execute(sql,args).fetchall(); c.close(); return rows

def inventory_data(line='Tutto'):
    where='' if line=='Tutto' else 'WHERE i.line=?'; args=() if line=='Tutto' else (line,)
    sql=f'''SELECT i.line AS Linea,i.format AS Formato,i.weight_kg AS Peso_kg,i.opening_qty AS Carico,
    COALESCE(SUM(s.qty),0) AS Venduti,COALESCE(SUM(s.gift_qty),0) AS Omaggi,
    i.opening_qty-COALESCE(SUM(s.qty+s.gift_qty),0) AS Residui,
    ROUND((i.opening_qty-COALESCE(SUM(s.qty+s.gift_qty),0))*i.weight_kg,2) AS Kg_residui
    FROM inventory i LEFT JOIN sales s ON s.line=i.line AND s.format=i.format {where}
    GROUP BY i.id ORDER BY CASE i.line WHEN 'Estate' THEN 1 ELSE 2 END, i.weight_kg DESC'''
    return df_rows(query(sql,args))

def financials(line='Tutto'):
    sw='' if line=='Tutto' else 'WHERE line=?'; args=() if line=='Tutto' else (line,)
    sales=query(f'''SELECT COALESCE(SUM(qty*list_unit_price),0) listino,COALESCE(SUM(discount),0) sconti,COALESCE(SUM(actual_total),0) vendite,
    COALESCE(SUM(CASE WHEN paid=1 THEN actual_total ELSE 0 END),0) incassato,
    COALESCE(SUM(CASE WHEN paid=0 THEN actual_total ELSE 0 END),0) credito FROM sales {sw}''',args)[0]
    costs=query(f'SELECT COALESCE(SUM(total),0) totale FROM costs {sw}',args)[0]['totale']
    return dict(listino=sales['listino'],sconti=sales['sconti'],vendite=sales['vendite'],incassato=sales['incassato'],credito=sales['credito'],costi=costs)

def render_kpis(f):
    cols=st.columns(6)
    vals=[('Vendite effettive',f['vendite']),('Sconti concessi',f['sconti']),('Incassato',f['incassato']),('Da incassare',f['credito']),('Costi',f['costi']),('Risultato su vendite',f['vendite']-f['costi'])]
    for col,(lab,val) in zip(cols,vals): col.metric(lab,euro(val))

def page_magazzino():
    st.title('🍯 Magazzino')
    line=st.segmented_control('Vista',['Tutto','Estate','Natale'],default='Tutto')
    rows=inventory_data(line)
    kg=sum(r['Kg_residui'] for r in rows); jars=sum(r['Residui'] for r in rows); loaded=sum(r['Carico']*r['Peso_kg'] for r in rows); sold=sum(r['Venduti']*r['Peso_kg'] for r in rows)
    a,b,c,d=st.columns(4); a.metric('Kg caricati',f'{loaded:g} kg'); b.metric('Kg venduti',f'{sold:g} kg'); c.metric('Kg residui',f'{kg:g} kg'); d.metric('Vasetti residui',int(jars))
    st.dataframe(rows,use_container_width=True,hide_index=True,column_config={'Peso_kg':st.column_config.NumberColumn('Peso kg',format='%.2f'),'Kg_residui':st.column_config.NumberColumn('Kg residui',format='%.2f')})
    low=[r for r in rows if r['Residui']<=10]
    if low: st.warning('Scorta bassa: '+', '.join(f"{r['Linea']} {r['Formato']} ({r['Residui']})" for r in low))
    with st.expander('➕ Carico / modifica disponibilità iniziale'):
        with st.form('inv'):
            l=st.selectbox('Linea',LINES); fmt=st.selectbox('Formato',list(FORMATS)); qty=st.number_input('Carico totale vasetti',0,10000,1); note=st.text_input('Nota')
            if st.form_submit_button('Salva carico'):
                c=conn(); c.execute('''INSERT INTO inventory(line,format,weight_kg,opening_qty,note) VALUES(?,?,?,?,?) ON CONFLICT(line,format) DO UPDATE SET opening_qty=excluded.opening_qty,note=excluded.note''',(l,fmt,FORMATS[fmt][0],qty,note)); c.commit(); c.close(); st.rerun()

def page_vendite():
    st.title('🧾 Vendite')
    with st.expander('➕ Nuova vendita / omaggio',expanded=True):
        with st.form('sale',clear_on_submit=True):
            c1,c2,c3,c4=st.columns(4); dt=c1.date_input('Data',date.today()); line=c2.selectbox('Linea',LINES); customer=c3.text_input('Cliente'); fmt=c4.selectbox('Formato',list(FORMATS))
            c1,c2,c3,c4=st.columns(4); qty=c1.number_input('Q.tà venduta',0,1000,1); gift=c2.number_input('Q.tà omaggio',0,1000,0); listp=c3.number_input('Prezzo unitario €',0.0,1000.0,FORMATS[fmt][1],0.5); discount=c4.number_input('Sconto totale €',0.0,10000.0,0.0,0.5)
            list_total=qty*listp; actual=max(0.0,list_total-discount)
            st.caption(f'Listino {euro(list_total)}  →  sconto {euro(discount)}  →  **totale effettivo {euro(actual)}**')
            paid=st.selectbox('Mi ha pagato?',['No','Sì','Omaggio' if gift and not qty else 'No'],index=0)
            method=''; collected=''
            if paid=='Sì':
                x,y=st.columns(2); method=x.selectbox('Con che metodo?',PAY_METHODS); collected=y.selectbox('Incassato da',PEOPLE)
            notes=st.text_input('Note')
            if st.form_submit_button('Registra'):
                if not customer.strip(): st.error('Inserisci il cliente/destinatario.')
                else:
                    c=conn(); c.execute('''INSERT INTO sales(sale_date,line,customer,format,qty,gift_qty,list_unit_price,discount,actual_total,paid,payment_method,collected_by,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',(str(dt),line,customer.strip(),fmt,qty,gift,listp,discount,actual,1 if paid=='Sì' else 0,method,collected,notes)); c.commit(); c.close(); st.rerun()
    f1,f2,f3=st.columns(3); fl=f1.selectbox('Filtra linea',['Tutto']+LINES); status=f2.selectbox('Stato',['Tutti','Pagato','Da incassare','Omaggi']); search=f3.text_input('Cerca cliente')
    sql='SELECT id,sale_date Data,line Linea,customer Cliente,format Formato,qty Quantità,gift_qty Omaggi,list_unit_price Listino_unitario,discount Sconto,actual_total Totale,payment_method Metodo,collected_by Incassato_da,paid Pagato,notes Note FROM sales WHERE 1=1'; args=[]
    if fl!='Tutto': sql+=' AND line=?'; args.append(fl)
    if status=='Pagato': sql+=' AND paid=1 AND qty>0'
    elif status=='Da incassare': sql+=' AND paid=0 AND qty>0'
    elif status=='Omaggi': sql+=' AND gift_qty>0'
    if search: sql+=' AND customer LIKE ?'; args.append('%'+search+'%')
    sql+=' ORDER BY id DESC'
    rows=df_rows(query(sql,args));
    for r in rows: r['Pagato']='Sì' if r['Pagato'] else ('—' if r['Quantità']==0 else 'No')
    st.dataframe(rows,use_container_width=True,hide_index=True)
    f=financials(fl); render_kpis(f)

def page_cassa():
    st.title('💶 Costi & Cassa')
    line=st.segmented_control('Analisi',['Tutto','Estate','Natale'],default='Tutto')
    f=financials(line); render_kpis(f)
    coverage=(f['incassato']/f['costi']*100) if f['costi'] else 0
    result=f['vendite']-f['costi']; st.progress(min(1.0,coverage/100),text=f'Copertura costi con incassi reali: {coverage:.1f}%')
    # Cash: only common-cash sales/costs + non-operating personal movements.
    cash_sales=query("SELECT COALESCE(SUM(actual_total),0) x FROM sales WHERE paid=1 AND collected_by='Cassa comune'")[0]['x']
    cash_costs=query("SELECT COALESCE(SUM(total),0) x FROM costs WHERE paid_by='Cassa comune'")[0]['x']
    moves=query('SELECT * FROM cash_moves ORDER BY id DESC')
    cash_adj=0; debts={'Chiara':0.0,'Annalisa':0.0}
    for m in moves:
        if m['type']=='Prelievo da restituire': cash_adj-=m['amount']; debts[m['person']]=debts.get(m['person'],0)+m['amount']
        elif m['type']=='Restituzione prelievo': cash_adj+=m['amount']; debts[m['person']]=debts.get(m['person'],0)-m['amount']
        elif m['type']=='Anticipo personale': cash_adj+=m['amount']; debts[m['person']]=debts.get(m['person'],0)-m['amount']
        elif m['type']=='Rimborso anticipo': cash_adj-=m['amount']; debts[m['person']]=debts.get(m['person'],0)+m['amount']
        elif m['type']=='Rettifica +': cash_adj+=m['amount']
        elif m['type']=='Rettifica -': cash_adj-=m['amount']
    st.subheader('Cassa reale e posizioni personali')
    a,b,c=st.columns(3); a.metric('Cassa comune teorica',euro(cash_sales-cash_costs+cash_adj)); b.metric('Chiara da restituire',euro(max(0,debts.get('Chiara',0)))); c.metric('Annalisa da restituire',euro(max(0,debts.get('Annalisa',0))))
    t1,t2,t3=st.tabs(['Costi','Movimenti personali','Analisi'])
    with t1:
        with st.form('cost',clear_on_submit=True):
            a,b,c1=st.columns(3); dt=a.date_input('Data costo',date.today()); ln=b.selectbox('Linea',['Estate','Natale','Generale Apiario']); cat=c1.selectbox('Categoria',COST_CATS)
            desc=st.text_input('Voce di costo'); a,b,c1=st.columns(3); qty=a.number_input('Quantità',0.0,100000.0,1.0); unit=b.number_input('Costo unitario €',0.0,100000.0,0.0); paidby=c1.selectbox('Pagato da',PEOPLE)
            notes=st.text_input('Note costo')
            if st.form_submit_button('Registra costo'):
                c=conn(); c.execute('insert into costs(cost_date,line,category,description,qty,unit_cost,total,paid_by,notes) values(?,?,?,?,?,?,?,?,?)',(str(dt),ln,cat,desc,qty,unit,qty*unit,paidby,notes)); c.commit(); c.close(); st.rerun()
        cw='' if line=='Tutto' else 'WHERE line=?'; ca=() if line=='Tutto' else (line,)
        st.dataframe(df_rows(query(f'SELECT id,cost_date Data,line Linea,category Categoria,description Voce,qty Quantità,unit_cost Costo_unitario,total Totale,paid_by Pagato_da,notes Note FROM costs {cw} ORDER BY id DESC',ca)),use_container_width=True,hide_index=True)
    with t2:
        with st.form('move',clear_on_submit=True):
            a,b,c1=st.columns(3); dt=a.date_input('Data movimento',date.today(),key='md'); person=b.selectbox('Persona',['Chiara','Annalisa']); typ=c1.selectbox('Movimento',['Prelievo da restituire','Restituzione prelievo','Anticipo personale','Rimborso anticipo','Rettifica +','Rettifica -'])
            amount=st.number_input('Importo €',0.0,100000.0,0.0,1.0); notes=st.text_input('Motivo / note')
            if st.form_submit_button('Registra movimento'):
                c=conn(); c.execute('insert into cash_moves(move_date,person,type,amount,notes) values(?,?,?,?,?)',(str(dt),person,typ,amount,notes)); c.commit(); c.close(); st.rerun()
        st.dataframe(df_rows(query('SELECT id,move_date Data,person Persona,type Movimento,amount Importo,notes Note FROM cash_moves ORDER BY id DESC')),use_container_width=True,hide_index=True)
    with t3:
        st.markdown(f'''**Lettura {line}:** vendite a listino {euro(f['listino'])}; sconti {euro(f['sconti'])}; vendite effettive {euro(f['vendite'])}; costi {euro(f['costi'])}; risultato economico su ordinato **{euro(result)}**.''')
        st.caption('I prelievi personali non sono costi: modificano la cassa e restano come importi da restituire. Gli sconti riducono il ricavo effettivo ma restano misurati separatamente.')

init_db()
st.sidebar.title('CLAS 🍯')
st.sidebar.caption('Gestione miele • apiario autosufficiente')
page=st.sidebar.radio('Sezione',['Magazzino','Vendite','Costi & Cassa'])
if page=='Magazzino': page_magazzino()
elif page=='Vendite': page_vendite()
else: page_cassa()

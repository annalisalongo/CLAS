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
            st.error(f"Impossibile preparare l’export Excel: {e}")
    if st.session_state.get("excel_export_bytes"):
        st.download_button("⬇️ Scarica gestionale in Excel", data=st.session_state["excel_export_bytes"],
            file_name=f"CLAS_export_{date.today()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="download_excel_export")
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

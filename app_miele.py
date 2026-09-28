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

page=st.sidebar.radio("Sezione",["Magazzino","Vendite","Costi & Cassa"])
if page=="Magazzino": page_magazzino()
elif page=="Vendite": page_vendite()
else: page_cassa()

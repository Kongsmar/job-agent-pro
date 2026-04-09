import streamlit as st
from openai import OpenAI
import io
import os
import sqlite3
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from docx import Document
from PyPDF2 import PdfReader
import json

# --- KONFIGURATION & DATABASE ---
st.set_page_config(page_title="Job Agent Pro - Master Edition", page_icon="🚀", layout="wide")
db_path = "job_agent_arkiv.db"

def init_db():
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS archive
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  date TEXT, company TEXT, title TEXT, 
                  ansogning TEXT, opslag TEXT, tone TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- SESSION STATE ---
if 'step' not in st.session_state: st.session_state.step = 1
def next_step(): st.session_state.step += 1
def prev_step(): st.session_state.step -= 1
def reset(): 
    for key in list(st.session_state.keys()): del st.session_state[key]
    st.session_state.step = 1

# --- HJÆLPEFUNKTIONER ---
def get_text_from_url(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        for script in soup(["script", "style"]): script.extract()
        return soup.get_text(separator=' ', strip=True)
    except: return ""

def extract_pdf(file):
    try:
        reader = PdfReader(file)
        return "".join([p.extract_text() for p in reader.pages])
    except: return ""

def fill_docx(template, content, company, title, contact_person):
    try:
        template.seek(0)
        doc = Document(template)
        data = {
            "{{ANSOGNING}}": content, 
            "{{VIRKSOMHED}}": company, 
            "{{JOBTITEL}}": title, 
            "{{KONTAKTPERSON}}": contact_person,
            "{{DATO}}": datetime.now().strftime("%d. %m. %Y")
        }
        
        def replace_text_logic(paragraphs):
            for p in paragraphs:
                for key, value in data.items():
                    if key in p.text:
                        # Prøv at erstatte i runs for at bevare formatering
                        for run in p.runs:
                            if key in run.text:
                                run.text = run.text.replace(key, str(value))
                        # Fallback hvis tagget var splittet i Word-filens XML
                        if key in p.text:
                            p.text = p.text.replace(key, str(value))

        replace_text_logic(doc.paragraphs)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    replace_text_logic(cell.paragraphs)
        
        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        return buf
    except: return None

# --- APP FLOW ---
st.title("💼 Job Agent Pro")
st.progress(st.session_state.step / 4)

# --- TRIN 1: FUNDAMENT ---
if st.session_state.step == 1:
    st.header("1. Grundlaget")
    cv = st.file_uploader("Upload dit CV (PDF)", type="pdf")
    temp = st.file_uploader("Upload din Word-skabelon (.docx)", type="docx")
    
    c1, c2 = st.columns(2)
    comp = c1.text_input("Virksomhedens navn:", placeholder="F.eks. LEGO")
    titl = c2.text_input("Hvilken stilling søger du?", placeholder="F.eks. Marketing Manager")
    contact = st.text_input("Kontaktperson (f.eks. Mette Jensen):", placeholder="Navnet der skal stå efter 'Kære' i din skabelon")
    
    if st.button("Næste →", disabled=not (cv and comp and titl)):
        st.session_state.cv_text = extract_pdf(cv)
        st.session_state.temp = temp
        st.session_state.comp = comp
        st.session_state.titl = titl
        st.session_state.contact = contact
        next_step()
        st.rerun()

# --- TRIN 2: JOBOPSLAGET ---
elif st.session_state.step == 2:
    st.header("2. Jobbet")
    url = st.text_input("Link til jobopslag (valgfrit):")
    if st.button("Hent tekst fra link 🌐") and url:
        txt = get_text_from_url(url)
        if txt: 
            st.session_state.fetched_txt = txt
            st.success("Tekst hentet!")
    
    opslag = st.text_area("Indsæt jobteksten her:", value=st.session_state.get('fetched_txt', ""), height=300)
    noter = st.text_area("Dine personlige noter (valgfrit):", placeholder="Nævn specifikke ting AI'en skal fremhæve...")
    
    col1, col2 = st.columns(2)
    if col1.button("← Tilbage"): prev_step(); st.rerun()
    if col2.button("Næste →", disabled=not opslag):
        st.session_state.opslag = opslag
        st.session_state.noter = noter
        next_step()
        st.rerun()

# --- TRIN 3: STRATEGI ---
elif st.session_state.step == 3:
    st.header("3. Din Strategi")
    c1, c2 = st.columns(2)
    tone = c1.selectbox("Toneleje:", ["Professionel", "Balanceret", "Personlig", "Kreativ", "Formel"])
    length = st.select_slider("Omfang:", ["Kort", "Standard", "Uddybende"], "Standard")
    
    s1, s2 = st.columns(2)
    strat = s1.selectbox("Indlednings-strategi:", ["Problemknuser", "Værdi-baseret", "Direkte/Resultater", "Passioneret"])
    fokus = s2.radio("Hovedfokus:", ["Faglige resultater", "Personlige kompetencer", "Balanceret"], horizontal=True)
    
    mot_pos = st.radio("Hvor skal din motivation placeres?", ["I starten (krogen)", "I bunden (opsamlingen)"], index=0)

    col1, col2 = st.columns(2)
    if col1.button("← Tilbage"): prev_step(); st.rerun()
    if col2.button("Analysér & Generér ✨"):
        st.session_state.p = {"tone": tone, "len": length, "strat": strat, "fokus": fokus, "mot_pos": mot_pos}
        next_step()
        st.rerun()

# --- TRIN 4: ANALYSE & RESULTAT ---
elif st.session_state.step == 4:
    st.header("4. Din færdige pakke")
    
    if "final_res" not in st.session_state:
        with st.spinner("Udfører ATS-analyse og skriver alt indhold..."):
            try:
                client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
                p = st.session_state.p
                
                # 1. ATS ANALYSE
                ats_p = f"""Analysér jobopslag mod CV. 
                Giv mig en 'Match Score' i procent (f.eks. 85%) og de 3 vigtigste nøgleord.
                Job: {st.session_state.opslag[:2000]}
                CV: {st.session_state.cv_text[:2000]}"""
                
                ats_resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": ats_p}])
                st.session_state.ats_result = ats_resp.choices[0].message.content

                # 2. HOVEDGENERERING
                len_instr = "ca. 550 ord (fyldige afsnit)" if p['len'] == "Standard" else "ca. 350 ord" if p['len'] == "Kort" else "ca. 800 ord"
                
                main_prompt = f"""
                Du er en elite-rekrutteringskonsulent. Lav en komplet pakke i JSON format.
                
                VIGTIG REGEL FOR MOTIVATION: 
                Brugeren har valgt: {p['mot_pos']}. 
                - Hvis 'I starten', skal første afsnit handle om motivationen for jobbet/virksomheden.
                - Hvis 'I bunden', skal de faglige kompetencer komme først.

                JSON STRUKTUR:
                1. 'ansogning': Skriv KUN brødteksten. Ingen 'Kære...', ingen 'Med venlig hilsen'. Start direkte. 
                   Længde: {len_instr}. Tone: {p['tone']}. Fokus: {p['fokus']}. Strategi: {p['strat']}.
                2. 'pitch': En 3-4 sætningers besked til LinkedIn.
                3. 'interview': En liste med de 3 mest kritiske interviewspørgsmål og strategiske svar.
                
                DATA:
                CV: {st.session_state.cv_text}
                JOB: {st.session_state.opslag}
                ANALYSEN: {st.session_state.ats_result}
                NOTER: {st.session_state.noter}
                """
                
                resp = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "system", "content": "Svar kun i JSON format."}, {"role": "user", "content": main_prompt}],
                    response_format={"type": "json_object"}
                )
                
                st.session_state.final_res = json.loads(resp.choices[0].message.content)
                
                # Arkivering
                conn = sqlite3.connect(db_path); c = conn.cursor()
                c.execute("INSERT INTO archive (date, company, title, ansogning, opslag, tone) VALUES (?,?,?,?,?,?)",
                          (datetime.now().strftime("%Y-%m-%d %H:%M"), st.session_state.comp, st.session_state.titl, st.session_state.final_res['ansogning'], st.session_state.opslag, p['tone']))
                conn.commit(); conn.close()
                
            except Exception as e:
                st.error(f"Fejl: {e}")

    if "final_res" in st.session_state:
        st.info(f"📊 **ATS & Match Analyse:**\n{st.session_state.ats_result}")
        
        c_main, c_side = st.columns([2, 1])
        with c_main:
            st.subheader("📝 Ansøgning (Brødtekst)")
            st.write(st.session_state.final_res['ansogning'])
            if st.session_state.temp:
                doc = fill_docx(st.session_state.temp, st.session_state.final_res['ansogning'], st.session_state.comp, st.session_state.titl, st.session_state.contact)
                st.download_button("Hent Word-fil 📄", doc, f"Ansøgning_{st.session_state.comp}.docx")
        
        with c_side:
            st.subheader("✉️ LinkedIn Pitch")
            st.success(st.session_state.final_res['pitch'])
            st.subheader("🎤 Interview Forberedelse")
            st.warning(st.session_state.final_res['interview'])
        
        if st.button("Start forfra 🔄"): reset(); st.rerun()

# --- ARKIV ---
st.divider()
with st.expander("📂 Arkiv"):
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path); df = pd.read_sql_query("SELECT * FROM archive ORDER BY id DESC", conn); conn.close()
        for _, r in df.iterrows():
            with st.expander(f"📌 {r['company']} - {r['title']} ({r['date']})"):
                st.write(r['ansogning'])

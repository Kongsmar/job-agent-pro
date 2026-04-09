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
st.set_page_config(page_title="Job Agent Pro - Master Guided", page_icon="🚀", layout="wide")
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
        headers = {'User-Agent': 'Mozilla/5.0'}
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
        
        # Ordbog over alle de tags vi leder efter
        data = {
            "{{ANSOGNING}}": content, 
            "{{VIRKSOMHED}}": company, 
            "{{JOBTITEL}}": title, 
            "{{KONTAKTPERSON}}": contact_person,
            "{{DATO}}": datetime.now().strftime("%d. %m. %Y")
        }
        
        # Funktion til at gennemgå paragraffer og erstatte tags korrekt
        def replace_text_in_paragraphs(paragraphs):
            for p in paragraphs:
                for key, value in data.items():
                    if key in p.text:
                        # Denne metode bevarer formatering bedre og sikrer erstatning
                        inline = p.runs
                        for i in range(len(inline)):
                            if key in inline[i].text:
                                inline[i].text = inline[i].text.replace(key, str(value))
                        # Hvis tagget var splittet over flere runs, bruger vi denne fallback:
                        if key in p.text:
                            p.text = p.text.replace(key, str(value))

        # Kør erstatning i hovedteksten
        replace_text_in_paragraphs(doc.paragraphs)
        
        # Kør erstatning i alle tabeller (hvis tags står i en tabel)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    replace_text_in_paragraphs(cell.paragraphs)
        
        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        return buf
    except Exception as e:
        st.error(f"Word-fejl: {e}")
        return None

# --- APP FLOW ---
st.title("🚀 Job Agent Pro")
st.progress(st.session_state.step / 4)

if st.session_state.step == 1:
    st.header("1. Grundlaget")
    cv = st.file_uploader("Upload dit CV (PDF)", type="pdf")
    temp = st.file_uploader("Upload din Word-skabelon (.docx)", type="docx")
    c1, c2 = st.columns(2)
    comp = c1.text_input("Virksomhedens navn:")
    titl = c2.text_input("Hvilken stilling søger du?")
    contact = st.text_input("Kontaktperson (f.eks. Mette Jensen):")
    if st.button("Næste →", disabled=not (cv and comp and titl)):
        st.session_state.cv_text = extract_pdf(cv)
        st.session_state.temp = temp
        st.session_state.comp = comp
        st.session_state.titl = titl
        st.session_state.contact = contact
        next_step()
        st.rerun()

elif st.session_state.step == 2:
    st.header("2. Jobbet")
    url = st.text_input("Link til jobopslag:")
    if st.button("Hent tekst") and url:
        txt = get_text_from_url(url)
        if txt: st.session_state.fetched_txt = txt
    opslag = st.text_area("Jobtekst:", value=st.session_state.get('fetched_txt', ""), height=250)
    noter = st.text_area("Noter til AI'en:")
    col1, col2 = st.columns(2)
    if col1.button("← Tilbage"): prev_step(); st.rerun()
    if col2.button("Næste →", disabled=not opslag):
        st.session_state.opslag = opslag
        st.session_state.noter = noter
        next_step()
        st.rerun()

elif st.session_state.step == 3:
    st.header("3. Strategi")
    c1, c2 = st.columns(2)
    tone = c1.selectbox("Toneleje:", ["Professionel", "Balanceret", "Personlig", "Kreativ", "Formel"])
    length = st.select_slider("Omfang:", ["Kort", "Standard", "Uddybende"], "Standard")
    strat = st.selectbox("Indledning:", ["Problemknuser", "Værdi-baseret", "Direkte/Resultater", "Passioneret"])
    fokus = st.radio("Fokus:", ["Faglige resultater", "Personlige kompetencer", "Balanceret"], horizontal=True)
    mirror = st.toggle("Spejl sprogbrug", True)
    motivation = st.radio("Motivationens placering:", ["I starten", "I bunden"])
    col1, col2 = st.columns(2)
    if col1.button("← Tilbage"): prev_step(); st.rerun()
    if col2.button("Generér Pakke ✨"):
        st.session_state.p = {"tone": tone, "len": length, "strat": strat, "fokus": fokus, "mirror": mirror, "mot": motivation}
        next_step()
        st.rerun()

elif st.session_state.step == 4:
    st.header("4. Analyse & Resultat")
    if "final_res" not in st.session_state:
        with st.spinner("Udfører analyse og skriver din ansøgning..."):
            try:
                client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
                p = st.session_state.p
                
                # ATS ANALYSE
                ats_p = f"Analysér dette jobopslag mod dette CV. Giv mig 3 nøgleord og en Match Score i %.\nJob: {st.session_state.opslag[:2000]}\nCV: {st.session_state.cv_text[:2000]}"
                ats_resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": ats_p}])
                st.session_state.ats_result = ats_resp.choices[0].message.content

                # HOVED PROMPT
                len_instr = "450-600 ord (4-5 afsnit)" if p['len'] == "Standard" else "250-350 ord" if p['len'] == "Kort" else "750+ ord"
                main_prompt = f"""
                Skriv en komplet pakke i JSON.
                'ansogning': Skriv KUN brødteksten. Ingen hilsen/afsked. Længde: {len_instr}. 
                'pitch': 3-4 sætninger til LinkedIn.
                'interview': 3 mest kritiske spørgsmål.
                DATA: CV: {st.session_state.cv_text}, JOB: {st.session_state.opslag}, ANALYSE: {st.session_state.ats_result}
                """
                resp = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "system", "content": "Svar kun i JSON."}, {"role": "user", "content": main_prompt}],
                    response_format={"type": "json_object"}
                )
                st.session_state.final_res = json.loads(resp.choices[0].message.content)
                
                # Gem i arkiv
                conn = sqlite3.connect(db_path); c = conn.cursor()
                c.execute("INSERT INTO archive (date, company, title, ansogning, opslag, tone) VALUES (?,?,?,?,?,?)",
                          (datetime.now().strftime("%Y-%m-%d %H:%M"), st.session_state.comp, st.session_state.titl, st.session_state.final_res['ansogning'], st.session_state.opslag, p['tone']))
                conn.commit(); conn.close()
            except Exception as e:
                st.error(f"Fejl: {e}")

    if "final_res" in st.session_state:
        st.info(f"📊 **ATS Analyse:** {st.session_state.ats_result}")
        c_main, c_side = st.columns([2, 1])
        with c_main:
            st.subheader("📝 Brødtekst")
            st.write(st.session_state.final_res['ansogning'])
            if st.session_state.temp:
                doc = fill_docx(st.session_state.temp, st.session_state.final_res['ansogning'], st.session_state.comp, st.session_state.titl, st.session_state.contact)
                st.download_button("Hent Word-fil 📄", doc, f"Ansøgning_{st.session_state.comp}.docx")
        
        with c_side:
            st.subheader("✉️ Ekstra")
            st.success("**Pitch:**\n" + st.session_state.final_res['pitch'])
            st.warning("**Interview:**\n" + st.session_state.final_res['interview'])
        
        if st.button("Start forfra 🔄"): reset(); st.rerun()

# --- ARKIV ---
st.divider()
with st.expander("📂 Arkiv"):
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path); df = pd.read_sql_query("SELECT * FROM archive ORDER BY id DESC", conn); conn.close()
        for _, r in df.iterrows():
            with st.expander(f"📌 {r['company']} - {r['title']} ({r['date']})"):
                st.write(r['ansogning'])

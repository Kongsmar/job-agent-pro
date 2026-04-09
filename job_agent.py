import streamlit as st
from openai import OpenAI
import io
import os
import sqlite3
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from docx import Document
from PyPDF2 import PdfReader
import json
import urllib.parse

# --- KONFIGURATION & DATABASE ---
st.set_page_config(page_title="Job Agent Pro", page_icon="🚀", layout="wide")
db_path = "job_agent_arkiv.db"

def get_danish_time():
    return (datetime.utcnow() + timedelta(hours=2)).strftime("%d. %m. %Y, %H:%M")

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

# --- HJÆLPEFUNKTIONER ---
def get_text_from_url(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        title = soup.title.string.split('|')[0].strip() if soup.title else ""
        for script in soup(["script", "style", "nav", "footer"]): script.extract()
        return soup.get_text(separator=' ', strip=True), title
    except Exception as e:
        return f"Kunne ikke hente tekst: {e}", ""

def extract_pdf(file):
    try:
        reader = PdfReader(file)
        return "".join([p.extract_text() for p in reader.pages])
    except: return ""

def fill_docx(template, content, headline, company, title, contact_person):
    try:
        template.seek(0)
        doc = Document(template)
        data = {
            "{{VIRKSOMHED}}": company, 
            "{{JOBTITEL}}": title, 
            "{{KONTAKTPERSON}}": contact_person,
            "{{OVERSKRIFT}}": headline.strip().capitalize(),
            "{{DATO}}": datetime.now().strftime("%d. %m. %Y")
        }
        for p in doc.paragraphs:
            for key, value in data.items():
                if key in p.text:
                    p.text = p.text.replace(key, str(value))
            if "{{ANSOGNING}}" in p.text:
                p.text = p.text.replace("{{ANSOGNING}}", "")
                # Tilføj ansøgningen afsnit for afsnit for at bevare formatering
                for text in content.split('\n'):
                    if text.strip():
                        doc.add_paragraph(text.strip())
        
        # Håndter tabeller (virksomhed, titel osv i header/footer)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        for key, value in data.items():
                            if key in p.text:
                                p.text = p.text.replace(key, str(value))
                                
        buf = io.BytesIO(); doc.save(buf); buf.seek(0)
        return buf
    except: return None

# --- SESSION STATE ---
if 'step' not in st.session_state: st.session_state.step = 1
def next_step(): st.session_state.step += 1
def prev_step(): st.session_state.step -= 1
def reset(): 
    for key in list(st.session_state.keys()):
        if key not in ['cv_text', 'temp']: del st.session_state[key]
    st.session_state.step = 1

# --- APP FLOW ---
st.title("💼 Job Agent Pro")
st.progress(st.session_state.step / 4)

if st.session_state.step == 1:
    st.header("1. Find Job & Grundlag")
    
    with st.expander("🔍 Start her: Lav en målrettet Google-søgning", expanded=True):
        c_s1, c_s2 = st.columns(2)
        s_title = c_s1.text_input("Hvilken stilling?", placeholder="f.eks. Projektleder")
        s_loc = c_s2.text_input("Hvor?", placeholder="f.eks. København")
        
        if s_title:
            # Smart Google Dork der finder de mest relevante opslag med det samme
            query = f'"{s_title}" {s_loc} site:jobindex.dk OR site:job.jobnet.dk OR site:linkedin.com/jobs'
            google_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
            st.markdown(f"### [Se ledige {s_title} job på Google ↗️]({google_url})")
            st.info("Find et job, kopiér URL'en fra din browser, og gå videre til Step 2.")

    st.divider()
    cv = st.file_uploader("Upload dit CV (PDF)", type="pdf")
    temp = st.file_uploader("Upload din Word-skabelon (.docx)", type="docx")
    
    c1, c2 = st.columns(2)
    comp = c1.text_input("Virksomhedens navn:", value=st.session_state.get('comp', ""))
    titl = c2.text_input("Jobtitel:", value=st.session_state.get('titl', ""))
    contact = st.text_input("Kontaktperson (valgfrit):")
    
    if st.button("Næste →", disabled=not (cv and comp and titl)):
        st.session_state.cv_text = extract_pdf(cv); st.session_state.temp = temp
        st.session_state.comp = comp; st.session_state.titl = titl
        st.session_state.contact = contact; next_step(); st.rerun()

elif st.session_state.step == 2:
    st.header("2. Jobopslaget")
    col_u1, col_u2 = st.columns([3, 1])
    manual_url = col_u1.text_input("Indsæt linket til jobbet her:")
    if col_u2.button("Hent tekst 📥"):
        if manual_url:
            with st.spinner("Henter indhold..."):
                txt, _ = get_text_from_url(manual_url)
                st.session_state.fetched_txt = txt
    
    opslag = st.text_area("Jobopslagets tekst:", value=st.session_state.get('fetched_txt', ""), height=350)
    noter = st.text_area("Særlige noter til AI'en (valgfrit):")
    
    c_b, c_n = st.columns(2)
    if c_b.button("← Tilbage"): prev_step(); st.rerun()
    if c_n.button("Næste →", disabled=not opslag):
        st.session_state.opslag = opslag; st.session_state.noter = noter
        next_step(); st.rerun()

elif st.session_state.step == 3:
    st.header("3. Strategi")
    c1, c2 = st.columns(2)
    tone = c1.selectbox("Tone:", ["Professionel", "Balanceret", "Personlig", "Kreativ", "Formel"])
    head_t = c2.selectbox("Overskrift:", ["Formel (Ansøgning om...)", "Værdiskabende", "Kreativ/Catchy", "Spørgende"])
    length = st.select_slider("Længde:", ["Kort", "Standard", "Uddybende"], "Standard")
    fokus = st.radio("Fokus:", ["Faglige resultater", "Personlige kompetencer", "Balanceret"], horizontal=True)
    
    if st.button("Generér Ansøgning ✨"):
        st.session_state.p = {"tone": tone, "len": length, "fokus": fokus, "head_t": head_t}
        next_step(); st.rerun()

elif st.session_state.step == 4:
    st.header("4. Resultat")
    if "final_res" not in st.session_state:
        with st.spinner("Skriver din personlige pakke..."):
            try:
                client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
                p = st.session_state.p
                main_prompt = f"""
                Lav en JSON pakke på dansk.
                1. 'ansogning': Skriv en LANG og fyldig brødtekst (min. 5 afsnit). Brug dobbelt linjeskift. Ingen hilsner eller navne. Start direkte med motivationen.
                2. 'overskrift': Lav en overskrift af typen '{p['head_t']}'. Kun stort begyndelsesbogstav.
                3. 'pitch': 3-4 sætninger til LinkedIn/besked.
                4. 'interview': Top 3 mest kritiske spørgsmål/svar i Markdown format.
                DATA: CV: {st.session_state.cv_text}, JOB: {st.session_state.opslag}, NOTER: {st.session_state.noter}
                """
                resp = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "system", "content": "Du er karriereekspert. Svar kun i JSON."}, {"role": "user", "content": main_prompt}],
                    response_format={"type": "json_object"}
                )
                st.session_state.final_res = json.loads(resp.choices[0].message.content)
                
                # Arkivér i databasen
                conn = sqlite3.connect(db_path); c = conn.cursor()
                c.execute("INSERT INTO archive (date, company, title, ansogning, opslag, tone) VALUES (?,?,?,?,?,?)",
                          (get_danish_time(), st.session_state.comp, st.session_state.titl, st.session_state.final_res['ansogning'], st.session_state.opslag, p['tone']))
                conn.commit(); conn.close()
            except Exception as e: st.error(f"Fejl under generering: {e}")

    if "final_res" in st.session_state:
        res = st.session_state.final_res
        headline = res.get('overskrift', '').strip().capitalize()
        st.subheader(headline)
        st.divider()
        c_m, c_s = st.columns([2, 1])
        with c_m:
            st.write(res.get('ansogning', ''))
            if st.session_state.temp:
                doc = fill_docx(st.session_state.temp, res.get('ansogning'), headline, st.session_state.comp, st.session_state.titl, st.session_state.contact)
                st.download_button("Hent Word-fil 📄", doc, f"Ansogning_{st.session_state.comp}.docx")
        with c_s:
            st.success(res.get('pitch', ''))
            st.markdown(res.get('interview', ''))
        if st.button("Start forfra 🔄"): reset(); st.rerun()

# --- ARKIV ---
st.divider()
st.subheader("📂 Tidligere ansøgninger")
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path); df = pd.read_sql_query("SELECT * FROM archive ORDER BY id DESC", conn); conn.close()
    for index, row in df.head(10).iterrows():
        with st.expander(f"📌 {row['company']} - {row['title']} ({row['date']})"):
            st.write(row['ansogning'])

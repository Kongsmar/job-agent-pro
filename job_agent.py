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
import re

# --- KONFIGURATION & DATABASE ---
st.set_page_config(page_title="Job Agent Pro - Power Edition", page_icon="🚀", layout="wide")
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
def clean_text_final(text):
    """Fjerner hilsner og flettekoder manuelt."""
    lines = text.split('\n')
    bad_starts = ['kære', 'med venlig hilsen', 'venlig hilsen', 'mvh', 'hilsen', 'til ', 'emne:', 'vedrør:']
    cleaned = [l for l in lines if not any(l.lower().strip().startswith(bw) for bw in bad_starts)]
    res = '\n'.join(cleaned).strip()
    res = re.sub(r'\{\{.*?\}\}', '', res)
    return res

def get_text_from_url(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        for script in soup(["script", "style"]): script.extract()
        return soup.get_text(separator=' ', strip=True)
    except: return "Kunne ikke hente tekst."

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
                if key in p.text: p.text = p.text.replace(key, str(value))
            if "{{ANSOGNING}}" in p.text:
                p.text = p.text.replace("{{ANSOGNING}}", "")
                for text in content.split('\n'):
                    if text.strip(): doc.add_paragraph(text.strip())
        buf = io.BytesIO(); doc.save(buf); buf.seek(0)
        return buf
    except: return None

# --- SESSION STATE ---
if 'step' not in st.session_state: st.session_state.step = 1
def next_step(): st.session_state.step += 1
def prev_step(): st.session_state.step -= 1
def reset(): 
    for key in list(st.session_state.keys()):
        if key not in ['cv_text', 'temp', 'final_res', 'ats_result']: del st.session_state[key]
    st.session_state.step = 1

# --- APP FLOW ---
st.title("💼 Job Agent Pro")
st.progress(st.session_state.step / 4)

if st.session_state.step == 1:
    st.header("1. Grundlag")
    with st.expander("🔍 Google Job-Søgning", expanded=True):
        c_s1, c_s2 = st.columns(2)
        s_title = c_s1.text_input("Hvilken stilling?", placeholder="f.eks. Projektleder")
        s_loc = c_s2.text_input("Hvor?", placeholder="f.eks. Aarhus")
        if s_title:
            query = f'"{s_title}" {s_loc} site:jobindex.dk OR site:job.jobnet.dk OR site:linkedin.com/jobs'
            google_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
            st.markdown(f"### [Klik for at søge på Google ↗️]({google_url})")

    st.divider()
    cv = st.file_uploader("Upload dit CV (PDF)", type="pdf")
    temp = st.file_uploader("Upload Word-skabelon (.docx)", type="docx")
    c1, c2 = st.columns(2)
    comp = c1.text_input("Virksomhed:", value=st.session_state.get('comp', ""))
    titl = c2.text_input("Stilling:", value=st.session_state.get('titl', ""))
    contact = st.text_input("Kontaktperson (valgfrit):")
    
    if st.button("Næste →", disabled=not (cv and comp and titl)):
        st.session_state.cv_text = extract_pdf(cv); st.session_state.temp = temp
        st.session_state.comp = comp; st.session_state.titl = titl
        st.session_state.contact = contact; next_step(); st.rerun()

elif st.session_state.step == 2:
    st.header("2. Jobopslaget")
    col_u1, col_u2 = st.columns([3, 1])
    manual_url = col_u1.text_input("Indsæt link til jobbet:")
    if col_u2.button("Hent tekst 📥"):
        if manual_url: st.session_state.fetched_txt = get_text_from_url(manual_url)
    
    opslag = st.text_area("Jobtekst:", value=st.session_state.get('fetched_txt', ""), height=300)
    noter = st.text_area("Særlige noter til denne ansøgning:")
    c_b, c_n = st.columns(2)
    if c_b.button("← Tilbage"): prev_step(); st.rerun()
    if c_n.button("Næste →", disabled=not opslag):
        st.session_state.opslag = opslag; st.session_state.noter = noter
        next_step(); st.rerun()

elif st.session_state.step == 3:
    st.header("3. Strategi")
    c1, c2 = st.columns(2)
    tone = c1.selectbox("Tone:", ["Professionel", "Balanceret", "Personlig", "Kreativ", "Formel"])
    head_t = c2.selectbox("Overskriftstype:", ["Formel", "Værdiskabende", "Catchy", "Spørgende"])
    
    # Længde-instruktion
    length = st.select_slider("Hvor lang skal ansøgningen være?", ["Kort", "Standard", "Uddybende"], value="Standard")
    
    fokus = st.radio("Fokus:", ["Faglige resultater", "Personlige kompetencer", "Balanceret"], horizontal=True)
    mot_pos = st.radio("Motivationens placering:", ["I starten (krogen)", "I bunden (opsamlingen)"], horizontal=True)
    
    if st.button("Generér Alt ✨"):
        st.session_state.p = {"tone": tone, "fokus": fokus, "head_t": head_t, "length": length, "mot_pos": mot_pos}
        next_step(); st.rerun()

elif st.session_state.step == 4:
    st.header("4. Resultat")
    if "final_res" not in st.session_state:
        with st.spinner("Skriver en fuld, professionel ansøgning..."):
            try:
                client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
                p = st.session_state.p
                
                # 1. ATS ANALYSE
                ats_p = f"Analysér dette CV mod Jobopslaget. Giv Match Score i % og punktform.\nCV: {st.session_state.cv_text[:2000]}\nJob: {st.session_state.opslag[:2000]}"
                ats_resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": ats_p}])
                st.session_state.ats_result = ats_resp.choices[0].message.content

                # 2. HOVEDGENERERING (FORBEDRET PROMPT FOR LÆNGDE OG FYLDE)
                main_prompt = f"""
                Du er en ekspert i rekruttering. Skriv en KOMPLET og DYBDEGÅENDE ansøgning på dansk.
                
                REGLER:
                - Ingen hilsner (Kære, Venlig hilsen osv).
                - Ingen flettekoder.
                - Start direkte med motivationen jf. indstillingen nedenfor.
                - Brug mindst 300 ord hvis 'Standard' og 500 ord hvis 'Uddybende'.
                
                STRUKTUR:
                1. 'ansogning': Skriv selve brødteksten. 
                   Længde: {p['length']} (gør den fyldig og detaljeret). 
                   Tone: {p['tone']}. Fokus: {p['fokus']}.
                   Motivationens placering: {p['mot_pos']}.
                   Sørg for at koble specifikke erfaringer fra CV'et direkte til behovene i Jobopslaget.
                2. 'overskrift': En stærk '{p['head_t']}' overskrift.
                3. 'pitch': LinkedIn pitch (3-4 skarpe sætninger).
                4. 'interview': 3 kritiske spørgsmål og svarforslag. 
                   Formatér som: #### ❓ [Spørgsmål]\n**Svarforslag:** [Svar]
                """
                
                resp = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "Du skriver ansøgninger der får folk til samtale. Svar altid i JSON."},
                        {"role": "user", "content": main_prompt + f"\nCV: {st.session_state.cv_text}\nJOB: {st.session_state.opslag}\nNOTER: {st.session_state.noter}"}
                    ],
                    response_format={"type": "json_object"}
                )
                
                raw_json = json.loads(resp.choices[0].message.content)
                raw_json['ansogning'] = clean_text_final(raw_json['ansogning'])
                st.session_state.final_res = raw_json
                
                # Arkivér
                conn = sqlite3.connect(db_path); c = conn.cursor()
                c.execute("INSERT INTO archive (date, company, title, ansogning, opslag, tone) VALUES (?,?,?,?,?,?)",
                          (get_danish_time(), st.session_state.comp, st.session_state.titl, st.session_state.final_res['ansogning'], st.session_state.opslag, p['tone']))
                conn.commit(); conn.close()
            except Exception as e: st.error(f"Fejl under generering: {e}")

    if "final_res" in st.session_state:
        res = st.session_state.final_res
        with st.expander("📊 ATS Match Analyse", expanded=True): st.markdown(st.session_state.ats_result)
        st.divider()
        c_m, c_s = st.columns([2, 1])
        with c_m:
            headline = res.get('overskrift', '').strip().capitalize()
            st.subheader(headline)
            st.write(res.get('ansogning', ''))
            if st.session_state.temp:
                doc = fill_docx(st.session_state.temp, res.get('ansogning'), headline, st.session_state.comp, st.session_state.titl, st.session_state.contact)
                st.download_button("Hent Word-fil (.docx) 📄", doc, f"Ansogning_{st.session_state.comp}.docx")
        with c_s:
            st.subheader("✉️ LinkedIn Pitch")
            st.info(res.get('pitch', ''))
            st.subheader("🎤 Interview Prep")
            st.markdown(res.get('interview', ''))
        if st.button("Start forfra 🔄"): reset(); st.rerun()

# --- ARKIV ---
st.divider()
st.subheader("📂 Tidligere jobs & ansøgninger")
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path); df = pd.read_sql_query("SELECT * FROM archive ORDER BY id DESC", conn); conn.close()
    for index, row in df.head(10).iterrows():
        with st.expander(f"📌 {row['company']} - {row['title']} ({row['date']})"):
            t1, t2 = st.tabs(["Ansøgning", "Originalt Opslag"])
            with t1:
                st.write(row['ansogning'])
                st.download_button("Hent som tekst", row['ansogning'], f"Ansogning_{row['company']}.txt", key=f"a_{index}")
            with t2:
                st.write(row['opslag'])
                st.download_button("Hent som tekst", row['opslag'], f"Opslag_{row['company']}.txt", key=f"o_{index}")

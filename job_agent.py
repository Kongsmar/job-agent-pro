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
import feedparser
import urllib.parse

# --- KONFIGURATION & DATABASE ---
st.set_page_config(page_title="Job Agent Pro - Master Edition", page_icon="🚀", layout="wide")
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
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        for script in soup(["script", "style"]): script.extract()
        return soup.get_text(separator=' ', strip=True)
    except: return ""

def search_jobindex(query, location):
    try:
        encoded_q = urllib.parse.quote(query)
        encoded_l = urllib.parse.quote(location)
        rss_url = f"https://www.jobindex.dk/jobsoegning?q={encoded_q}&l={encoded_l}&format=rss"
        
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'}
        response = requests.get(rss_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            feed = feedparser.parse(response.content)
            return feed.entries
        return []
    except: return []

def extract_pdf(file):
    try:
        reader = PdfReader(file)
        return "".join([p.extract_text() for p in reader.pages])
    except: return ""

def fill_docx(template, content, headline, company, title, contact_person):
    try:
        template.seek(0)
        doc = Document(template)
        formatted_headline = headline.strip().capitalize()
        data = {
            "{{VIRKSOMHED}}": company, 
            "{{JOBTITEL}}": title, 
            "{{KONTAKTPERSON}}": contact_person,
            "{{OVERSKRIFT}}": formatted_headline,
            "{{DATO}}": datetime.now().strftime("%d. %m. %Y")
        }
        for p in doc.paragraphs:
            for key, value in data.items():
                if key in p.text:
                    p.text = p.text.replace(key, str(value))
            if "{{ANSOGNING}}" in p.text:
                p.text = p.text.replace("{{ANSOGNING}}", "")
                paragraphs_content = content.split('\n')
                cursor = p
                for text in paragraphs_content:
                    if text.strip():
                        new_p = doc.add_paragraph(text.strip())
                        cursor._element.addnext(new_p._element)
                        cursor = new_p
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        for key, value in data.items():
                            if key in p.text:
                                p.text = p.text.replace(key, str(value))
        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        return buf
    except: return None

# --- SESSION STATE ---
if 'step' not in st.session_state: st.session_state.step = 1
def next_step(): st.session_state.step += 1
def prev_step(): st.session_state.step -= 1
def reset(): 
    for key in list(st.session_state.keys()): 
        if key != 'cv_text' and key != 'temp': # Bevar filer hvis muligt
            del st.session_state[key]
    st.session_state.step = 1

# --- APP FLOW ---
st.title("💼 Job Agent Pro")
st.progress(st.session_state.step / 4)

if st.session_state.step == 1:
    st.header("1. Find Job & Grundlag")
    
    with st.expander("🔍 Valgfrit: Søg efter jobopslag på Jobindex"):
        c_s1, c_s2 = st.columns(2)
        search_q = c_s1.text_input("Jobtitel:")
        search_l = c_s2.text_input("By/Område:")
        
        if st.button("Søg nu"):
            with st.spinner("Henter data..."):
                results = search_jobindex(search_q, search_l)
                if results:
                    for entry in results[:10]:
                        col_t, col_b = st.columns([4, 1])
                        col_t.markdown(f"**{entry.title}**")
                        if col_b.button("Brug dette 📥", key=entry.link):
                            st.session_state.fetched_txt = get_text_from_url(entry.link)
                            st.session_state.comp = entry.title.split(" hos ")[-1] if " hos " in entry.title else ""
                            st.session_state.titl = entry.title.split(" hos ")[0]
                            st.success(f"Valgt: {st.session_state.titl}")
                else:
                    st.warning("Ingen resultater. Prøv bredere søgeord.")

    st.divider()
    
    cv = st.file_uploader("Upload dit CV (PDF)", type="pdf")
    temp = st.file_uploader("Upload din Word-skabelon (.docx)", type="docx")
    
    c1, c2 = st.columns(2)
    comp = c1.text_input("Virksomhed:", value=st.session_state.get('comp', ""))
    titl = c2.text_input("Stilling:", value=st.session_state.get('titl', ""))
    contact = st.text_input("Kontaktperson (hvis kendt):")
    
    if st.button("Næste →", disabled=not (cv and comp and titl)):
        st.session_state.cv_text = extract_pdf(cv)
        st.session_state.temp = temp
        st.session_state.comp = comp
        st.session_state.titl = titl
        st.session_state.contact = contact
        next_step()
        st.rerun()

elif st.session_state.step == 2:
    st.header("2. Jobopslaget")
    
    col_u1, col_u2 = st.columns([3, 1])
    manual_url = col_u1.text_input("Har du et link? Indsæt her:")
    if col_u2.button("Hent fra link"):
        if manual_url:
            st.session_state.fetched_txt = get_text_from_url(manual_url)
    
    opslag = st.text_area("Jobtekst (redigér eller indsæt her):", value=st.session_state.get('fetched_txt', ""), height=350)
    noter = st.text_area("Noter til AI (f.eks. 'Fokusér på min erfaring med Python'):")
    
    c_back, c_next = st.columns(2)
    if c_back.button("← Tilbage"): prev_step(); st.rerun()
    if c_next.button("Næste →", disabled=not opslag):
        st.session_state.opslag = opslag
        st.session_state.noter = noter
        next_step()
        st.rerun()

elif st.session_state.step == 3:
    st.header("3. Strategi")
    c1, c2 = st.columns(2)
    tone = c1.selectbox("Tone:", ["Professionel", "Balanceret", "Personlig", "Kreativ", "Formel"])
    headline_type = c2.selectbox("Overskriftstype:", ["Formel (Ansøgning om...)", "Værdiskabende (Resultatorienteret)", "Kreativ/Catchy", "Spørgende/Nysgerrig"])
    length = st.select_slider("Omfang:", ["Kort", "Standard", "Uddybende"], "Standard")
    strat = st.selectbox("Indledning:", ["Problemknuser", "Værdi-baseret", "Direkte/Resultater", "Passioneret"])
    fokus = st.radio("Fokus:", ["Faglige resultater", "Personlige kompetencer", "Balanceret"], horizontal=True)
    mot_pos = st.radio("Motivationens placering:", ["I starten (krogen)", "I bunden (opsamlingen)"])
    
    if st.button("Generér Alt ✨"):
        st.session_state.p = {"tone": tone, "len": length, "strat": strat, "fokus": fokus, "mot_pos": mot_pos, "headline_type": headline_type}
        next_step()
        st.rerun()

elif st.session_state.step == 4:
    st.header("4. Resultat")
    if "final_res" not in st.session_state:
        with st.spinner("Skriver din pakke..."):
            try:
                client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
                p = st.session_state.p
                
                # ATS ANALYSE
                ats_p = f"Analysér CV mod Jobopslag. Giv Match Score i % og top styrker/mangler.\nCV: {st.session_state.cv_text[:2000]}\nJob: {st.session_state.opslag[:2000]}"
                ats_resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": ats_p}])
                st.session_state.ats_result = ats_resp.choices[0].message.content

                main_prompt = f"""
                Lav en JSON pakke på dansk.
                1. 'ansogning': Skriv en LANG og fyldig brødtekst (min. 5 afsnit). Brug dobbelt linjeskift. Ingen hilsner eller navne. Start direkte.
                2. 'overskrift': Lav en overskrift af typen '{p['headline_type']}'. Den skal afspejle din vinkel i teksten. Kun stort begyndelsesbogstav.
                3. 'pitch': 3-4 sætninger til LinkedIn.
                4. 'interview': Top 3 mest kritiske spørgsmål baseret på jobbet med stærke svarforslag. 
                   Formatér som ren Markdown: #### [Spørgsmål]\n**Svarforslag:** [Svar]
                
                DATA: CV: {st.session_state.cv_text}, JOB: {st.session_state.opslag}, ANALYSE: {st.session_state.ats_result}, NOTER: {st.session_state.noter}
                """
                
                resp = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "system", "content": "Du er karriererådgiver. Svar KUN i JSON format. Ingen koder i teksten."}, {"role": "user", "content": main_prompt}],
                    response_format={"type": "json_object"}
                )
                st.session_state.final_res = json.loads(resp.choices[0].message.content)

                conn = sqlite3.connect(db_path); c = conn.cursor()
                c.execute("INSERT INTO archive (date, company, title, ansogning, opslag, tone) VALUES (?,?,?,?,?,?)",
                          (get_danish_time(), st.session_state.comp, st.session_state.titl, st.session_state.final_res['ansogning'], st.session_state.opslag, p['tone']))
                conn.commit(); conn.close()
            except Exception as e:
                st.error(f"Fejl under generering: {e}")

    if "final_res" in st.session_state:
        res = st.session_state.final_res
        with st.expander("📊 ATS & Match Analyse", expanded=True):
            st.markdown(st.session_state.ats_result)
        
        c_m, c_s = st.columns([2, 1])
        with c_m:
            headline_final = res.get('overskrift', '').strip().capitalize()
            st.markdown(f"### {headline_final}")
            st.divider()
            st.subheader("📝 Ansøgning")
            st.write(res.get('ansogning', ''))
            
            if st.session_state.temp:
                doc = fill_docx(st.session_state.temp, res.get('ansogning'), headline_final, st.session_state.comp, st.session_state.titl, st.session_state.contact)
                st.download_button("Hent Word 📄", doc, f"Ansøgning_{st.session_state.comp}.docx")
        
        with c_s:
            st.subheader("✉️ LinkedIn Pitch")
            st.success(res.get('pitch', ''))
            st.subheader("🎤 Interview Prep")
            st.markdown(res.get('interview', ''))
        
        if st.button("Start forfra 🔄"): reset(); st.rerun()

# --- ARKIV ---
st.divider()
st.subheader("📂 Arkiv")
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path); df = pd.read_sql_query("SELECT * FROM archive ORDER BY id DESC", conn); conn.close()
    if not df.empty:
        for index, row in df.head(15).iterrows():
            with st.expander(f"📌 {row['company']} - {row['title']} ({row['date']})"):
                ca, cb = st.columns(2)
                with ca: st.download_button("Hent Ansøgning (.txt)", row['ansogning'], f"Ans_{row['company']}.txt", key=f"arch_a_{index}")
                with cb: st.download_button("Hent Jobopslag (.txt)", row['opslag'], f"Ops_{row['company']}.txt", key=f"arch_o_{index}")
                st.divider()
                st.write(row['ansogning'])
    else:
        st.info("Arkivet er tomt.")

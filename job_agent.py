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
from fpdf import FPDF
from PyPDF2 import PdfReader
import json

# --- KONFIGURATION & DATABASE ---
st.set_page_config(page_title="Job Agent Pro - Master Edition", page_icon="🚀", layout="wide")
db_path = "job_agent_arkiv_v_final.db"

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
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        for script in soup(["script", "style"]):
            script.extract()
        return soup.get_text(separator=' ', strip=True)
    except: return ""

def extract_text_from_pdf(pdf_file):
    try:
        reader = PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text()
        return text
    except: return None

def create_pdf(text):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=11)
    try:
        clean_text = text.encode('latin-1', 'replace').decode('latin-1')
    except:
        clean_text = text.replace('–', '-').replace('—', '-')
    pdf.multi_cell(0, 8, txt=clean_text)
    return pdf.output(dest='S').encode('latin-1')

def fill_word_template(template_file, content, company_name, job_title):
    try:
        doc = Document(template_file)
        today_str = datetime.now().strftime("%d. %B %Y")
        data_map = {
            "{{ANSOGNING}}": content, 
            "{{VIRKSOMHED}}": company_name, 
            "{{JOBTITEL}}": job_title,
            "{{DATO}}": today_str
        }
        for p in doc.paragraphs:
            for key, value in data_map.items():
                if key in p.text:
                    p.text = p.text.replace(key, value)
        
        target_stream = io.BytesIO()
        doc.save(target_stream)
        target_stream.seek(0)
        return target_stream
    except: return None

# --- APP LAYOUT ---
st.title("🚀 Job Agent Pro - Master Edition")

tabs = st.tabs(["📄 Ny Ansøgning", "📂 Arkiv"])

with tabs[0]:
    with st.sidebar:
        st.header("⚙️ Grundindstillinger")
        api_key = st.secrets.get("OPENAI_API_KEY")
        uploaded_cv = st.file_uploader("1. Upload dit CV (PDF)", type="pdf")
        uploaded_template = st.file_uploader("2. Upload Word-skabelon (.docx)", type="docx")
        
        st.divider()
        st.subheader("🎨 Stil & Form")
        selected_tone = st.select_slider("Toneleje:", options=["Formel", "Professionel", "Balanceret", "Personlig", "Kreativ"], value="Balanceret")
        selected_length = st.select_slider("Længde:", options=["Kort", "Standard", "Uddybende"], value="Standard")

        st.divider()
        st.subheader("🎯 Strategiske valg")
        intro_strategy = st.selectbox("Indlednings-strategi:", [
            "Direkte & Resultatorienteret",
            "Værdi-baseret (Hvorfor jeg passer til jer)",
            "Problemknuser (Hvad jeg kan løse for jer)",
            "Nysgerrig & Motiveret"
        ])
        
        motivation_pos = st.radio("Placering af motivation:", ["I indledningen (Krogen)", "I bunden (Opsamlingen)"], index=0)
        
        focus_area = st.segmented_control("Hovedfokus:", ["Faglige resultater", "Personlige kompetencer", "Balanceret"], default="Balanceret")
        
        st.divider()
        st.subheader("➕ Ekstra funktioner")
        mirror_language = st.toggle("Spejl virksomhedens sprogbrug", value=True)
        include_pitch = st.toggle("Generer LinkedIn Pitch", value=True)
        include_interview = st.toggle("Generer Interview Prep", value=True)

    st.subheader("Job Detaljer")
    c1, c2 = st.columns(2)
    with c1: company = st.text_input("Virksomhedens navn:")
    with c2: title = st.text_input("Jobtitel:")
    
    job_url = st.text_input("Link til jobopslag (URL):")
    job_desc_manual = st.text_area("Eller indsæt jobtekst her:", height=100)
    
    st.divider()
    st.subheader("💡 Personlige noter & Guldkorn")
    personal_notes = st.text_area("Specifikke ting AI'en skal nævne (valgfrit):", placeholder="F.eks. 'Jeg kender systemet de nævner'...", height=70)

    if st.button("Kør Fuldt Program ✨"):
        if not api_key:
            st.error("OpenAI API-nøgle mangler.")
        elif not uploaded_cv or not company or (not job_url and not job_desc_manual):
            st.error("Udfyld venligst alle felter og upload CV.")
        else:
            try:
                client = OpenAI(api_key=api_key)
                cv_text = extract_text_from_pdf(uploaded_cv)
                
                job_text = job_desc_manual
                if job_url:
                    with st.spinner("Henter jobopslag..."):
                        fetched = get_text_from_url(job_url)
                        if len(fetched) > 150: job_text = fetched

                # --- GENERERING ---
                with st.spinner("Arbejder på din strategiske pakke..."):
                    main_prompt = f"""
                    Du er en elite karriererådgiver. Lav følgende for {title} hos {company}:
                    
                    1. En ansøgning (Brødtekst):
                       - Tone: {selected_tone}
                       - Længde: {selected_length}
                       - Indlednings-strategi: {intro_strategy}
                       - Motivationens placering: {motivation_pos}
                       - Hovedfokus: {focus_area}
                       - Strategi: {'Spejl deres sprogbrug' if mirror_language else 'Standard professionel'}
                       - Personlige noter: {personal_notes}
                       - Start og slut direkte (ingen afsender/modtager data).
                    
                    2. En LinkedIn Pitch (3-4 sætninger):
                       - En fængende besked til en rekrutteringsansvarlig.
                    
                    3. Interview Prep:
                       - De 3 mest sandsynlige spørgsmål baseret på gaps mellem CV og jobopslag.
                    
                    CV: {cv_text[:3000]}
                    Jobopslag: {job_text[:3000]}
                    """
                    
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "system", "content": "Du skal svare i JSON format med nøglerne: 'ansogning', 'pitch', 'interview'."},
                                  {"role": "user", "content": main_prompt}],
                        response_format={ "type": "json_object" }
                    )
                    
                    res_data = json.loads(response.choices[0].message.content)
                    ans_text = res_data['ansogning']
                    
                    # Gem i database
                    conn = sqlite3.connect(db_path)
                    c = conn.cursor()
                    c.execute("INSERT INTO archive (date, company, title, ansogning, opslag, tone) VALUES (?, ?, ?, ?, ?, ?)",
                              (datetime.now().strftime("%Y-%m-%d %H:%M"), company, title, ans_text, job_text, selected_tone))
                    conn.commit()
                    conn.close()

                    # --- VISUALISERING ---
                    st.success("Færdig! Her er dit materiale:")
                    
                    col_left, col_right = st.columns([2, 1])
                    
                    with col_left:
                        st.subheader("📝 Ansøgning")
                        st.write(ans_text)
                        
                        d1, d2 = st.columns(2)
                        with d1:
                            if uploaded_template:
                                w_file = fill_word_template(uploaded_template, ans_text, company, title)
                                if w_file:
                                    st.download_button("Hent Word-fil 📄", w_file, f"Ansogning_{company}.docx")
                        with d2:
                            st.download_button("Hent som PDF 📄", create_pdf(ans_text), f"Ansogning_{company}.pdf")

                    with col_right:
                        if include_pitch:
                            st.subheader("✉️ LinkedIn Pitch")
                            st.info(res_data['pitch'])
                        
                        if include_interview:
                            st.subheader("🎤 Interview Prep")
                            st.warning(res_data['interview'])
            
            except Exception as e:
                st.error(f"Der opstod en fejl: {e}")

with tabs[1]:
    st.header("📂 Arkiv")
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query("SELECT * FROM archive ORDER BY id DESC", conn)
        conn.close()
        for i, row in df.iterrows():
            with st.expander(f"📌 {row['company']} - {row['title']} ({row['date']})"):
                st.write(row['ansogning'])
                st.download_button("Download Tekst", row['ansogning'], f"Arkiv_{row['id']}.txt", key=f"dl_{row['id']}")

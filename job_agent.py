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

# --- KONFIGURATION & DATABASE ---
st.set_page_config(page_title="Job Agent Pro", page_icon="💼", layout="wide")
db_path = "job_archive_v8.db"

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
    except:
        return ""

def extract_text_from_pdf(pdf_file):
    try:
        reader = PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text()
        return text
    except:
        return None

def create_pdf(text):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=11)
    clean_text = text.encode('latin-1', 'replace').decode('latin-1')
    pdf.multi_cell(0, 8, txt=clean_text)
    return pdf.output(dest='S').encode('latin-1')

# --- APP LAYOUT ---
st.title("💼 Job Agent Pro")

tabs = st.tabs(["🚀 Analyse & Ansøgning", "📁 Arkiv"])

with tabs[0]:
    with st.sidebar:
        st.header("⚙️ Din Profil")
        api_key = st.secrets.get("OPENAI_API_KEY")
        uploaded_cv = st.file_uploader("1. Upload dit CV (PDF)", type="pdf")
        uploaded_template = st.file_uploader("2. Upload Word-skabelon (.docx)", type="docx")
        
        st.divider()
        st.subheader("🎭 Personligheds-filter")
        
        # HER ER DIN NYE SLIDER MED TEKST
        tone_options = ["Meget Formel", "Professionel", "Balanceret", "Personlig", "Kreativ"]
        selected_tone = st.select_slider(
            "Vælg toneleje:",
            options=tone_options,
            value="Balanceret"
        )
        
        # Forklaring til AI'en baseret på valget
        tone_prompts = {
            "Meget Formel": "meget formel, korrekt og konservativ. Brug et højtideligt sprog og vær meget respektfuld.",
            "Professionel": "saglig, forretningsorienteret og kompetent. Brug et moderne erhvervssprog.",
            "Balanceret": "professionel men imødekommende. En god blanding af personlighed og faglighed.",
            "Personlig": "varm, autentisk og fortællende. Fokusér på dine værdier og din menneskelige motivation.",
            "Kreativ": "modig, sprudlende og anderledes. Brug en fængende indledning og et legende sprog."
        }

    st.subheader("Job Detaljer")
    c1, c2 = st.columns(2)
    with c1: company = st.text_input("Virksomhed:")
    with c2: title = st.text_input("Jobtitel:")
    
    job_url = st.text_input("Link til jobopslag (URL):")
    job_desc_manual = st.text_area("Eller indsæt jobtekst her:", height=150)

    if st.button("Start Match-Analyse & Generering ✨"):
        if not api_key or not uploaded_cv or (not job_url and not job_desc_manual):
            st.error("Hov! Husk at uploade CV og indsætte jobopslag.")
        else:
            try:
                client = OpenAI(api_key=api_key)
                cv_text = extract_text_from_pdf(uploaded_cv)
                
                # Hent jobtekst
                job_text = job_desc_manual
                if job_url:
                    with st.spinner("Henter jobopslag fra nettet..."):
                        url_text = get_text_from_url(job_url)
                        if len(url_text) > 100: job_text = url_text

                # --- TRIN 1: MATCH ANALYSE ---
                st.divider()
                with st.spinner("Analyserer match..."):
                    analysis_prompt = f"""
                    Du er rekrutteringsekspert. Lav en ultra-skarp analyse:
                    1. Hvad er de 3 vigtigste krav i jobopslaget?
                    2. Hvordan matcher dette CV kravene? (Vær ærlig)
                    3. Hvilke mangler skal vi 'skrive udenom' eller forklare i ansøgningen?
                    
                    Job: {job_text[:2500]}
                    CV: {cv_text[:2500]}
                    """
                    
                    analysis_res = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "system", "content": "Du er en professionel rekrutteringskonsulent."},
                                  {"role": "user", "content": analysis_prompt}]
                    )
                    st.subheader("📊 Match Analyse")
                    st.info(analysis_res.choices[0].message.content)

                # --- TRIN 2: ANSØGNING ---
                with st.spinner(f"Skriver en {selected_tone.lower()} ansøgning..."):
                    tone_desc = tone_prompts[selected_tone]
                    ans_prompt = f"""
                    Skriv en målrettet jobansøgning til {title} hos {company}.
                    Tonen skal være {tone_desc}.
                    
                    Brug denne analyse til at prioritere indholdet: {analysis_res.choices[0].message.content}
                    
                    CV: {cv_text}
                    Jobopslag: {job_text}
                    """
                    
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "system", "content": "Du er ekspert i at skrive succesfulde jobansøgninger."},
                                  {"role": "user", "content": ans_prompt}]
                    )
                    ans_text = response.choices[0].message.content
                    
                    # Gem i database
                    conn = sqlite3.connect(db_path)
                    c = conn.cursor()
                    c.execute("INSERT INTO archive (date, company, title, ansogning, opslag, tone) VALUES (?, ?, ?, ?, ?, ?)",
                              (datetime.now().strftime("%Y-%m-%d %H:%M"), company, title, ans_text, job_text, selected_tone))
                    conn.commit()
                    conn.close()
                    
                    st.subheader("📝 Din nye ansøgning")
                    st.success(f"Genereret med stilen: {selected_tone}")
                    st.write(ans_text)
                    
                    # Downloads
                    st.download_button("Hent som PDF 📄", create_pdf(ans_text), f"Ansogning_{company}.pdf")
            
            except Exception as e:
                st.error(f"Der opstod en fejl: {e}")

# --- ARKIV ---
with tabs[1]:
    st.header("📁 Gemte Ansøgninger")
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query("SELECT * FROM archive ORDER BY id DESC", conn)
        conn.close()
        for i, row in df.iterrows():
            with st.expander(f"📌 {row['company']} - {row['title']} ({row['date']})"):
                st.write(f"**Valgt tone:** {row.get('tone', 'Ikke angivet')}")
                st.write(row['ansogning'])

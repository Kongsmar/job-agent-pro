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
db_path = "job_archive_v7.db"

def init_db():
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS archive
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  date TEXT, company TEXT, title TEXT, 
                  ansogning TEXT, opslag TEXT, tone_level INTEGER)''')
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
    except Exception as e:
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
st.title("💼 Job Agent Pro: Analyse & Ansøgning")

tabs = st.tabs(["🚀 Ny Analyse & Ansøgning", "📁 Arkiv"])

with tabs[0]:
    with st.sidebar:
        st.header("⚙️ Din Profil")
        api_key = st.secrets.get("OPENAI_API_KEY")
        uploaded_cv = st.file_uploader("1. Upload dit CV (PDF)", type="pdf")
        uploaded_template = st.file_uploader("2. Upload Word-skabelon (.docx)", type="docx")
        
        st.divider()
        st.subheader("🎭 Personligheds-filter")
        # Slider fra 1 (Formel) til 5 (Personlig/Kreativ)
        tone_val = st.sidebar.slider("Toneleje", 1, 5, 3, help="1: Meget Formel/Konservativ | 3: Professionel | 5: Meget Personlig/Kreativ")
        
        tone_map = {
            1: "meget formel, korrekt og konservativ. Brug 'De/Dem' hvis passende og et højtideligt sprog.",
            2: "professionel, saglig og forretningsorienteret.",
            3: "moderne, balanceret og engageret professionel.",
            4: "personlig, varm og fortællende med fokus på værdier.",
            5: "meget personlig, kreativ og modig. Skil dig ud med en unik stemme."
        }

    st.subheader("Job Detaljer")
    c1, c2 = st.columns(2)
    with c1: company = st.text_input("Virksomhed:")
    with c2: title = st.text_input("Jobtitel:")
    
    job_url = st.text_input("Link til jobopslag:")
    job_desc_manual = st.text_area("Eller indsæt jobtekst her:", height=150)

    if st.button("Start Match-Analyse & Generering ✨"):
        if not api_key or not uploaded_cv or (not job_url and not job_desc_manual):
            st.error("Mangler API-nøgle, CV eller Jobbeskrivelse.")
        else:
            try:
                client = OpenAI(api_key=api_key)
                cv_text = extract_text_from_pdf(uploaded_cv)
                
                # Hent jobtekst
                job_text = job_desc_manual
                if job_url:
                    with st.spinner("Henter jobopslag..."):
                        url_text = get_text_from_url(job_url)
                        if len(url_text) > 200: job_text = url_text

                # --- TRIN 1: ANALYSE ---
                st.divider()
                with st.spinner("Analyserer match mellem CV og Job..."):
                    analysis_prompt = f"""
                    Du er en rekrutteringsekspert. Lav en kort og præcis analyse af følgende:
                    1. Hvad er de 3 vigtigste krav i jobopslaget?
                    2. Hvordan matcher kandidatens CV disse krav?
                    3. Er der nogle 'gaps' (mangler), som ansøgningen skal adressere?
                    
                    Jobopslag: {job_text[:2000]}
                    CV: {cv_text[:2000]}
                    """
                    
                    analysis_res = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "system", "content": "Du er en ærlig rekrutteringskonsulent."},
                                  {"role": "user", "content": analysis_prompt}]
                    )
                    st.subheader("📊 Match Analyse")
                    st.info(analysis_res.choices[0].message.content)

                # --- TRIN 2: ANSØGNING ---
                with st.spinner("Skriver ansøgning baseret på analyse og valgt tone..."):
                    tone_desc = tone_map[tone_val]
                    ans_prompt = f"""
                    Skriv en målrettet ansøgning til stillingen som {title} hos {company}.
                    Tonen skal være {tone_desc}.
                    Brug denne analyse til at fremhæve de rigtige ting: {analysis_res.choices[0].message.content}
                    
                    CV data: {cv_text}
                    Jobopslag: {job_text}
                    """
                    
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "system", "content": "Du er en ekspert i at skrive jobansøgninger på dansk."},
                                  {"role": "user", "content": ans_prompt}]
                    )
                    ans_text = response.choices[0].message.content
                    
                    # Gem i database
                    conn = sqlite3.connect(db_path)
                    c = conn.cursor()
                    c.execute("INSERT INTO archive (date, company, title, ansogning, opslag, tone_level) VALUES (?, ?, ?, ?, ?, ?)",
                              (datetime.now().strftime("%Y-%m-%d %H:%M"), company, title, ans_text, job_text, tone_val))
                    conn.commit()
                    conn.close()
                    
                    st.subheader("📝 Genereret Ansøgning")
                    st.success(f"Toneniveau: {tone_val}/5")
                    st.write(ans_text)
                    
                    # Downloads (som før)
                    # ... [Koden for download knapper herfra er den samme som tidligere version] ...
                    st.download_button("Hent som PDF", create_pdf(ans_text), f"Ansøgning_{company}.pdf")

            except Exception as e:
                st.error(f"Fejl: {e}")

# --- ARKIV FANEN ---
with tabs[1]:
    st.header("📁 Arkiv")
    # ... [Samme arkiv logik som før] ...

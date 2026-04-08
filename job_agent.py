import streamlit as st
import google.generativeai as genai
import io
import os
import sqlite3
import pandas as pd
from datetime import datetime
from docx import Document
from fpdf import FPDF

# --- KONFIGURATION & DATABASE ---
st.set_page_config(page_title="Job Agent Pro", page_icon="💼", layout="wide")

db_path = "job_archive_v3.db"

def init_db():
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS archive
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  date TEXT, company TEXT, title TEXT, 
                  ansogning TEXT, opslag TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- HJÆLPEFUNKTIONER ---
def create_pdf(text):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    # Rens tekst for specialtegn der driller PDF
    clean_text = text.encode('latin-1', 'replace').decode('latin-1')
    pdf.multi_cell(0, 10, txt=clean_text)
    return pdf.output(dest='S').encode('latin-1')

def fill_word_template(template_file, content, company_name):
    try:
        doc = Document(template_file)
        data_map = {
            "{{ANSOGNING}}": content,
            "{{VIRKSOMHED}}": company_name,
            "{{DATO}}": datetime.now().strftime("%d. %m. %Y")
        }
        for p in doc.paragraphs:
            for key, value in data_map.items():
                if key in p.text:
                    p.text = p.text.replace(key, value)
        
        target_stream = io.BytesIO()
        doc.save(target_stream)
        target_stream.seek(0)
        return target_stream
    except:
        return None

# --- APP LAYOUT ---
st.title("💼 Din Personlige Job Agent")

tabs = st.tabs(["🚀 Ny Ansøgning", "📁 Permanent Arkiv"])

with tabs[0]:
    with st.sidebar:
        st.header("⚙️ Din Profil")
        api_key = st.secrets.get("GEMINI_API_KEY")
        st.divider()
        user_cv = st.text_area("Dit Master CV (Tekst):", height=300)
        uploaded_template = st.file_uploader("Upload Word-skabelon (.docx)", type="docx")
        st.info("Husk: Skabelonen skal indeholde {{ANSOGNING}}, {{VIRKSOMHED}} og {{DATO}}")

    col1, col2 = st.columns(2)
    with col1: company = st.text_input("Virksomhedens navn:")
    with col2: title = st.text_input("Jobtitel:")
    
    job_desc = st.text_area("Indsæt jobopslaget her (tekst eller kopieret indhold):", height=250)

    if st.button("Generer & Arkiver ✨"):
        if not api_key:
            st.error("Systemfejl: API-nøgle mangler i Secrets.")
        elif not user_cv or not job_desc or not company:
            st.error("Udfyld venligst alle felter før generering.")
        else:
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel('gemini-pro')
                
                with st.spinner("AI Agenten analyserer og skriver..."):
                    prompt = f"Skriv en motiveret ansøgning til {title} hos {company}. CV: {user_cv}. Opslag: {job_desc}. Sproget skal være dansk og professionelt."
                    response = model.generate_content(prompt)
                    ans_text = response.text
                    
                    # Gem i database
                    conn = sqlite3.connect(db_path)
                    c = conn.cursor()
                    c.execute("INSERT INTO archive (date, company, title, ansogning, opslag) VALUES (?, ?, ?, ?, ?)",
                              (datetime.now().strftime("%Y-%m-%d %H:%M"), company, title, ans_text, job_desc))
                    conn.commit()
                    conn.close()
                    
                    st.divider()
                    st.subheader("Resultat:")
                    st.write(ans_text)
                    
                    # Download knapper
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        if uploaded_template:
                            w_file = fill_word_template(uploaded_template, ans_text, company)
                            st.download_button("Hent Word-fil 📄", w_file, f"Ansogning_{company}.docx")
                    with c2:
                        st.download_button("Hent Ansøgning (.txt)", ans_text, f"Ansogning_{company}.txt")
                    with c3:
                        pdf_file = create_pdf(job_desc)
                        st.download_button("Hent Opslag (PDF) 📄", pdf_file, f"Jobopslag_{company}.pdf")
            except Exception as e:
                st.error(f"Fejl: {e}")

with tabs[1]:
    st.header("Tidligere Ansøgninger")
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query("SELECT * FROM archive ORDER BY id DESC", conn)
        conn.close()
        
        for i, row in df.iterrows():
            with st.expander(f"📌 {row['company']} - {row['title']} ({row['date']})"):
                ca, cb = st.columns(2)
                with ca:
                    st.write("**Ansøgning:**")
                    st.write(row['ansogning'])
                    st.download_button("Download Ansøgning", row['ansogning'], f"Arkiv_{row['company']}.txt", key=f"a_{row['id']}")
                with cb:
                    st.write("**Originalt Opslag:**")
                    st.write(row['opslag'])
                    pdf_arkiv = create_pdf(row['opslag'])
                    st.download_button("Download Opslag (PDF)", pdf_arkiv, f"Arkiv_Opslag_{row['company']}.pdf", key=f"o_{row['id']}")

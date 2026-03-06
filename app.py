import os
import io
import json
import uuid
import streamlit as st
from datetime import datetime

from src.db import get_session, User, Project, Document, Run, Answer
from src.auth import hash_password, verify_password
from src.parser import parse_questionnaire
from src.retriever import chunk_text, BM25Retriever
from src.generator import generate_answer
from src.export_docx import export_to_docx

st.set_page_config(page_title="Questionnaire Answering Tool", layout="wide")

DB = get_session()

UPLOAD_DIR = "uploads"
Q_UPLOAD_DIR = os.path.join(UPLOAD_DIR, "questionnaires")
R_UPLOAD_DIR = os.path.join(UPLOAD_DIR, "references")
EXPORT_DIR = os.path.join(UPLOAD_DIR, "exports")
os.makedirs(Q_UPLOAD_DIR, exist_ok=True)
os.makedirs(R_UPLOAD_DIR, exist_ok=True)
os.makedirs(EXPORT_DIR, exist_ok=True)

# -----------------------------
# Helpers
# -----------------------------
def db_get_user_by_email(email: str):
    return DB.query(User).filter(User.email == email).first()

def db_create_user(email: str, password: str):
    u = User(email=email, password_hash=hash_password(password))
    DB.add(u)
    DB.commit()
    DB.refresh(u)
    return u

def db_get_or_create_project(user_id: int, name="Default Project"):
    p = DB.query(Project).filter(Project.user_id == user_id, Project.name == name).first()
    if p:
        return p
    p = Project(user_id=user_id, name=name)
    DB.add(p)
    DB.commit()
    DB.refresh(p)
    return p

def save_uploaded_file(uploaded_file, folder: str):
    file_id = str(uuid.uuid4())[:8]
    safe_name = uploaded_file.name.replace("/", "_").replace("\\", "_")
    path = os.path.join(folder, f"{file_id}_{safe_name}")
    with open(path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return path

def read_text_from_reference(file_bytes: bytes, filename: str) -> str:
    name = filename.lower()
    if name.endswith(".txt"):
        return file_bytes.decode("utf-8", errors="ignore")
    if name.endswith(".pdf"):
        # reuse pdfplumber via parser dependency if installed
        import pdfplumber
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            return "\n".join((page.extract_text() or "") for page in pdf.pages)
    # fallback: treat as text
    return file_bytes.decode("utf-8", errors="ignore")

def load_reference_chunks(project_id: int):
    """Build chunk index from DB reference documents."""
    refs = DB.query(Document).filter(
        Document.project_id == project_id,
        Document.doc_type == "reference"
    ).all()

    chunks_meta = []
    for d in refs:
        chunks = chunk_text(d.text, chunk_size_words=220)
        for i, ch in enumerate(chunks):
            chunks_meta.append({
                "doc_name": d.filename,
                "chunk_id": i,
                "text": ch
            })
    return chunks_meta

def create_run(project_id: int):
    r = Run(project_id=project_id)
    DB.add(r)
    DB.commit()
    DB.refresh(r)
    return r

def store_answer(run_id: int, q: str, answer: str, citations, evidence):
    a = Answer(
        run_id=run_id,
        question=q,
        answer=answer,
        citations_json=json.dumps(citations, ensure_ascii=False),
        evidence_json=json.dumps(evidence, ensure_ascii=False),
        edited_answer=None
    )
    DB.add(a)

def get_latest_run_answers(project_id: int):
    run = DB.query(Run).filter(Run.project_id == project_id).order_by(Run.id.desc()).first()
    if not run:
        return None, []
    answers = DB.query(Answer).filter(Answer.run_id == run.id).all()
    return run, answers

def answers_to_map(answers):
    out = {}
    for a in answers:
        out[a.question] = {
            "answer": a.answer,
            "citations": json.loads(a.citations_json or "[]"),
            "evidence": json.loads(a.evidence_json or "[]"),
            "edited_answer": a.edited_answer
        }
    return out

def compute_coverage(answers):
    total = len(answers)
    with_citations = 0
    not_found = 0
    for a in answers:
        cits = json.loads(a.citations_json or "[]")
        if a.answer.strip().lower().startswith("not found"):
            not_found += 1
        if cits and not a.answer.strip().lower().startswith("not found"):
            with_citations += 1
    return total, with_citations, not_found


# -----------------------------
# Session state
# -----------------------------
if "user_id" not in st.session_state:
    st.session_state.user_id = None
if "project_id" not in st.session_state:
    st.session_state.project_id = None
if "questions" not in st.session_state:
    st.session_state.questions = []
if "questionnaire_filename" not in st.session_state:
    st.session_state.questionnaire_filename = None

# -----------------------------
# Sidebar: Auth
# -----------------------------
st.sidebar.title("Auth")

auth_mode = st.sidebar.radio("Choose", ["Login", "Sign Up"])

email = st.sidebar.text_input("Email")
password = st.sidebar.text_input("Password", type="password")

if auth_mode == "Sign Up":
    if st.sidebar.button("Create Account"):
        if not email or not password:
            st.sidebar.error("Email and password required.")
        elif db_get_user_by_email(email):
            st.sidebar.error("User already exists. Please login.")
        else:
            u = db_create_user(email, password)
            st.session_state.user_id = u.id
            p = db_get_or_create_project(u.id)
            st.session_state.project_id = p.id
            st.sidebar.success("Account created and logged in!")

if auth_mode == "Login":
    if st.sidebar.button("Login"):
        u = db_get_user_by_email(email)
        if not u:
            st.sidebar.error("User not found. Please sign up.")
        elif not verify_password(password, u.password_hash):
            st.sidebar.error("Incorrect password.")
        else:
            st.session_state.user_id = u.id
            p = db_get_or_create_project(u.id)
            st.session_state.project_id = p.id
            st.sidebar.success("Logged in!")

if st.sidebar.button("Logout"):
    st.session_state.user_id = None
    st.session_state.project_id = None
    st.session_state.questions = []
    st.session_state.questionnaire_filename = None
    st.sidebar.info("Logged out.")

# API key
st.sidebar.divider()
st.sidebar.subheader("LLM API Key")
api_key = st.sidebar.text_input("OpenAI API Key", type="password", value=os.getenv("OPENAI_API_KEY", ""))

# -----------------------------
# Main UI
# -----------------------------
st.title("PaySage Questionnaire Copilot")
st.caption("Upload questionnaire + references → Generate grounded answers with citations → Review/Edit → Export DOCX")

if not st.session_state.user_id:
    st.info("Please login or sign up from the sidebar to continue.")
    st.stop()

project_id = st.session_state.project_id

# -----------------------------
# Section: Uploads
# -----------------------------
st.header("1) Upload Questionnaire and Reference Documents")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Upload Questionnaire (CSV/XLSX/PDF)")
    questionnaire_file = st.file_uploader("Questionnaire file", type=["csv", "xlsx", "pdf"], key="q_upload")

with col2:
    st.subheader("Upload Reference Documents (TXT/PDF)")
    ref_files = st.file_uploader("Reference files", type=["txt", "pdf"], accept_multiple_files=True, key="ref_upload")

if questionnaire_file is not None:
    # Save questionnaire file
    q_path = save_uploaded_file(questionnaire_file, Q_UPLOAD_DIR)
    st.session_state.questionnaire_filename = os.path.basename(q_path)

    # Parse questions
    q_bytes = questionnaire_file.getvalue()
    try:
        questions = parse_questionnaire(q_bytes, questionnaire_file.name)
        # small cleanup: remove empty and duplicates
        cleaned = []
        seen = set()
        for q in questions:
            q2 = q.strip()
            if not q2:
                continue
            if q2 in seen:
                continue
            seen.add(q2)
            cleaned.append(q2)
        st.session_state.questions = cleaned
        st.success(f"Parsed {len(cleaned)} questions from questionnaire.")
    except Exception as e:
        st.error(f"Failed to parse questionnaire: {e}")

if ref_files:
    added = 0
    for rf in ref_files:
        b = rf.getvalue()
        text = read_text_from_reference(b, rf.name).strip()
        if not text:
            continue
        # store in DB
        d = Document(
            project_id=project_id,
            filename=rf.name,
            text=text,
            doc_type="reference",
            created_at=datetime.utcnow()
        )
        DB.add(d)
        added += 1
    DB.commit()
    st.success(f"Stored {added} reference document(s) in database.")

# show current reference doc count
ref_count = DB.query(Document).filter(Document.project_id == project_id, Document.doc_type == "reference").count()
st.write(f"📌 Reference documents currently stored: **{ref_count}**")

# -----------------------------
# Section: Generate
# -----------------------------
st.header("2) Generate Answers (Grounded + Citations)")

threshold = st.slider("Retrieval threshold (higher = stricter 'Not found')", 0.1, 5.0, 1.0, 0.1)

if st.button("Generate Answers", type="primary"):
    if not api_key:
        st.warning("⚠️ No OpenAI API key provided. Running in fallback mode (answers generated from reference text).")
    if not st.session_state.questions:
        st.error("Upload a questionnaire first (and ensure questions are parsed).")
        st.stop()
    if ref_count == 0:
        st.error("Upload at least 1 reference document.")
        st.stop()

    chunks_meta = load_reference_chunks(project_id)
    retriever = BM25Retriever(chunks_meta)

    run = create_run(project_id)

    progress = st.progress(0)
    status = st.empty()

    for i, q in enumerate(st.session_state.questions):
        status.write(f"Answering: {q}")
        top_chunks = retriever.search(q, top_k=3)
        answer, citations, evidence = generate_answer(q, top_chunks, api_key=api_key, threshold=threshold)

        store_answer(run.id, q, answer, citations, evidence)
        progress.progress((i + 1) / len(st.session_state.questions))

    DB.commit()
    st.success("✅ Answers generated and stored!")
    status.empty()

# -----------------------------
# Section: Review/Edit + Coverage + Evidence
# -----------------------------
st.header("3) Review & Edit Answers (Before Export)")

latest_run, latest_answers = get_latest_run_answers(project_id)

if not latest_run:
    st.info("No runs yet. Upload docs and click Generate Answers.")
    st.stop()

total, with_cits, not_found = compute_coverage(latest_answers)

st.subheader("Coverage Summary ✅ (Nice-to-have)")
c1, c2, c3 = st.columns(3)
c1.metric("Total Questions", total)
c2.metric("Answered with Citations", with_cits)
c3.metric("Not found", not_found)

answers_map = answers_to_map(latest_answers)

st.subheader("Answers Table")
for idx, q in enumerate(st.session_state.questions or [a.question for a in latest_answers], start=1):
    a = answers_map.get(q)
    if not a:
        continue

    with st.expander(f"{idx}. {q}", expanded=(idx <= 2)):
        st.write("**Generated Answer:**")
        st.write(a["answer"])

        st.write("**Citations:**")
        st.write(", ".join(a["citations"]) if a["citations"] else "None")

        st.write("**Evidence Snippets ✅ (Nice-to-have)**")
        ev = a.get("evidence", [])
        if not ev:
            st.write("No evidence available.")
        else:
            for item in ev:
                st.code(f"{item['citation']}: {item['snippet']}")

        st.write("**Edit Answer (optional):**")
        new_text = st.text_area(
            "Edited answer",
            value=a.get("edited_answer") or "",
            key=f"edit_{latest_run.id}_{idx}",
            placeholder="Write improved answer here (leave empty to keep generated answer)"
        )

        if st.button("Save edit", key=f"save_{latest_run.id}_{idx}"):
            row = DB.query(Answer).filter(Answer.run_id == latest_run.id, Answer.question == q).first()
            row.edited_answer = new_text.strip() if new_text.strip() else None
            DB.commit()
            st.success("Saved!")

# -----------------------------
# Section: Export DOCX
# -----------------------------
st.header("4) Export Document (DOCX)")

export_name = st.text_input("Export filename", value=f"questionnaire_response_run_{latest_run.id}.docx")

if st.button("Generate DOCX Export"):
    # Build export map including edits
    # Refresh latest answers
    refreshed = DB.query(Answer).filter(Answer.run_id == latest_run.id).all()
    amap = {}
    for a in refreshed:
        amap[a.question] = {
            "answer": a.answer,
            "citations": json.loads(a.citations_json or "[]"),
            "edited_answer": a.edited_answer
        }

    out_path = os.path.join(EXPORT_DIR, export_name)
    questions_for_export = st.session_state.questions or [a.question for a in refreshed]
    export_to_docx(questions_for_export, amap, out_path)

    with open(out_path, "rb") as f:
        st.download_button(
            "⬇️ Download DOCX",
            data=f,
            file_name=export_name,
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
    st.success("Export ready!")
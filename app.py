import streamlit as st
from pipeline import PaperAgentSystem
import base64
from pathlib import Path
from export_files import create_pdf, create_docx, create_pptx
import os
def set_background(image_file):
    image_path = Path(__file__).parent / image_file

    if image_path.exists():
        encoded_image = base64.b64encode(
            image_path.read_bytes()
        ).decode()

        st.markdown(
            f"""
            <style>
            .stApp {{
                background-image:
                    linear-gradient(
                        rgba(3, 12, 30, 0.65),
                        rgba(3, 12, 30, 0.75)
                    ),
                    url("data:image/jpeg;base64,{encoded_image}");
                background-size: cover;
                background-position: center;
                background-attachment: fixed;
            }}
            </style>
            """,
            unsafe_allow_html=True
        )

st.set_page_config(page_title="Paper-to-Presentation & Viva Agent", page_icon="📚", layout="wide")
set_background("background.jpg")


# ---------- 3D / Glassmorphism UI theme ----------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
.stApp {
  font-family: 'Inter', sans-serif;
  background-color: #090b1b;
  background-attachment: fixed;
}
.block-container { padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1450px; }
h1 { color: #f1eaff !important; font-weight: 800 !important; letter-spacing: -1.4px; text-shadow: 0 0 26px rgba(167,139,250,.28); }
h2, h3 { color: #d9ccff !important; }
section[data-testid="stSidebar"] { background: linear-gradient(160deg, rgba(25,22,53,.96), rgba(8,18,35,.96)); border-right: 1px solid rgba(167,139,250,.24); box-shadow: 12px 0 45px rgba(0,0,0,.28); }
section[data-testid="stSidebar"] > div { padding-top: 1.6rem; }
div[data-testid="stVerticalBlockBorderWrapper"], div[data-testid="stExpander"], [data-testid="stFileUploader"] {
  background: linear-gradient(145deg, rgba(255,255,255,.075), rgba(255,255,255,.025)) !important;
  border: 1px solid rgba(167,139,250,.24) !important; border-radius: 20px !important;
  box-shadow: 0 18px 38px rgba(0,0,0,.24), inset 0 1px 0 rgba(255,255,255,.10), 0 0 22px rgba(124,58,237,.06);
  backdrop-filter: blur(18px);
}
[data-testid="stFileUploader"] { padding: 18px !important; border: 1px dashed rgba(103,232,249,.45) !important; }
.stTextInput input, .stSelectbox [data-baseweb="select"] > div, [data-testid="stTextArea"] textarea {
  background: rgba(17,24,49,.82) !important; color: #f5f3ff !important; border: 1px solid rgba(139,92,246,.38) !important; border-radius: 13px !important; box-shadow: inset 0 2px 8px rgba(0,0,0,.22);
}
label, .stMarkdown, p, span { color: #e5e7eb; }
.stButton > button, .stDownloadButton > button {
  background: linear-gradient(135deg, #8b5cf6 0%, #6366f1 48%, #0891b2 100%) !important; color: white !important;
  border: 1px solid rgba(255,255,255,.20) !important; border-radius: 14px !important; padding: .72rem 1.25rem !important; font-weight: 700 !important;
  box-shadow: 0 8px 0 rgba(45,35,110,.65), 0 15px 28px rgba(99,102,241,.25);
  transition: transform .22s ease, box-shadow .22s ease, filter .22s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover { transform: translateY(-3px); filter: brightness(1.12); box-shadow: 0 11px 0 rgba(45,35,110,.55), 0 22px 35px rgba(34,211,238,.22); }
.stButton > button:active { transform: translateY(2px); box-shadow: 0 3px 0 rgba(45,35,110,.7); }
[data-testid="stExpander"] summary { color: #e9ddff !important; font-weight: 600; }
[data-testid="stAlert"] { border-radius: 14px; border: 1px solid rgba(103,232,249,.22); background: rgba(30,41,70,.58); }
</style>
""", unsafe_allow_html=True)

st.title("📚 Paper-to-Presentation & Viva Agent")
st.caption("Upload a research paper and generate a summary, concepts, slides, or Viva practice.")

with st.sidebar:
    st.header("⚙️ Setup")
    api_key = st.text_input("Gemini API key", type="password")
    task = st.selectbox(
        "Choose task",
        ["Complete report", "Summarizer", "Concept Extractor", "Slide Generator", "Viva Agent", "Ask a question"]
    )
    n_questions = st.slider("Number of Viva questions", min_value=3, max_value=15, value=8)
    st.info("Your paper is processed in this session. Avoid uploading confidential papers.")

request = st.text_input(
    "Optional: type your request (automatic intent detection)",
    placeholder="e.g., Explain the methodology / make slides / prepare viva questions"
)
uploaded = st.file_uploader("Upload research paper (PDF)", type=["pdf"])

if "agent_system" not in st.session_state:
    st.session_state.agent_system = None
if "paper_signature" not in st.session_state:
    st.session_state.paper_signature = None

if uploaded and api_key:
    signature = (uploaded.name, uploaded.size)
    if st.session_state.paper_signature != signature or st.session_state.agent_system is None:
        try:
            with st.spinner("Reading PDF and creating the ChromaDB index..."):
                system = PaperAgentSystem(api_key)
                info = system.load_paper(uploaded.getvalue(), uploaded.name)
                st.session_state.agent_system = system
                st.session_state.paper_signature = signature
                st.success(f"Paper indexed: {info['chunks']} chunks | {info['characters']:,} characters")
        except Exception as e:
            st.error(f"PDF/indexing failed: {e}")

    if st.button("🚀 Run Agents", type="primary", disabled=st.session_state.agent_system is None):
        try:
            with st.spinner("Detecting intent, retrieving context, and running agent(s)..."):
                result = st.session_state.agent_system.run(
                    uploaded.getvalue(), uploaded.name, task, n_questions, request
                )
            st.success(f"Intent detected/routed: **{result['intent']}**")
            with st.expander("🔎 Agentic RAG decision (acceptance criterion 5)", expanded=True):
                retrieval = result["retrieval"]
                st.write("**Decision:**", "Retrieve paper context" if retrieval["decision"] else "No retrieval")
                st.write("**Reason:**", retrieval["reason"])
                st.write("**Chunks retrieved:**", len(retrieval["chunks"]))
                if retrieval["chunks"]:
                    st.caption("Preview of retrieved evidence:")
                    st.code(retrieval["chunks"][0][:1200])
            for heading, content in result["outputs"].items():
                st.subheader(heading)
                st.markdown(content)
                
            # Generate downloadable files
            report_content = result["report"]

            pdf_file = create_pdf(report_content)
            docx_file = create_docx(report_content)
            pptx_file = create_pptx(report_content)

            st.divider()
            st.subheader("📥 Download Your Files")

            col1, col2, col3 = st.columns(3)

            with col1:
                with open(pdf_file, "rb") as f:
                    st.download_button(
                        label="⬇️ Download PDF",
                        data=f.read(),
                        file_name="paper_agent_report.pdf",
                        mime="application/pdf",
                        key="download_pdf",
                    )

            with col2:
                with open(docx_file, "rb") as f:
                    st.download_button(
                        label="📝 Download Editable Word",
                        data=f.read(),
                        file_name="paper_agent_report.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key="download_docx",
                    )

            with col3:
                with open(pptx_file, "rb") as f:
                    st.download_button(
                        label="📊 Download Editable PPT",
                        data=f.read(),
                        file_name="paper_presentation.pptx",
                        mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                        key="download_pptx",
                    )
        except Exception as e:
            st.error(f"Agent execution failed: {e}")
            st.exception(e)
elif uploaded and not api_key:
    st.warning("Enter your Gemini API key in the sidebar before processing.")

with st.expander("🧪 Prompt engineering used (acceptance criterion 3)"):
    st.markdown("""
**Intent system prompt (zero-shot classification):**  
You are an intent router for a research-paper assistant. Return exactly one label: summary, concepts, slides, viva, question, complete, or help.

**Intent user prompt (few-shot examples):**
- make presentation slides → slides
- explain the main contribution → question
- prepare oral exam questions → viva
- give me everything → complete

**Answer system prompt (grounded zero-shot):**  
Use provided paper context for factual claims. If context does not contain an answer, say the paper does not specify it. Do not invent results, numbers, citations, or claims.

**Reflection prompt:**  
Improve the draft for accuracy, clarity, completeness, and grounding. Remove unsupported claims. Return corrected final answer only.
""")

with st.expander("🧩 Architecture / acceptance criteria"):
    st.markdown("""
- **LLM:** Gemini API (`gemini-3.8-flash`)
- **GUI:** Streamlit upload, task selector, request input, output and download
- **Prompt engineering:** system/user prompts, zero-shot + few-shot routing, reflection pass
- **LangChain + LCEL:** `ChatPromptTemplate | ChatGoogleGenerativeAI | StrOutputParser`
- **Agentic RAG:** retrieval policy decides whether paper context is needed; paper tasks retrieve
- **Intent routing:** intent classifier routes to summary/concepts/slides/viva/question/complete
- **Vector DB:** ChromaDB stores chunk embeddings and performs similarity search
""")

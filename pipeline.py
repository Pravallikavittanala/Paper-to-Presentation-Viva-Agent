import os
import io
import uuid
from typing import Dict, Any, List

from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser


class PaperAgentSystem:
    """Paper-to-Presentation & Viva pipeline with intent routing and agentic RAG."""

    def __init__(self, api_key: str):
        os.environ["GOOGLE_API_KEY"] = api_key
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-3.8-flash",
            temperature=0.2,
        )
        self.embeddings = GoogleGenerativeAIEmbeddings(
            model="gemini-embedding-001"
        )
        self.db = None
        self.paper_name = ""
        self.paper_text = ""
        self.last_retrieval = {"used": False, "reason": "No paper loaded", "chunks": []}

        # Prompt engineering: system + user messages, explicit instructions,
        # zero-shot classification, few-shot examples, and reflection/self-check.
        self.intent_prompt = ChatPromptTemplate.from_messages([
            ("system",
             "You are an intent router for a research-paper assistant. "
             "Return exactly one label: summary, concepts, slides, viva, question, complete, or help. "
             "Use question for a specific question about the uploaded paper. "
             "Use complete when the user asks for a complete report/all outputs."),
            ("human",
             "Examples:\n"
             "User: make presentation slides -> slides\n"
             "User: explain the main contribution -> question\n"
             "User: prepare oral exam questions -> viva\n"
             "User: give me everything -> complete\n\n"
             "Classify this request: {request}\nLabel:")
        ])
        self.intent_chain = self.intent_prompt | self.llm | StrOutputParser()

        self.answer_prompt = ChatPromptTemplate.from_messages([
            ("system",
             "You are a careful academic assistant. Use the provided paper context for factual claims. "
             "If the context does not contain an answer, clearly say that the paper does not specify it. "
             "Do not invent results, numbers, citations, or claims. "
             "Write clear student-friendly English. Prompt technique: zero-shot instruction + grounded context."),
            ("human",
             "Task: {task}\nRequest: {request}\nPaper: {paper_name}\n"
             "Retrieved context:\n{context}\n\n"
             "Produce the requested output. For slides, create 8 numbered slides with a title "
             "and 3–5 concise bullets each. For viva, include questions and model answers.")
        ])
        self.answer_chain = self.answer_prompt | self.llm | StrOutputParser()

        self.reflection_prompt = ChatPromptTemplate.from_messages([
            ("system",
             "You are a reflection/checking agent. Improve the draft for accuracy, clarity, "
             "completeness, and grounding. Remove unsupported claims. Do not reveal hidden chain "
             "of thought; provide only the corrected final answer."),
            ("human",
             "Paper context:\n{context}\n\nDraft:\n{draft}\n\n"
             "Return the corrected final answer only.")
        ])
        self.reflection_chain = self.reflection_prompt | self.llm | StrOutputParser()

    def _extract_pdf(self, pdf_bytes: bytes) -> str:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        text = "\n".join(pages).strip()
        if not text:
            raise ValueError("No selectable text found in PDF. Try a text-based PDF (not scanned images).")
        return text

    def _build_vector_db(self, text: str):
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, chunk_overlap=150, separators=["\n\n", "\n", ". ", " ", ""]
        )
        chunks = splitter.split_text(text)
        docs = []
        from langchain_core.documents import Document
        for i, chunk in enumerate(chunks):
            docs.append(Document(
                page_content=chunk,
                metadata={"source": self.paper_name, "chunk": i}
            ))
        # A unique collection prevents different uploaded papers from mixing.
        self.db = Chroma.from_documents(
            documents=docs,
            embedding=self.embeddings,
            collection_name=f"paper_{uuid.uuid4().hex[:12]}",
        )
        return len(docs)

    def load_paper(self, pdf_bytes: bytes, filename: str) -> Dict[str, Any]:
        self.paper_name = filename
        self.paper_text = self._extract_pdf(pdf_bytes)
        chunk_count = self._build_vector_db(self.paper_text)
        return {"filename": filename, "characters": len(self.paper_text), "chunks": chunk_count}

    def detect_intent(self, request: str) -> str:
        """Route common requests locally so intent detection uses no Gemini call."""
        text = request.lower()
        if any(word in text for word in ("complete report", "everything", "all outputs", "full report", "generate all")):
            return "complete"
        if any(word in text for word in ("viva", "oral exam", "interview questions")):
            return "viva"
        if any(word in text for word in ("slide", "presentation", "ppt")):
            return "slides"
        if any(word in text for word in ("concept", "contribution", "limitation", "findings", "methodology")):
            return "concepts"
        if any(word in text for word in ("summar", "overview", "abstract")):
            return "summary"
        if any(word in text for word in ("help", "how to use", "what can you do")):
            return "help"
        return "question"

    def _agent_decides_retrieval(self, intent: str, request: str) -> Dict[str, Any]:
        """Simple transparent policy: paper-grounded tasks retrieve; help does not."""
        retrieve = intent in {"summary", "concepts", "slides", "viva", "question", "complete"}
        reason = (
            "This task needs evidence from the uploaded paper, so retrieve relevant chunks."
            if retrieve else
            "This is a general help request; paper retrieval is not necessary."
        )
        return {"retrieve": retrieve, "reason": reason}

    def _retrieve(self, query: str, k: int = 5) -> List[str]:
        if self.db is None:
            return []
        results = self.db.similarity_search(query, k=k)
        return [doc.page_content for doc in results]

    def _run_one_agent(self, task: str, request: str, context: str) -> str:
        task_instructions = {
            "summary": "Summarize under headings: Problem, Objective, Method, Results, Conclusion.",
            "concepts": "List key concepts, contributions, methodology, findings, and limitations.",
            "slides": "Create 8 presentation slides with a title and 3–5 bullets each.",
            "viva": "Create viva questions with clear model answers.",
            "question": "Answer the user's question accurately using the paper context.",
        }
        draft = self.answer_chain.invoke({
            "task": task_instructions.get(task, task),
            "request": request,
            "paper_name": self.paper_name,
            "context": context or "No paper context retrieved.",
        })
        # One generation call per individual task helps conserve API quota.
        return draft

    def run(self, pdf_bytes: bytes, filename: str, task: str = "Complete report",
            n_questions: int = 8, request: str = "") -> Dict[str, Any]:
        if self.db is None or filename != self.paper_name:
            self.load_paper(pdf_bytes, filename)

        # User's free-text request is routed automatically; task selector is fallback.
        request = (request or "").strip()
        if request:
            intent = self.detect_intent(request)
        else:
            task_map = {
                "Complete report": "complete",
                "Summarizer": "summary",
                "Concept Extractor": "concepts",
                "Slide Generator": "slides",
                "Viva Agent": "viva",
                "Ask a question": "question",
            }
            intent = task_map.get(task, "complete")
            request = {
                "summary": "Summarize this paper",
                "concepts": "Extract key concepts",
                "slides": "Create presentation slides",
                "viva": f"Generate {n_questions} viva questions and answers",
                "question": "Answer a question about this paper",
                "complete": "Generate a complete report with summary, concepts, slides, and viva",
            }.get(intent, "Generate complete report")

        if intent == "help":
            help_text = (
                "Upload a text-based research-paper PDF, choose a task, enter the number "
                "of viva questions if needed, and click Run Agents. The app can create a "
                "summary, key concepts, presentation slides, viva questions, or a complete report."
            )
            outputs = {"Help": help_text}
            report = "# Help\n\n" + help_text
            self.last_retrieval = {
                "used": False,
                "decision": False,
                "reason": "This is a general help request; paper retrieval is not necessary.",
                "chunks": [],
            }
            return {
                "intent": intent,
                "outputs": outputs,
                "report": report,
                "retrieval": self.last_retrieval,
                "paper": self.paper_name,
            }

        decision = self._agent_decides_retrieval(intent, request)
        chunks = self._retrieve(request, k=6) if decision["retrieve"] else []
        context = "\n\n--- Retrieved chunk ---\n\n".join(chunks)
        self.last_retrieval = {
            "used": bool(chunks),
            "decision": decision["retrieve"],
            "reason": decision["reason"],
            "chunks": chunks,
        }

        outputs = {}
        if intent == "complete":
            # FAST PATH: one Gemini call creates all four report sections.
            # Individual tasks also use one Gemini generation call.
            combined_task = (
                "Create one complete paper report with exactly these sections:\\n"
                "1. SUMMARY: Problem, Objective, Method, Results, Conclusion.\\n"
                "2. KEY CONCEPTS: concepts, contribution, methodology, findings, limitations.\\n"
                "3. PRESENTATION SLIDES: exactly 8 numbered slides, each with a title and 3–5 concise bullets.\\n"
                f"4. VIVA QUESTIONS & ANSWERS: exactly {n_questions} questions with clear model answers.\\n"
                "Keep all sections grounded only in the retrieved paper context. Do not invent facts. "
                "If something is absent, state that the paper does not specify it."
            )
            combined_prompt = ChatPromptTemplate.from_messages([
                ("system",
                 "You are a careful academic paper assistant. Produce accurate, student-friendly output. "
                 "Use only the supplied paper context; do not invent claims, numbers, or citations."),
                ("human",
                 "Paper: {paper_name}\\nRequest: {request}\\n\\n"
                 "Paper context:\\n{context}\\n\\n{instructions}")
            ])
            combined_chain = combined_prompt | self.llm | StrOutputParser()
            try:
                combined_report = combined_chain.invoke({
                    "paper_name": self.paper_name,
                    "request": request,
                    "context": context or "No paper context retrieved.",
                    "instructions": combined_task,
                })
            except Exception as exc:
                if "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc) or "quota" in str(exc).lower():
                    raise RuntimeError(
                        "Gemini API daily quota is exhausted. Wait for the quota reset or use a Google AI project with available quota."
                    ) from exc
                raise
            outputs["Complete Report"] = combined_report
        elif intent == "viva":
            outputs["Viva Questions & Answers"] = self._run_one_agent(
                "viva", f"Generate {n_questions} viva questions and answers", context
            )
        else:
            outputs[{"summary":"Summary","concepts":"Key Concepts","slides":"Presentation Slides",
                     "question":"Answer"}[intent]] = self._run_one_agent(intent, request, context)

        report = "\n\n".join(f"# {title}\n\n{content}" for title, content in outputs.items())
        return {
            "intent": intent,
            "outputs": outputs,
            "report": report,
            "retrieval": self.last_retrieval,
            "paper": self.paper_name,
        }

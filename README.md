# Paper-to-Presentation & Viva Agent (upgraded)

## Run
1. Open this folder in VS Code.
2. In terminal (PowerShell):
   ```powershell
   .venv\Scripts\python.exe -m pip install -r requirements.txt
   .venv\Scripts\python.exe -m streamlit run app.py
   ```
3. Enter your Gemini API key in the app sidebar and upload a text-based PDF.
4. Select a task or type a request for automatic intent detection; click **Run Agents**.

## Seven acceptance criteria
- Gemini API LLM
- Streamlit GUI
- Prompt engineering: zero-shot, few-shot examples, reflection; prompts visible in UI
- LangChain ChatPromptTemplate + LCEL (`prompt | llm | StrOutputParser`)
- Agentic RAG decision and retrieval explanation shown in UI
- LLM intent classifier and task routing
- ChromaDB vector embeddings and similarity search

## Note
Model names can change in the Gemini API. If Gemini returns a model-not-found error, use a model name available to your API key and update the `model=` value in `pipeline.py`.

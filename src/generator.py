import json
from openai import OpenAI

def build_prompt(question, retrieved_chunks):
    refs = "\n\n".join(
        [f"[{c['doc_name']}#chunk{c['chunk_id']}]\n{c['text']}" for c in retrieved_chunks]
    )

    return f"""
You are answering a structured compliance questionnaire.

RULES:
- Use ONLY the references below.
- If the answer is not explicitly supported by references, respond exactly: Not found in references.
- Always include citations for any answer you give.

Question:
{question}

References:
{refs}

Return STRICT JSON ONLY:
{{
  "answer": "...",
  "citations": ["doc#chunkX", "doc#chunkY"]
}}
"""

def generate_answer(question, retrieved_chunks, api_key=None, threshold=1.0):

    if not retrieved_chunks or retrieved_chunks[0]["score"] < threshold:
        return "Not found in references.", [], []

    # If API key not provided → fallback mode
    if not api_key:
        top = retrieved_chunks[0]

        answer = top["text"].split(".")[0] + "."
        citation = f"{top['doc_name']}#chunk{top['chunk_id']}"

        evidence = [{
            "citation": citation,
            "snippet": top["text"][:200]
        }]

        return answer, [citation], evidence

    # --- normal OpenAI mode ---
    client = OpenAI(api_key=api_key)

    prompt = build_prompt(question, retrieved_chunks)

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )

    text = resp.choices[0].message.content.strip()

    try:
        obj = json.loads(text)
        answer = obj.get("answer", "")
        citations = obj.get("citations", [])
    except:
        answer = "Not found in references."
        citations = []

    evidence = [{
        "citation": f"{c['doc_name']}#chunk{c['chunk_id']}",
        "snippet": c["text"][:200]
    } for c in retrieved_chunks[:2]]

    return answer, citations, evidence

# PaySage Questionnaire Copilot

A reference-grounded questionnaire answering tool built for the GTM Engineering Internship assignment.

## Overview

This application helps teams answer structured questionnaires such as security reviews, vendor assessments, compliance forms, and operational audits using approved internal reference documents.

The tool supports:

- User authentication
- Persistent storage with SQLite
- Questionnaire upload (CSV, XLSX, PDF)
- Reference document upload (TXT, PDF)
- Grounded answer generation with citations
- Human review and editing before export
- DOCX export preserving question order and structure

## Fictional Company Setup

**Industry:** Fintech (B2B Payments)

**Company:** PaySage

**Description:**  
PaySage is a fintech SaaS platform that helps small and medium businesses collect digital payments, manage invoices, and reconcile transactions automatically. The platform integrates with payment providers like Stripe and bank transfers while ensuring secure data handling, role-based access control, and audit logging.

## Problem

Teams often need to complete structured questionnaires using internal documentation. This process is repetitive, time-consuming, and error-prone. The goal of this project is to automate that workflow while keeping outputs grounded in source documents.

## How it works

1. User signs up and logs in
2. User uploads a questionnaire
3. User uploads reference documents
4. The system parses the questionnaire into individual questions
5. Relevant reference chunks are retrieved for each question
6. Answers are generated using only retrieved evidence
7. Each answer includes citations
8. Unsupported questions are marked as `Not found in references.`
9. The user reviews and edits answers
10. The final response is exported as a DOCX document

## Tech Stack

- Streamlit
- Python
- SQLite
- SQLAlchemy
- Pandas
- pdfplumber
- rank-bm25
- python-docx
- OpenAI API (optional)
- Retrieval-only fallback mode

## Grounding and citations

The app retrieves relevant chunks from uploaded reference documents and uses them as the only source of truth for answering questions.

If sufficient evidence is not found, the system returns:

`Not found in references.`

Each generated answer includes at least one citation pointing to the retrieved document chunk.

## Nice-to-have features implemented

- Coverage summary
- Evidence snippets
- Fallback mode without API key
- Run-based answer storage for future extension into version history

## Running locally

### 1. Clone the repo
```bash
git clone https://github.com/AKALYA200211/gtm-questionnaire-rag.git
cd GTM-questionnaire-rag

Live App:
https://gtm-questionnaire-rag.streamlit.app

GitHub Repository:
https://github.com/AKALYA200211/gtm-questionnaire-rag

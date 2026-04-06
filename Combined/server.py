from fastmcp import FastMCP
import gmail_service
from dotenv import load_dotenv
import asyncio
import tempfile
import os
from processor import (
    setup_qdrant as rag_setup_qdrant, load_model as rag_load_model,
    load_reranker, load_llm, create_prompt, create_rag_chain, ask_query
)
from embed import main_pipeline, load_file
from database import insert_to_qdrant
from processing import make_chunks, embed_chunks
from qdrant_client.models import Distance, VectorParams
from config import collection_name, config
import base64

load_dotenv()

_qdrant_client = rag_setup_qdrant()
_embed_model   = rag_load_model()
_reranker      = load_reranker()
_llm           = load_llm()
_prompt        = create_prompt()
_rag_chain     = create_rag_chain(_llm, _prompt)

mcp = FastMCP("Gmail")

@mcp.tool()
async def gmail_list_inbox(max_results: int=10, query: str="in:inbox"):
    """
    List recent emails from Gmail inbox. 
    Returns sender, subject, snippet, and ID.

    Args:
    max_results: Number of emails (default 10)
    query: Optional Gmail search e.g. "is:unread"
    """

    return await gmail_service.list_inbox(max_results=max_results, query=query)


@mcp.tool()
async def gmail_read_email(message_id: str):
    """
    Read the full body of an email by its message ID.

    Args: 
        message_id: Unique gmail message ID.
    """

    return await gmail_service.read_email(message_id)

@mcp.tool()
async def gmail_send_email(to: str, subject: str, body: str, cc: str|None=None):
    """
    Send a new email.

    Args:
    to: Recipient email address.
    subject: Email Subject line.
    body: Plain text body of email.
    cc: Option cc email address.
    """

    return await gmail_service.send_email(to=to, subject=subject, body=body, cc=cc)

@mcp.tool()
async def gmail_reply_email(message_id:str, body:str):
    """
    Reply to an existing email thread.

    Args:
        message_id: Message ID to reply to.
        body: Reply text.
    """

    return await gmail_service.reply_email(message_id, body=body)

@mcp.tool()
async def gmail_search_email(query: str, max_results: int = 10):
    """
    Search for emails in the user's Gmail inbox. 
    Use this tool when you want to find, check or look up specific emails based on criteria like sender, subject, or keywords like "quiz", "assignaments", "tickets".
    Args:
        query: Gmail search query (e.g., 'from:alice' or 'subject:invoice').
        max_results: Max results to return (default 10).
    """
    return await gmail_service.search_email(query=query, max_results=max_results)

@mcp.tool()
async def gmail_archive_email(message_id: str):
     """
     Archive an email (removes from inbox).

     Args:
        message_id: Gmail message ID.
     """

     return await gmail_service.archive_email(message_id)



@mcp.tool()
async def query_documents(question: str):
    """
    Answer questions about documents, PDFs, presentations, spreadsheets, or images
    that the user has shared. Use when the user asks 'what does the PDF say',
    'summarize the notes', 'what is on slide 3', or any content question.

    Args:
        question: The user's question about their documents.
    """
    answer = await asyncio.to_thread(
        ask_query, question, _embed_model, _qdrant_client, _reranker, _rag_chain
    )
    return {"answer": answer}


@mcp.tool()
async def ingest_file_to_knowledge_base(file_path: str):
    """
    Process and store a document into the knowledge base so it can be queried.
    Supports PDF, PPTX, PPT, DOCX, XLSX, PNG, JPG and other image formats.
    Use after saving a received file to disk.

    Args:
        file_path: Absolute path to the file on disk.
    """
    pages   = await asyncio.to_thread(load_file, file_path)
    chunks  = make_chunks(pages)
    vectors = await asyncio.to_thread(_embed_model.encode,
                                      [c["chunk_text"] for c in chunks],
                                      True)
    insert_to_qdrant(chunks, vectors, _qdrant_client)   # upsert, NOT create_collection
    return {"success": True, "chunks_stored": len(chunks), "file": os.path.basename(file_path)}

@mcp.tool()
async def gmail_sent_attachments_to_whatsapp(query: str):
    """
    Search Gmail for emails matching query, find PDF attachments,
    send them to WhatsApp directly, and store them in the knowledge base.
    Use when the user asks to "send", "share", "fetch" or "forward" 
    files, PDFs or attachments from Gmail.

    Args:
        query: Search terms e.g 'Unit 3 PPT', 'notes', 'assignment'
    """
    results    = await gmail_service.list_inbox(max_results=5, query=f"{query} has:attachment")
    emails     = results.get("emails", [])
    attachments = []

    for email in emails:
        atts = await gmail_service.get_email_attachments(email["id"])
        attachments.extend(atts)

    if not attachments:
        return {"attachments": [], "message": "No attachments found."}

    # ── Step 1: Return files to WhatsApp immediately ──────────
    result = {
        "attachments": [
            {
                "filename":  att["filename"],
                "mime_type": att["mime_type"],
                "data_b64":  base64.b64encode(att["bytes"]).decode(),
            }
            for att in attachments
        ]
    }

    # ── Step 2: Ingest into Qdrant in the background ──────────
    # This can take minutes for large PDFs — don't block the response on it
    async def _ingest_in_background():
        for att in attachments:
            try:
                ext = os.path.splitext(att["filename"])[1] or ".tmp"
                with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
                    f.write(att["bytes"])
                    temp_path = f.name
                pages   = await asyncio.to_thread(load_file, temp_path)
                chunks  = make_chunks(pages)
                if chunks:
                    vectors = await asyncio.to_thread(
                        _embed_model.encode, [c["chunk_text"] for c in chunks], True
                    )
                    insert_to_qdrant(chunks, vectors, _qdrant_client)
                os.unlink(temp_path)
                print(f"[server] Background ingestion done: {att['filename']}")
            except Exception as e:
                print(f"[server] Background ingestion failed for {att['filename']}: {e}")

    asyncio.create_task(_ingest_in_background())

    return result


existing = [c.name for c in _qdrant_client.get_collections().collections]
if collection_name not in existing:
    _qdrant_client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=config.vector_size, distance=Distance.COSINE)
    )
    print(f"[qdrant] Collection '{collection_name}' created")

if __name__ == "__main__":
    mcp.run(transport="streamable-http", port=8001, path="/mcp")
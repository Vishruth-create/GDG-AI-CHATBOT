from fastmcp import FastMCP
import gmail_service
from dotenv import load_dotenv

load_dotenv()

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

import base64  # add this at the top

@mcp.tool()
async def gmail_sent_attachments_to_whatsapp(query: str):
    """
    Search Gmail for emails matching query...
    Then find PDF Attachment and send it to whatsapp directly.
    When user asks "send", "share" or "forward" files, PDFs or attachments.

    Args:
        query: Search terms e.g 'notes'
    """
    results = await gmail_service.list_inbox(max_results=5, query=f"{query} has:attachment")
    emails = results.get("emails", [])
    attachments = []

    for email in emails:
        atts = await gmail_service.get_email_attachments(email["id"])
        attachments.extend(atts)

    # ← KEY FIX: convert raw bytes to base64 so MCP can serialize the response
    return {
        "attachments": [
            {
                "filename":  att["filename"],
                "mime_type": att["mime_type"],
                "data_b64":  base64.b64encode(att["bytes"]).decode(),
            }
            for att in attachments
        ]
    }

if __name__ == "__main__":
    mcp.run(transport="streamable-http", port=8001, path="/mcp")

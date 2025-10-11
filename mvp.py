import asyncio
import json
import logging
import os
import pickle
import sys
from typing import Dict, List
from datetime import datetime

# MCP imports
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

# Google API imports
from googleapiclient.discovery import build
import google_auth_oauthlib.flow
import google.auth.transport.requests

# Configure logging to stderr so it doesn't interfere with MCP protocol
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Google API scopes
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
    "https://www.googleapis.com/auth/drive.readonly"
]

def get_google_service(api_name: str, api_version: str):
    """Get authenticated Google service - THIS IS WHERE OAUTH HAPPENS"""
    creds = None
    
    # Load existing credentials
    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)
        logger.info("Loaded existing credentials")
    
    # Refresh or get new credentials
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing expired credentials")
            creds.refresh(google.auth.transport.requests.Request())
        else:
            if not os.path.exists("credentials.json"):
                raise FileNotFoundError(
                    "credentials.json not found. Please download it from Google Cloud Console.\n"
                    "1. Go to https://console.cloud.google.com/\n"
                    "2. Create/select a project\n"
                    "3. Enable Gmail API and Drive API\n" 
                    "4. Create OAuth 2.0 credentials\n"
                    "5. Download as credentials.json"
                )
            
            logger.info("STARTING OAUTH FLOW - Browser will open now!")
            flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            # THIS IS WHERE THE BROWSER OPENS FOR OAUTH
            creds = flow.run_local_server(port=0)
            logger.info("OAuth completed successfully!")
        
        # Save credentials for next run
        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)
        logger.info("Saved credentials for future use")
    else:
        logger.info("Using existing valid credentials")
    
    return build(api_name, api_version, credentials=creds)


async def check_gmail_privacy():
    """Check Gmail privacy - the actual implementation"""
    try:
        logger.info("Starting Gmail privacy check...")
        
        # THIS CALL WILL TRIGGER OAUTH IF NEEDED
        service = get_google_service("gmail", "v1")
        
        # Get recent messages (last 10)
        results = service.users().messages().list(
            userId="me", 
            maxResults=3,
            q="newer_than:7d"
        ).execute()
        
        messages = results.get("messages", [])
        logger.info(f"Found {len(messages)} recent messages")
        
        if not messages:
            return {
                "success": True,
                "total_messages_checked": 0,
                "findings": ["No recent messages found"],
                "risk_level": "low"
            }
        
        # risky_messages = []
        # privacy_risks = []
        # sensitive_keywords = [
        #     "password", "ssn", "social security", "confidential", 
        #     "bank account", "credit card", "passport", "driver license",
        #     "api key", "secret", "private key", "token"
        # ]
        
        # subscription_emails = []
        all_msg=[]
        for i, msg in enumerate(messages):
            try:
                logger.info(f"Processing message {i+1}/{len(messages)}")
                
                # Get message details
                message_data = service.users().messages().get(
                    userId="me", 
                    id=msg["id"],
                    format="full"
                ).execute()  
                all_msg.append(message_data) 
            except Exception as e:
                logger.warning(f"Error processing message {msg['id']}: {e}")
                continue
        return all_msg
            
        
    except Exception as e:
        logger.error(f"Gmail privacy check failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "scan_timestamp": datetime.now().isoformat()
        }

async def check_drive_privacy():
    try:
        service = get_google_service("drive", "v3")
        
        results = service.files().list(
            pageSize=3,
            fields="nextPageToken, files(id, name, mimeType, owners, shared, permissions, createdTime, modifiedTime, webViewLink)"
        ).execute()
        
        files = results.get("files", [])
        
        file_data_list = []
        
        for file in files:
            file_data = service.files().get(
                fileId=file["id"],
                fields="id, name, mimeType, owners, shared, permissions, createdTime, modifiedTime, webViewLink"
            ).execute()
            
            file_data_list.append(file_data)
        
        return {
            "success": True,
            "total_files_checked": len(files),
            "files": file_data_list
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

def test_auth_on_startup():
    """Optional: Test authentication on startup"""
    try:
        print("Testing Google API authentication...", file=sys.stderr)
        service = get_google_service("gmail", "v1")
        profile = service.users().getProfile(userId="me").execute()
        print(f"Successfully authenticated as: {profile.get('emailAddress')}", file=sys.stderr)
        return True
    except Exception as e:
        print(f"Authentication failed: {e}", file=sys.stderr)
        return False

# Create server instance
app = Server("privacy-checker")

@app.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """List available tools - Fixed for MCP 1.0+"""
    logger.info("Handling tools/list request")
    
    return [
        types.Tool(
            name="check_gmail_privacy",
            description="Analyze Gmail messages for privacy risks and sensitive content",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        types.Tool(
            name="check_drive_privacy", 
            description="Analyze Google Drive files for privacy risks and sensitive content",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        types.Tool(
            name="get_privacy_summary",
            description="Get a comprehensive privacy summary across Gmail and Google Drive",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    ]

@app.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Handle tool calls - Fixed for MCP 1.0+"""
    logger.info(f"Handling tool call: {name} with args: {arguments}")
    
    if name == "check_gmail_privacy":
        result = await check_gmail_privacy()
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "check_drive_privacy":
        result = await check_drive_privacy()
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "get_privacy_summary":
        """
        Return raw outputs for both Gmail and Drive. No AI here.
        The client (Streamlit) will analyze these with an LLM.
        """
        try:
            logger.info("Collecting raw Gmail + Drive data for summary...")
            gmail_raw = await check_gmail_privacy()   # your new version returns message metadata list
            drive_raw = await check_drive_privacy()   # if you also switch drive to raw, that's fine; otherwise keep as-is

            payload = {
                "success": True,
                "ts": datetime.now().isoformat(),
                "gmail_raw": gmail_raw,
                "drive_raw": drive_raw,
                "note": "Client is expected to run AI analysis over gmail_raw and drive_raw.",
            }
            return [types.TextContent(type="text", text=json.dumps(payload, indent=2))]
        except Exception as e:
            logger.error(f"get_privacy_summary failed: {e}")
            payload = {"success": False, "error": str(e), "ts": datetime.now().isoformat()}
            return [types.TextContent(type="text", text=json.dumps(payload, indent=2))]
                 
    else:
        raise ValueError(f"Unknown tool: {name}")

async def main():
    """Main entry point for the MCP server"""
    
    # Check command line arguments
    if len(sys.argv) > 1 and sys.argv[1] == "--test-auth":
        print("=== TESTING AUTHENTICATION ===", file=sys.stderr)
        if test_auth_on_startup():
            print("Authentication successful! You can now run the MCP server normally.", file=sys.stderr)
        else:
            print("Run 'python mvp.py --test-auth' first to set up OAuth", file=sys.stderr)
        return
    
    # All server status messages go to stderr to avoid interfering with MCP protocol
    print("Starting Privacy Checker MCP Server...", file=sys.stderr)
    print("OAuth will trigger when tools are called by an MCP client", file=sys.stderr)
    print("To test auth now, run: python mvp.py --test-auth", file=sys.stderr)
    
    try:
        # Run the server using stdio transport
        async with stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options()
            )
    except Exception as e:
        logger.error(f"Server failed to start: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())

#bridge.py

if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--analyze-url":
        url = sys.argv[2]
        # Here, you can pass the URL to OpenAI/Perplexity or your existing AI logic
        # For now, just send a dummy JSON result
        summary = {
            "url": url,
            "privacy_risk": "medium",
            "summary": f"The site {url} may collect cookies or tracking data. Review its privacy policy before logging in."
        }
        print(json.dumps(summary))
    else:
        import asyncio
        asyncio.run(main())
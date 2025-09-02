import asyncio
import json
import logging
import os
import pickle
import sys
from typing import Any, Dict, List
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

def _get_gmail_recommendations(risky_messages: List, subscriptions: List) -> List[str]:
    """Generate Gmail-specific recommendations"""
    recommendations = []
    
    if risky_messages:
        recommendations.append("Review and delete emails containing sensitive information")
        recommendations.append("Enable Gmail's confidential mode for sensitive emails")
    
    if len(subscriptions) > 10:
        recommendations.append("Unsubscribe from unnecessary mailing lists to reduce data exposure")
    
    recommendations.extend([
        "Enable two-factor authentication if not already active",
        "Review Gmail forwarding settings",
        "Check for suspicious login activity in account settings"
    ])
    
    return recommendations

def _get_drive_recommendations(risky_files: List, public_files: List, shared_files: List) -> List[str]:
    """Generate Drive-specific recommendations"""
    recommendations = []
    
    if public_files:
        recommendations.append("URGENT: Restrict access to public files, especially sensitive ones")
    
    if risky_files:
        recommendations.append("Rename or move files with sensitive information in filenames")
        recommendations.append("Consider encrypting sensitive documents")
    
    if shared_files:
        recommendations.append("Audit file sharing permissions and remove unnecessary access")
    
    recommendations.extend([
        "Enable link sharing notifications",
        "Set default sharing to 'Restricted' for new files",
        "Regular audit of file permissions"
    ])
    
    return recommendations

def _get_overall_recommendations(gmail_results: Dict, drive_results: Dict) -> List[str]:
    """Generate overall privacy recommendations"""
    recommendations = []
    
    # Prioritize critical issues
    if drive_results.get("public_files_found", 0) > 0:
        recommendations.append("CRITICAL: Secure public Drive files immediately")
    
    if gmail_results.get("risky_messages_found", 0) > 3:
        recommendations.append("HIGH: Clean up sensitive information in Gmail")
    
    recommendations.extend([
        "Set up regular privacy audits (monthly)",
        "Enable activity monitoring for both Gmail and Drive",
        "Consider using Google's Privacy Checkup tool",
        "Review and update privacy settings across all Google services"
    ])
    
    return recommendations

async def check_gmail_privacy():
    """Check Gmail privacy - the actual implementation"""
    try:
        logger.info("Starting Gmail privacy check...")
        
        # THIS CALL WILL TRIGGER OAUTH IF NEEDED
        service = get_google_service("gmail", "v1")
        
        # Get recent messages (last 10)
        results = service.users().messages().list(
            userId="me", 
            maxResults=10,
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
        
        risky_messages = []
        privacy_risks = []
        sensitive_keywords = [
            "password", "ssn", "social security", "confidential", 
            "bank account", "credit card", "passport", "driver license",
            "api key", "secret", "private key", "token"
        ]
        
        subscription_emails = []
        
        for i, msg in enumerate(messages):
            try:
                logger.info(f"Processing message {i+1}/{len(messages)}")
                
                # Get message details
                message_data = service.users().messages().get(
                    userId="me", 
                    id=msg["id"],
                    format="full"
                ).execute()
                
                # Extract headers
                headers = message_data.get("payload", {}).get("headers", [])
                subject = ""
                sender = ""
                
                for header in headers:
                    if header["name"] == "Subject":
                        subject = header["value"]
                    elif header["name"] == "From":
                        sender = header["value"]
                
                # Extract message content
                snippet = message_data.get("snippet", "")
                
                # Check for sensitive content
                content_to_check = (subject + " " + snippet).lower()
                found_keywords = [keyword for keyword in sensitive_keywords 
                                if keyword in content_to_check]
                
                if found_keywords:
                    risky_messages.append({
                        "message_id": msg["id"],
                        "subject": subject,
                        "sender": sender,
                        "found_keywords": found_keywords,
                        "snippet_preview": snippet[:100] + "..." if len(snippet) > 100 else snippet
                    })
                    logger.warning(f"RISK FOUND: {found_keywords}")
                
                # Check for subscription emails
                if any(word in content_to_check for word in ["unsubscribe", "newsletter", "marketing"]):
                    subscription_emails.append({
                        "sender": sender,
                        "subject": subject
                    })
                
                # Check for privacy policy updates
                if any(word in content_to_check for word in ["privacy policy", "terms of service", "updated"]):
                    privacy_risks.append({
                        "type": "policy_update",
                        "sender": sender,
                        "subject": subject,
                        "description": "Privacy policy or terms may have changed"
                    })
            
            except Exception as e:
                logger.warning(f"Error processing message {msg['id']}: {e}")
                continue
        
        # Calculate risk level
        risk_level = "low"
        if len(risky_messages) > 5:
            risk_level = "high"
        elif len(risky_messages) > 2:
            risk_level = "medium"
        
        result = {
            "success": True,
            "total_messages_checked": len(messages),
            "risky_messages_found": len(risky_messages),
            "findings": risky_messages if risky_messages else ["No risky Gmail content found"],
            "subscription_count": len(subscription_emails),
            "privacy_policy_updates": privacy_risks,
            "risk_level": risk_level,
            "recommendations": _get_gmail_recommendations(risky_messages, subscription_emails),
            "scan_timestamp": datetime.now().isoformat()
        }
        
        logger.info(f"Gmail scan complete - Risk level: {risk_level}")
        return result
        
    except Exception as e:
        logger.error(f"Gmail privacy check failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "scan_timestamp": datetime.now().isoformat()
        }

async def check_drive_privacy():
    """Check Drive privacy - the actual implementation"""
    try:
        logger.info("Starting Google Drive privacy check...")
        
        # THIS CALL WILL TRIGGER OAUTH IF NEEDED
        service = get_google_service("drive", "v3")
        
        # Get files with detailed metadata
        results = service.files().list(
            pageSize=50,
            fields="files(id,name,mimeType,shared,permissions,createdTime,modifiedTime,size,webViewLink)"
        ).execute()
        
        files = results.get("files", [])
        logger.info(f"Found {len(files)} files")
        
        if not files:
            return {
                "success": True,
                "total_files_checked": 0,
                "findings": ["No files found in Drive"],
                "risk_level": "low"
            }
        
        risky_files = []
        public_files = []
        shared_files = []
        sensitive_keywords = [
            "password", "confidential", "ssn", "social security",
            "resume", "cv", "passport", "license", "bank", "financial",
            "tax", "personal", "private", "secret"
        ]
        
        for i, file in enumerate(files):
            file_name = file.get("name", "").lower()
            file_info = {
                "id": file.get("id"),
                "name": file.get("name"),
                "type": file.get("mimeType"),
                "created": file.get("createdTime"),
                "modified": file.get("modifiedTime"),
                "size": file.get("size"),
                "link": file.get("webViewLink")
            }
            
            logger.info(f"Processing file {i+1}/{len(files)}: {file.get('name', 'Unknown')}")
            
            # Check for sensitive file names
            found_keywords = [keyword for keyword in sensitive_keywords 
                            if keyword in file_name]
            
            if found_keywords:
                risky_files.append({
                    **file_info,
                    "risk_reason": f"Filename contains: {', '.join(found_keywords)}"
                })
                logger.warning(f"RISKY FILE: {found_keywords}")
            
            # Check file permissions for privacy risks
            try:
                permissions = service.permissions().list(fileId=file["id"]).execute()
                permissions_list = permissions.get("permissions", [])
                
                # Check if file is public
                is_public = any(perm.get("type") == "anyone" for perm in permissions_list)
                if is_public:
                    public_files.append({
                        **file_info,
                        "risk_reason": "File is publicly accessible"
                    })
                    logger.error(f"PUBLIC FILE: {file.get('name')}")
                
                # Check if file is shared with many people
                external_shares = [perm for perm in permissions_list 
                                 if perm.get("type") == "user" and perm.get("role") in ["reader", "writer", "commenter"]]
                
                if len(external_shares) > 5:
                    shared_files.append({
                        **file_info,
                        "shared_with_count": len(external_shares),
                        "risk_reason": f"File shared with {len(external_shares)} people"
                    })
                    logger.warning(f"OVERSHARED: {len(external_shares)} people")
            
            except Exception as e:
                logger.warning(f"Could not check permissions for file {file['id']}: {e}")
        
        # Calculate overall risk level
        high_risk_count = len([f for f in risky_files if any(keyword in f["name"].lower() 
                             for keyword in ["password", "ssn", "confidential", "bank"])])
        public_sensitive_count = len([f for f in public_files if any(keyword in f["name"].lower() 
                                    for keyword in sensitive_keywords)])
        
        if public_sensitive_count > 0 or high_risk_count > 3:
            risk_level = "critical"
        elif len(public_files) > 0 or high_risk_count > 1:
            risk_level = "high"
        elif len(risky_files) > 5 or len(shared_files) > 10:
            risk_level = "medium"
        else:
            risk_level = "low"
        
        result = {
            "success": True,
            "total_files_checked": len(files),
            "risky_files_found": len(risky_files),
            "public_files_found": len(public_files),
            "overshared_files_found": len(shared_files),
            "findings": {
                "sensitive_filenames": risky_files if risky_files else ["No risky file names found"],
                "public_files": public_files if public_files else ["No public files found"],
                "overshared_files": shared_files if shared_files else ["No overshared files found"]
            },
            "risk_level": risk_level,
            "recommendations": _get_drive_recommendations(risky_files, public_files, shared_files),
            "scan_timestamp": datetime.now().isoformat()
        }
        
        logger.info(f"Drive scan complete - Risk level: {risk_level}")
        return result
        
    except Exception as e:
        logger.error(f"Drive privacy check failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "scan_timestamp": datetime.now().isoformat()
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
        try:
            logger.info("Generating comprehensive privacy summary...")
            
            # Get the results from both checks
            gmail_results = await check_gmail_privacy()
            drive_results = await check_drive_privacy()
            
            # Calculate overall risk score
            gmail_risk = gmail_results.get("risk_level", "low")
            drive_risk = drive_results.get("risk_level", "low")
            
            risk_scores = {"low": 1, "medium": 2, "high": 3, "critical": 4}
            overall_risk_score = max(risk_scores.get(gmail_risk, 1), risk_scores.get(drive_risk, 1))
            overall_risk_level = [k for k, v in risk_scores.items() if v == overall_risk_score][0]
            
            # Generate summary insights
            total_issues = 0
            critical_issues = []
            
            if gmail_results.get("success"):
                total_issues += gmail_results.get("risky_messages_found", 0)
                if gmail_results.get("risk_level") in ["high", "critical"]:
                    critical_issues.append("Gmail contains sensitive information in recent messages")
            
            if drive_results.get("success"):
                total_issues += drive_results.get("risky_files_found", 0)
                total_issues += drive_results.get("public_files_found", 0)
                if drive_results.get("public_files_found", 0) > 0:
                    critical_issues.append("Google Drive has publicly accessible files")
            
            result = {
                "success": True,
                "overall_risk_level": overall_risk_level,
                "total_privacy_issues": total_issues,
                "critical_issues": critical_issues,
                "gmail_analysis": gmail_results,
                "drive_analysis": drive_results,
                "top_recommendations": _get_overall_recommendations(gmail_results, drive_results),
                "summary_timestamp": datetime.now().isoformat()
            }
            
            logger.info(f"Summary complete - Overall risk: {overall_risk_level}")
            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
            
        except Exception as e:
            logger.error(f"Privacy summary generation failed: {e}")
            result = {
                "success": False,
                "error": str(e)
            }
            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
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

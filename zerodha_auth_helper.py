"""
Quick helper to capture Zerodha callback and generate session
Run this, then use ngrok to expose it
"""

from flask import Flask, request, jsonify
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.zerodha_service import zerodha_service

app = Flask(__name__)

@app.route('/auth/callback')
def callback():
    """Handle Zerodha callback"""
    request_token = request.args.get('request_token')
    status = request.args.get('status')
    
    if not request_token:
        return """
        <html>
        <body>
            <h1>❌ Error: No request token received</h1>
            <p>The callback didn't include a request_token.</p>
        </body>
        </html>
        """, 400
    
    if status != 'success':
        return f"""
        <html>
        <body>
            <h1>❌ Authorization Failed</h1>
            <p>Status: {status}</p>
            <p>You may have denied the authorization.</p>
        </body>
        </html>
        """, 400
    
    try:
        # Generate session
        session_data = zerodha_service.generate_session(request_token)
        access_token = session_data['access_token']
        user_name = session_data.get('user_name', 'Unknown')
        email = session_data.get('email', 'Unknown')
        
        return f"""
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    max-width: 800px;
                    margin: 50px auto;
                    padding: 20px;
                    background: #f5f5f5;
                }}
                .success {{
                    background: #d4edda;
                    border: 1px solid #c3e6cb;
                    padding: 20px;
                    border-radius: 5px;
                    margin: 20px 0;
                }}
                .token {{
                    background: #fff;
                    padding: 15px;
                    border-radius: 5px;
                    font-family: monospace;
                    word-break: break-all;
                    margin: 10px 0;
                }}
                h1 {{ color: #155724; }}
                code {{
                    background: #f8f9fa;
                    padding: 2px 6px;
                    border-radius: 3px;
                }}
            </style>
        </head>
        <body>
            <div class="success">
                <h1>✅ Zerodha Authentication Successful!</h1>
                <p><strong>User:</strong> {user_name}</p>
                <p><strong>Email:</strong> {email}</p>
                <p><strong>Status:</strong> Connected to Zerodha</p>
            </div>
            
            <h2>📋 Your Access Token:</h2>
            <div class="token">
                {access_token}
            </div>
            
            <h2>🎯 Next Steps:</h2>
            <ol>
                <li>Copy the access token above</li>
                <li>Store it securely</li>
                <li>Use it in your Python code</li>
            </ol>
            
            <h3>Sample Code:</h3>
            <pre style="background: #f8f9fa; padding: 15px; border-radius: 5px; overflow-x: auto;">
from app.services.zerodha_service import zerodha_service

# Set the access token
zerodha_service.set_access_token('{access_token}')

# Now you can use Zerodha APIs!
from app.services.zerodha_service import get_live_price
price = get_live_price("RELIANCE", "NSE")
print(f"RELIANCE: ₹{{price}}")
            </pre>
            
            <p style="color: #856404; background: #fff3cd; padding: 10px; border-radius: 5px;">
                <strong>⚠️ Note:</strong> This token expires at 6:00 AM tomorrow. 
                You'll need to re-authenticate daily.
            </p>
            
            <h2>🚀 You're now connected to Zerodha!</h2>
            <p>You can close this window and start trading with ARISE.</p>
        </body>
        </html>
        """
        
    except Exception as e:
        return f"""
        <html>
        <body>
            <h1>❌ Session Generation Failed</h1>
            <p>Error: {str(e)}</p>
            <p>Request Token: {request_token}</p>
        </body>
        </html>
        """, 500

@app.route('/')
def home():
    """Home page with login button"""
    login_url = zerodha_service.get_login_url()
    
    return f"""
    <html>
    <head>
        <style>
            body {{
                font-family: Arial, sans-serif;
                max-width: 600px;
                margin: 50px auto;
                padding: 20px;
                text-align: center;
            }}
            .btn {{
                display: inline-block;
                background: #2196F3;
                color: white;
                padding: 15px 30px;
                text-decoration: none;
                border-radius: 5px;
                font-size: 18px;
                margin: 20px 0;
            }}
            .btn:hover {{
                background: #0b7dda;
            }}
        </style>
    </head>
    <body>
        <h1>🚀 ARISE - Zerodha Authentication</h1>
        <p>Click the button below to connect your Zerodha account with ARISE</p>
        
        <a href="{login_url}" class="btn">
            🔐 Login with Zerodha
        </a>
        
        <p style="color: #666; margin-top: 40px; font-size: 14px;">
            You'll be redirected to Zerodha to authorize ARISE.<br>
            After authorization, you'll return here with your access token.
        </p>
    </body>
    </html>
    """

if __name__ == '__main__':
    print("\n" + "="*70)
    print("ZERODHA AUTHENTICATION HELPER")
    print("="*70)
    print("\n🚀 Starting authentication server...")
    print("\n📋 Instructions:")
    print("1. This server will run on http://localhost:5000")
    print("2. Open another terminal and run: ngrok http 5000")
    print("3. Copy the HTTPS URL from ngrok (e.g., https://abc123.ngrok.io)")
    print("4. Update redirect URL in Zerodha developer console to: https://abc123.ngrok.io/auth/callback")
    print("5. Visit http://localhost:5000 and click 'Login with Zerodha'")
    print("\nOR just visit the login URL directly and copy the token from the 404 page URL!")
    print("\n" + "="*70 + "\n")
    
    # Run Flask app
    app.run(host='0.0.0.0', port=5000, debug=True)

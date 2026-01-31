"""
Demo Authentication System - V7.0
Time-limited access for client demonstrations
"""

import streamlit as st
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict
import json
from pathlib import Path
import config


# Demo tokens storage file
DEMO_TOKENS_FILE = Path("data/demo_tokens.json")


def generate_demo_token(expiry_hours: int = 24) -> Dict:
    """
    Generate a new demo access token with expiry time.
    
    Args:
        expiry_hours: Number of hours until token expires
        
    Returns:
        Dict with token, expiry time, and access URL
    """
    token = secrets.token_urlsafe(32)
    expiry_time = datetime.now() + timedelta(hours=expiry_hours)
    
    token_data = {
        'token': token,
        'created_at': datetime.now().isoformat(),
        'expires_at': expiry_time.isoformat(),
        'expiry_hours': expiry_hours
    }
    
    # Save token to file
    _save_token(token_data)
    
    return token_data


def validate_demo_token(token: str) -> bool:
    """
    Validate if a demo token is valid and not expired.
    
    Args:
        token: The demo access token
        
    Returns:
        True if valid, False otherwise
    """
    tokens = _load_tokens()
    
    for saved_token in tokens:
        if saved_token.get('token') == token:
            expiry_time = datetime.fromisoformat(saved_token['expires_at'])
            if datetime.now() < expiry_time:
                return True
            else:
                # Token expired, remove it
                tokens.remove(saved_token)
                _save_tokens(tokens)
                return False
    
    return False


def check_demo_auth() -> bool:
    """
    Check if user is authenticated for demo access.
    Uses session state to track authentication.
    
    Returns:
        True if authenticated, False otherwise
    """
    if not config.DEMO_MODE:
        return True  # Not in demo mode, allow access
    
    # Check session state for authentication
    if 'demo_authenticated' in st.session_state and st.session_state.demo_authenticated:
        # Check if session hasn't expired
        if 'demo_expiry' in st.session_state:
            if datetime.now() < st.session_state.demo_expiry:
                return True
            else:
                st.session_state.demo_authenticated = False
                st.warning("⏰ Demo session has expired. Please log in again.")
                return False
        return True
    
    return False


def render_demo_login() -> bool:
    """
    Render demo login page and handle authentication.
    
    Returns:
        True if login successful, False otherwise
    """
    st.markdown("""
    <style>
    .demo-login-container {
        max-width: 400px;
        margin: 100px auto;
        padding: 40px;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 20px;
        box-shadow: 0 20px 60px rgba(0,0,0,0.3);
    }
    .demo-title {
        text-align: center;
        color: white;
        font-size: 28px;
        margin-bottom: 30px;
    }
    .demo-subtitle {
        text-align: center;
        color: rgba(255,255,255,0.8);
        font-size: 14px;
        margin-bottom: 20px;
    }
    </style>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("## 🤖 AI Exception Modeler")
        st.markdown("### Demo Access Portal")
        st.markdown("---")
        
        with st.form("demo_login_form"):
            username = st.text_input("Username", placeholder="Enter demo username")
            password = st.text_input("Password", type="password", placeholder="Enter demo password")
            
            submit = st.form_submit_button("🔓 Access Demo", use_container_width=True)
            
            if submit:
                if (username == config.DEMO_CONFIG['demo_username'] and 
                    password == config.DEMO_CONFIG['demo_password']):
                    
                    st.session_state.demo_authenticated = True
                    st.session_state.demo_expiry = datetime.now() + timedelta(
                        hours=config.DEMO_CONFIG['expiry_hours']
                    )
                    st.success("✅ Login successful! Redirecting...")
                    st.rerun()
                    return True
                else:
                    st.error("❌ Invalid credentials. Please try again.")
                    return False
        
        st.markdown("---")
        st.markdown(
            f"*Demo access expires in {config.DEMO_CONFIG['expiry_hours']} hours*",
            help="Contact your sales representative for extended access"
        )
    
    return False


def get_demo_expiry_info() -> Optional[Dict]:
    """
    Get current demo session expiry information.
    
    Returns:
        Dict with expiry info if in demo mode and authenticated, None otherwise
    """
    if not config.DEMO_MODE:
        return None
    
    if 'demo_expiry' in st.session_state:
        expiry = st.session_state.demo_expiry
        remaining = expiry - datetime.now()
        
        return {
            'expires_at': expiry.isoformat(),
            'remaining_hours': max(0, remaining.total_seconds() / 3600),
            'remaining_minutes': max(0, remaining.total_seconds() / 60)
        }
    
    return None


def render_demo_banner():
    """
    Render demo mode banner with expiry countdown.
    """
    if not config.DEMO_MODE:
        return
    
    expiry_info = get_demo_expiry_info()
    if expiry_info:
        remaining_hours = expiry_info['remaining_hours']
        
        if remaining_hours < 1:
            color = "#ff6b6b"  # Red for less than 1 hour
            remaining_text = f"{int(expiry_info['remaining_minutes'])} minutes"
        elif remaining_hours < 6:
            color = "#ffa726"  # Orange for less than 6 hours
            remaining_text = f"{remaining_hours:.1f} hours"
        else:
            color = "#66bb6a"  # Green otherwise
            remaining_text = f"{remaining_hours:.1f} hours"
        
        st.markdown(f"""
        <div style="background: {color}; color: white; padding: 8px 16px; 
                    border-radius: 8px; text-align: center; margin-bottom: 16px;">
            🔐 <strong>DEMO MODE</strong> - Session expires in {remaining_text}
        </div>
        """, unsafe_allow_html=True)


def _load_tokens() -> list:
    """Load saved demo tokens from file."""
    if DEMO_TOKENS_FILE.exists():
        try:
            with open(DEMO_TOKENS_FILE, 'r') as f:
                return json.load(f)
        except:
            return []
    return []


def _save_tokens(tokens: list):
    """Save demo tokens to file."""
    DEMO_TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DEMO_TOKENS_FILE, 'w') as f:
        json.dump(tokens, f, indent=2)


def _save_token(token_data: Dict):
    """Add new token to saved tokens."""
    tokens = _load_tokens()
    tokens.append(token_data)
    _save_tokens(tokens)


if __name__ == "__main__":
    # CLI tool to generate demo tokens
    print("🔐 AI Exception Modeler - Demo Token Generator")
    print("-" * 50)
    
    token_data = generate_demo_token(24)
    print(f"\n✅ Demo token generated!")
    print(f"   Token: {token_data['token']}")
    print(f"   Expires: {token_data['expires_at']}")
    print(f"\n📋 Share this with your client:")
    print(f"   Username: {config.DEMO_CONFIG['demo_username']}")
    print(f"   Password: {config.DEMO_CONFIG['demo_password']}")

"""
Google OAuth Authentication Service
"""
from google.oauth2 import id_token
from google.auth.transport import requests
from fastapi import HTTPException, status
from typing import Dict, Optional
import os
from dotenv import load_dotenv

load_dotenv()


class GoogleAuthService:
    """Service for handling Google OAuth authentication"""
    
    def __init__(self):
        self.client_id = os.getenv('GOOGLE_CLIENT_ID')
        self.client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
        
        if not self.client_id:
            raise ValueError("GOOGLE_CLIENT_ID environment variable is not set")
    
    def verify_google_token(self, token: str) -> Dict[str, any]:
        """
        Verify Google ID token and extract user information
        
        Args:
            token: Google ID token from frontend
            
        Returns:
            Dictionary containing user information from Google
            
        Raises:
            HTTPException: If token verification fails
        """
        try:
            # Verify the token with Google
            idinfo = id_token.verify_oauth2_token(
                token, 
                requests.Request(), 
                self.client_id
            )
            
            # Verify the issuer
            if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
                raise ValueError('Wrong issuer.')
            
            # Extract user information
            user_data = {
                'google_id': idinfo['sub'],
                'email': idinfo.get('email', ''),
                'email_verified': idinfo.get('email_verified', False),
                'name': idinfo.get('name', ''),
                'given_name': idinfo.get('given_name', ''),
                'family_name': idinfo.get('family_name', ''),
                'picture': idinfo.get('picture', ''),
                'locale': idinfo.get('locale', '')
            }
            
            return user_data
            
        except ValueError as e:
            # Invalid token
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid Google token: {str(e)}"
            )
        except Exception as e:
            # Other errors
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to verify Google token: {str(e)}"
            )
    
    def get_user_info_from_token(self, token: str) -> Dict[str, any]:
        """
        Get user information from Google ID token
        This is an alias for verify_google_token for consistency
        
        Args:
            token: Google ID token
            
        Returns:
            Dictionary containing user information
        """
        return self.verify_google_token(token)


# Singleton instance
_google_auth_service: Optional[GoogleAuthService] = None


def get_google_auth_service() -> GoogleAuthService:
    """
    Get or create GoogleAuthService instance (dependency injection)
    
    Returns:
        GoogleAuthService instance
    """
    global _google_auth_service
    
    if _google_auth_service is None:
        _google_auth_service = GoogleAuthService()
    
    return _google_auth_service

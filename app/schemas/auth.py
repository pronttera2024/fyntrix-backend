"""
Authentication schemas for AWS Cognito
"""
from pydantic import BaseModel, EmailStr, Field, validator
import re


class SignupRequest(BaseModel):
    """User signup request"""
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=8, description="Password (min 8 characters)")
    name: str = Field(..., min_length=1, max_length=100, description="Full name")
    
    @validator('password')
    def validate_password(cls, v):
        """Validate password meets AWS Cognito requirements"""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'[0-9]', v):
            raise ValueError('Password must contain at least one number')
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError('Password must contain at least one special character')
        return v
    
    @validator('name')
    def validate_name(cls, v):
        """Validate name is not empty and contains valid characters"""
        if not v.strip():
            raise ValueError('Name cannot be empty')
        if not re.match(r'^[a-zA-Z\s\-\.]+$', v):
            raise ValueError('Name can only contain letters, spaces, hyphens, and periods')
        return v.strip()


class LoginRequest(BaseModel):
    """User login request"""
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., description="User password")


class AuthResponse(BaseModel):
    """Authentication response"""
    access_token: str = Field(..., description="JWT access token")
    id_token: str = Field(..., description="JWT ID token")
    refresh_token: str = Field(..., description="Refresh token")
    expires_in: int = Field(..., description="Token expiration time in seconds")
    token_type: str = Field(default="Bearer", description="Token type")


class UserResponse(BaseModel):
    """User information response"""
    user_id: str = Field(..., description="User unique identifier (sub)")
    email: str = Field(..., description="User email address")
    name: str = Field(..., description="User full name")
    email_verified: bool = Field(..., description="Email verification status")


class SignupResponse(BaseModel):
    """Signup response"""
    message: str = Field(..., description="Success message")
    user: UserResponse = Field(..., description="Created user information")
    auth: AuthResponse = Field(..., description="Authentication tokens")


class RefreshTokenRequest(BaseModel):
    """Refresh token request"""
    refresh_token: str = Field(..., description="Refresh token")


class ErrorResponse(BaseModel):
    """Error response"""
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")

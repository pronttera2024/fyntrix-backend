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


class PhoneSignupRequest(BaseModel):
    """User signup request with phone number"""
    phone_number: str = Field(..., description="User phone number in E.164 format (e.g., +919876543210)")
    name: str = Field(..., min_length=1, max_length=100, description="Full name")
    
    @validator('phone_number')
    def validate_phone_number(cls, v):
        """Validate phone number is in E.164 format"""
        if not re.match(r'^\+[1-9]\d{1,14}$', v):
            raise ValueError('Phone number must be in E.164 format (e.g., +919876543210)')
        return v
    
    @validator('name')
    def validate_name(cls, v):
        """Validate name is not empty and contains valid characters"""
        if not v.strip():
            raise ValueError('Name cannot be empty')
        if not re.match(r'^[a-zA-Z\s\-\.]+$', v):
            raise ValueError('Name can only contain letters, spaces, hyphens, and periods')
        return v.strip()


class PhoneVerifyOTPRequest(BaseModel):
    """Verify OTP for phone signup"""
    phone_number: str = Field(..., description="User phone number in E.164 format")
    otp_code: str = Field(..., min_length=6, max_length=6, description="6-digit OTP code")


class PhoneLoginRequest(BaseModel):
    """User login request with phone number"""
    phone_number: str = Field(..., description="User phone number in E.164 format")
    
    @validator('phone_number')
    def validate_phone_number(cls, v):
        """Validate phone number is in E.164 format"""
        if not re.match(r'^\+[1-9]\d{1,14}$', v):
            raise ValueError('Phone number must be in E.164 format (e.g., +919876543210)')
        return v


class PhoneLoginVerifyRequest(BaseModel):
    """Verify OTP for phone login"""
    phone_number: str = Field(..., description="User phone number in E.164 format")
    session: str = Field(..., description="Session token from login initiation")
    otp_code: str = Field(..., min_length=6, max_length=6, description="6-digit OTP code")


class PhoneResendOTPRequest(BaseModel):
    """Resend OTP request for phone signup or login"""
    phone_number: str = Field(..., description="User phone number in E.164 format")
    
    @validator('phone_number')
    def validate_phone_number(cls, v):
        """Validate phone number is in E.164 format"""
        if not re.match(r'^\+[1-9]\d{1,14}$', v):
            raise ValueError('Phone number must be in E.164 format (e.g., +919876543210)')
        return v


class PhoneUserResponse(BaseModel):
    """User information response for phone auth"""
    user_id: str = Field(..., description="User unique identifier (sub)")
    phone_number: str = Field(..., description="User phone number")
    name: str = Field(..., description="User full name")
    phone_number_verified: bool = Field(..., description="Phone verification status")


class GoogleAuthRequest(BaseModel):
    """Google OAuth authentication request"""
    token: str = Field(..., description="Google ID token from frontend")
    
    
class GoogleAuthResponse(BaseModel):
    """Google OAuth authentication response"""
    access_token: str = Field(..., description="JWT access token")
    id_token: str = Field(..., description="JWT ID token")
    refresh_token: str = Field(..., description="Refresh token")
    expires_in: int = Field(..., description="Token expiration time in seconds")
    token_type: str = Field(default="Bearer", description="Token type")
    user: UserResponse = Field(..., description="User information")


class DeleteUserRequest(BaseModel):
    """Delete user request"""
    identifier: str = Field(..., description="Email address or phone number (E.164 format) of user to delete")
    
    @validator('identifier')
    def validate_identifier(cls, v):
        """Validate identifier is either email or phone number"""
        if not v.strip():
            raise ValueError('Identifier cannot be empty')
        return v.strip()

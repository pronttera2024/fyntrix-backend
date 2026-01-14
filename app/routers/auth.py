"""
Authentication router for AWS Cognito
"""
from fastapi import APIRouter, HTTPException, status, Depends, Header, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
from sqlalchemy.orm import Session
from ..schemas.auth import (
    SignupRequest,
    LoginRequest,
    SignupResponse,
    AuthResponse,
    UserResponse,
    RefreshTokenRequest,
    ErrorResponse,
    PhoneSignupRequest,
    PhoneVerifyOTPRequest,
    PhoneLoginRequest,
    PhoneLoginVerifyRequest,
    PhoneUserResponse
)
from ..services.cognito_auth import get_cognito_service, CognitoAuthService
from ..services.user_service import UserService
from ..config.database import get_db

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Security scheme for JWT Bearer tokens
security = HTTPBearer()


def get_request_metadata(request: Request) -> dict:
    """
    Extract request metadata for audit logging
    
    Args:
        request: FastAPI Request object
        
    Returns:
        Dictionary with ip_address, device, user_agent
    """
    # Get client IP (handle proxy headers)
    ip_address = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    if not ip_address:
        ip_address = request.headers.get("X-Real-IP", "")
    if not ip_address and request.client:
        ip_address = request.client.host
    
    # Get user agent and device info
    user_agent = request.headers.get("User-Agent", "Unknown")
    
    # Simple device detection from user agent
    device = "Unknown"
    if "Mobile" in user_agent or "Android" in user_agent or "iPhone" in user_agent:
        device = "Mobile"
    elif "Tablet" in user_agent or "iPad" in user_agent:
        device = "Tablet"
    elif "Mozilla" in user_agent or "Chrome" in user_agent:
        device = "Desktop"
    
    return {
        "ip_address": ip_address,
        "device": device,
        "user_agent": user_agent,
        "location": None  # Can be enhanced with GeoIP lookup
    }


@router.post(
    "/signup",
    response_model=SignupResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "User successfully created and authenticated"},
        400: {"model": ErrorResponse, "description": "Invalid input data"},
        409: {"model": ErrorResponse, "description": "User already exists"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="Sign up a new user",
    description="""
    Create a new user account with AWS Cognito.
    
    **Requirements:**
    - Email must be valid
    - Password must be at least 8 characters with uppercase, lowercase, number, and special character
    - Name must contain only letters, spaces, hyphens, and periods
    
    **Note:** Email is automatically verified upon signup.
    """
)
async def signup(
    request: SignupRequest,
    http_request: Request,
    cognito: CognitoAuthService = Depends(get_cognito_service),
    db: Session = Depends(get_db)
):
    """
    Sign up a new user
    
    - **email**: Valid email address (will be used as username)
    - **password**: Strong password meeting complexity requirements
    - **name**: User's full name
    
    Returns user information and authentication tokens.
    """
    result = cognito.signup(
        email=request.email,
        password=request.password,
        name=request.name
    )
    
    # Create user in database
    request_metadata = get_request_metadata(http_request)
    user = UserService.create_user_from_cognito(
        db=db,
        cognito_data={
            "sub": result['user_sub'],
            "email": result['email'],
            "name": result['name'],
            "email_verified": result['email_verified'],
            "username": result['email']
        },
        request_metadata=request_metadata
    )
    
    return SignupResponse(
        message="User created successfully",
        user=UserResponse(
            user_id=result['user_sub'],
            email=result['email'],
            name=result['name'],
            email_verified=result['email_verified']
        ),
        auth=AuthResponse(
            access_token=result['auth']['access_token'],
            id_token=result['auth']['id_token'],
            refresh_token=result['auth']['refresh_token'],
            expires_in=result['auth']['expires_in'],
            token_type=result['auth']['token_type']
        )
    )


@router.post(
    "/login",
    response_model=AuthResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Successfully authenticated"},
        401: {"model": ErrorResponse, "description": "Invalid credentials"},
        403: {"model": ErrorResponse, "description": "User not confirmed"},
        404: {"model": ErrorResponse, "description": "User not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="Log in a user",
    description="""
    Authenticate a user with email and password.
    
    Returns JWT tokens (access_token, id_token, refresh_token) that can be used for API authorization.
    """
)
async def login(
    request: LoginRequest,
    http_request: Request,
    cognito: CognitoAuthService = Depends(get_cognito_service),
    db: Session = Depends(get_db)
):
    """
    Log in a user
    
    - **email**: User's email address
    - **password**: User's password
    
    Returns authentication tokens.
    """
    result = cognito.login(
        email=request.email,
        password=request.password
    )
    
    # Get user info from Cognito and update database
    user_info = cognito.get_user_info(access_token=result['access_token'])
    request_metadata = get_request_metadata(http_request)
    user = UserService.create_user_from_cognito(
        db=db,
        cognito_data=user_info,
        request_metadata=request_metadata
    )
    
    return AuthResponse(
        access_token=result['access_token'],
        id_token=result['id_token'],
        refresh_token=result['refresh_token'],
        expires_in=result['expires_in'],
        token_type=result['token_type']
    )


@router.post(
    "/refresh",
    response_model=AuthResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Token successfully refreshed"},
        401: {"model": ErrorResponse, "description": "Invalid or expired refresh token"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="Refresh access token",
    description="""
    Refresh the access token using a refresh token.
    
    The refresh token is obtained during login/signup and can be used to get new access tokens
    without requiring the user to log in again.
    """
)
async def refresh_token(
    request: RefreshTokenRequest,
    email: str = Header(..., description="User email address"),
    cognito: CognitoAuthService = Depends(get_cognito_service)
):
    """
    Refresh access token
    
    - **refresh_token**: Valid refresh token from login/signup
    - **email**: User's email address (passed in header)
    
    Returns new access and ID tokens.
    """
    result = cognito.refresh_token(
        refresh_token=request.refresh_token,
        email=email
    )
    
    return AuthResponse(
        access_token=result['access_token'],
        id_token=result['id_token'],
        refresh_token=request.refresh_token,  # Refresh token doesn't change
        expires_in=result['expires_in'],
        token_type=result['token_type']
    )


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "User information retrieved successfully"},
        401: {"model": ErrorResponse, "description": "Invalid or expired token"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="Get current user information",
    description="""
    Get information about the currently authenticated user.
    
    Requires a valid access token (use Authorize button in Swagger UI).
    """,
    dependencies=[Depends(security)]  # Add security dependency
)
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    cognito: CognitoAuthService = Depends(get_cognito_service)
):
    """
    Get current user information
    
    Returns user profile information.
    """
    access_token = credentials.credentials
    
    result = cognito.get_user_info(access_token=access_token)
    
    return UserResponse(
        user_id=result['user_id'],
        email=result['email'],
        name=result['name'],
        email_verified=result['email_verified']
    )


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Health check",
    description="Check if the authentication service is running and configured properly"
)
async def health_check(
    cognito: CognitoAuthService = Depends(get_cognito_service)
):
    """
    Health check endpoint
    
    Returns service status and configuration info (without sensitive data).
    """
    return {
        "status": "healthy",
        "service": "AWS Cognito Authentication",
        "region": cognito.region,
        "user_pool_id": cognito.user_pool_id,
        "client_id": cognito.client_id
    }


@router.post(
    "/phone/signup",
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "OTP sent to phone number"},
        400: {"model": ErrorResponse, "description": "Invalid input data"},
        409: {"model": ErrorResponse, "description": "User already exists"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="Sign up with phone number",
    description="""
    Create a new user account with phone number.
    
    **Requirements:**
    - Phone number must be in E.164 format (e.g., +919876543210)
    - Name is required
    
    **Flow:**
    1. Call this endpoint with phone_number and name
    2. OTP will be sent to the phone via SMS
    3. Call /phone/verify-signup with the OTP to complete registration
    """
)
async def phone_signup(
    request: PhoneSignupRequest,
    http_request: Request,
    cognito: CognitoAuthService = Depends(get_cognito_service),
    db: Session = Depends(get_db)
):
    """
    Sign up a new user with phone number
    
    - **phone_number**: Phone number in E.164 format (e.g., +919876543210)
    - **name**: User's full name
    
    Returns confirmation that OTP was sent.
    """
    result = cognito.phone_signup(
        phone_number=request.phone_number,
        name=request.name
    )
    
    # Create user in database (will be updated on verification)
    request_metadata = get_request_metadata(http_request)
    user = UserService.create_user_from_cognito(
        db=db,
        cognito_data={
            "sub": result['user_sub'],
            "phone_number": result['phone_number'],
            "name": result['name'],
            "phone_number_verified": False,
            "username": result['phone_number']
        },
        request_metadata=request_metadata
    )
    
    return {
        "message": result['message'],
        "phone_number": result['phone_number'],
        "user_sub": result['user_sub']
    }


@router.post(
    "/phone/verify-signup",
    response_model=AuthResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Phone number verified and authenticated successfully"},
        400: {"model": ErrorResponse, "description": "Invalid or expired OTP"},
        401: {"model": ErrorResponse, "description": "User already confirmed"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="Verify phone number with OTP and get auth tokens",
    description="""
    Verify phone number with OTP code received via SMS.
    
    After successful verification, automatically logs in the user and returns JWT tokens
    (access_token, id_token, refresh_token) for API authorization.
    
    This matches the behavior of email signup where tokens are returned immediately.
    """
)
async def phone_verify_signup(
    request: PhoneVerifyOTPRequest,
    http_request: Request,
    cognito: CognitoAuthService = Depends(get_cognito_service),
    db: Session = Depends(get_db)
):
    """
    Verify phone number with OTP and get authentication tokens
    
    - **phone_number**: Phone number in E.164 format
    - **otp_code**: 6-digit OTP code received via SMS
    
    Returns authentication tokens after successful verification.
    """
    result = cognito.phone_verify_signup(
        phone_number=request.phone_number,
        otp_code=request.otp_code
    )
    
    # If tokens are returned, update user in database
    if 'access_token' in result:
        user_info = cognito.get_user_info(access_token=result['access_token'])
        request_metadata = get_request_metadata(http_request)
        user = UserService.create_user_from_cognito(
            db=db,
            cognito_data=user_info,
            request_metadata=request_metadata
        )
        
        return AuthResponse(
            access_token=result['access_token'],
            id_token=result['id_token'],
            refresh_token=result['refresh_token'],
            expires_in=result['expires_in'],
            token_type=result['token_type']
        )
    else:
        # Fallback: verification succeeded but no tokens (shouldn't happen normally)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Verification succeeded but failed to generate tokens. Please login manually."
        )


@router.post(
    "/phone/login",
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "OTP sent to phone number"},
        403: {"model": ErrorResponse, "description": "Phone number not verified"},
        404: {"model": ErrorResponse, "description": "User not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="Initiate phone login",
    description="""
    Initiate login with phone number - sends OTP via SMS.
    
    **Flow:**
    1. Call this endpoint with phone_number
    2. OTP will be sent to the phone via SMS
    3. Call /phone/login/verify with the OTP and session token to get auth tokens
    """
)
async def phone_login(
    request: PhoneLoginRequest,
    cognito: CognitoAuthService = Depends(get_cognito_service)
):
    """
    Initiate phone login - sends OTP
    
    - **phone_number**: Phone number in E.164 format
    
    Returns session token needed for OTP verification.
    """
    result = cognito.phone_login_initiate(
        phone_number=request.phone_number
    )
    
    return {
        "message": result['message'],
        "session": result['session'],
        "phone_number": request.phone_number
    }


@router.post(
    "/phone/login/verify",
    response_model=AuthResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Successfully authenticated"},
        400: {"model": ErrorResponse, "description": "Invalid or expired OTP"},
        401: {"model": ErrorResponse, "description": "Invalid OTP code"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="Verify OTP and complete login",
    description="""
    Verify OTP code and complete phone login.
    
    Returns JWT tokens (access_token, id_token, refresh_token) for API authorization.
    """
)
async def phone_login_verify(
    request: PhoneLoginVerifyRequest,
    http_request: Request,
    cognito: CognitoAuthService = Depends(get_cognito_service),
    db: Session = Depends(get_db)
):
    """
    Verify OTP and complete login
    
    - **phone_number**: Phone number in E.164 format
    - **session**: Session token from /phone/login endpoint
    - **otp_code**: 6-digit OTP code received via SMS
    
    Returns authentication tokens.
    """
    result = cognito.phone_login_verify(
        phone_number=request.phone_number,
        session=request.session,
        otp_code=request.otp_code
    )
    
    # Get user info and update database
    user_info = cognito.get_user_info(access_token=result['access_token'])
    request_metadata = get_request_metadata(http_request)
    user = UserService.create_user_from_cognito(
        db=db,
        cognito_data=user_info,
        request_metadata=request_metadata
    )
    
    return AuthResponse(
        access_token=result['access_token'],
        id_token=result['id_token'],
        refresh_token=result['refresh_token'],
        expires_in=result['expires_in'],
        token_type=result['token_type']
    )

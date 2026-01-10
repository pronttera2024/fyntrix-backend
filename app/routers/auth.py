"""
Authentication router for AWS Cognito
"""
from fastapi import APIRouter, HTTPException, status, Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
from ..schemas.auth import (
    SignupRequest,
    LoginRequest,
    SignupResponse,
    AuthResponse,
    UserResponse,
    RefreshTokenRequest,
    ErrorResponse
)
from ..services.cognito_auth import get_cognito_service, CognitoAuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Security scheme for JWT Bearer tokens
security = HTTPBearer()


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
    cognito: CognitoAuthService = Depends(get_cognito_service)
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
    cognito: CognitoAuthService = Depends(get_cognito_service)
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

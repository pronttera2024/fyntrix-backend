"""
AWS Cognito Authentication Service
"""
import os
import boto3
import hmac
import hashlib
import base64
from typing import Dict, Optional
from botocore.exceptions import ClientError
from fastapi import HTTPException, status


class CognitoAuthService:
    """AWS Cognito authentication service"""
    
    def __init__(self):
        self.region = os.getenv("AWS_COGNITO_REGION")
        self.user_pool_id = os.getenv("AWS_COGNITO_USER_POOL_ID")
        self.client_id = os.getenv("AWS_COGNITO_CLIENT_ID")
        self.client_secret = os.getenv("AWS_COGNITO_CLIENT_SECRET")
        
        if not all([self.region, self.user_pool_id, self.client_id, self.client_secret]):
            raise ValueError("AWS Cognito environment variables not properly configured")
        
        self.client = boto3.client('cognito-idp', region_name=self.region)
    
    def _get_secret_hash(self, username: str) -> str:
        """Generate secret hash for Cognito client with secret"""
        message = bytes(username + self.client_id, 'utf-8')
        secret = bytes(self.client_secret, 'utf-8')
        dig = hmac.new(secret, message, hashlib.sha256).digest()
        return base64.b64encode(dig).decode()
    
    def signup(self, email: str, password: str, name: str) -> Dict:
        """
        Sign up a new user with AWS Cognito
        Auto-verifies email as per requirements
        """
        try:
            secret_hash = self._get_secret_hash(email)
            
            # Sign up the user
            response = self.client.sign_up(
                ClientId=self.client_id,
                SecretHash=secret_hash,
                Username=email,
                Password=password,
                UserAttributes=[
                    {'Name': 'email', 'Value': email},
                    {'Name': 'name', 'Value': name},
                ]
            )
            
            user_sub = response['UserSub']
            
            # Auto-verify the email (admin privilege)
            self.client.admin_update_user_attributes(
                UserPoolId=self.user_pool_id,
                Username=email,
                UserAttributes=[
                    {'Name': 'email_verified', 'Value': 'true'}
                ]
            )
            
            # Confirm the user (skip verification step)
            self.client.admin_confirm_sign_up(
                UserPoolId=self.user_pool_id,
                Username=email
            )
            
            # Automatically log in the user after signup
            auth_response = self.login(email, password)
            
            return {
                'user_sub': user_sub,
                'email': email,
                'name': name,
                'email_verified': True,
                'auth': auth_response
            }
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            
            if error_code == 'UsernameExistsException':
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="User with this email already exists"
                )
            elif error_code == 'InvalidPasswordException':
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Password does not meet requirements"
                )
            elif error_code == 'InvalidParameterException':
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid parameter: {error_message}"
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Signup failed: {error_message}"
                )
    
    def login(self, email: str, password: str) -> Dict:
        """
        Authenticate user with AWS Cognito
        """
        try:
            secret_hash = self._get_secret_hash(email)
            
            response = self.client.initiate_auth(
                ClientId=self.client_id,
                AuthFlow='USER_PASSWORD_AUTH',
                AuthParameters={
                    'USERNAME': email,
                    'PASSWORD': password,
                    'SECRET_HASH': secret_hash
                }
            )
            
            auth_result = response['AuthenticationResult']
            
            return {
                'access_token': auth_result['AccessToken'],
                'id_token': auth_result['IdToken'],
                'refresh_token': auth_result['RefreshToken'],
                'expires_in': auth_result['ExpiresIn'],
                'token_type': 'Bearer'
            }
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            
            if error_code == 'NotAuthorizedException':
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Incorrect email or password"
                )
            elif error_code == 'UserNotConfirmedException':
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User account is not confirmed"
                )
            elif error_code == 'UserNotFoundException':
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found"
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Login failed: {error_message}"
                )
    
    def refresh_token(self, refresh_token: str, email: str) -> Dict:
        """
        Refresh access token using refresh token
        """
        try:
            secret_hash = self._get_secret_hash(email)
            
            response = self.client.initiate_auth(
                ClientId=self.client_id,
                AuthFlow='REFRESH_TOKEN_AUTH',
                AuthParameters={
                    'REFRESH_TOKEN': refresh_token,
                    'SECRET_HASH': secret_hash
                }
            )
            
            auth_result = response['AuthenticationResult']
            
            return {
                'access_token': auth_result['AccessToken'],
                'id_token': auth_result['IdToken'],
                'expires_in': auth_result['ExpiresIn'],
                'token_type': 'Bearer'
            }
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token refresh failed: {error_message}"
            )
    
    def get_user_info(self, access_token: str) -> Dict:
        """
        Get user information from access token
        """
        try:
            response = self.client.get_user(
                AccessToken=access_token
            )
            
            user_attributes = {attr['Name']: attr['Value'] for attr in response['UserAttributes']}
            
            return {
                'user_id': user_attributes.get('sub'),
                'email': user_attributes.get('email'),
                'name': user_attributes.get('name'),
                'email_verified': user_attributes.get('email_verified') == 'true'
            }
            
        except ClientError as e:
            error_message = e.response['Error']['Message']
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid or expired token: {error_message}"
            )


# Singleton instance
_cognito_service: Optional[CognitoAuthService] = None


def get_cognito_service() -> CognitoAuthService:
    """Get or create Cognito service instance"""
    global _cognito_service
    if _cognito_service is None:
        _cognito_service = CognitoAuthService()
    return _cognito_service

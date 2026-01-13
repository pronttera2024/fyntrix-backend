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
    
    def phone_signup(self, phone_number: str, name: str) -> Dict:
        """
        Sign up a new user with phone number
        Sends OTP via SNS for verification
        """
        try:
            secret_hash = self._get_secret_hash(phone_number)
            
            response = self.client.sign_up(
                ClientId=self.client_id,
                SecretHash=secret_hash,
                Username=phone_number,
                Password=self._generate_random_password(),
                UserAttributes=[
                    {'Name': 'phone_number', 'Value': phone_number},
                    {'Name': 'name', 'Value': name},
                ]
            )
            
            return {
                'user_sub': response['UserSub'],
                'phone_number': phone_number,
                'name': name,
                'message': 'OTP sent to phone number. Please verify to complete signup.'
            }
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            
            if error_code == 'UsernameExistsException':
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="User with this phone number already exists"
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
    
    def phone_verify_signup(self, phone_number: str, otp_code: str) -> Dict:
        """
        Verify phone number with OTP code during signup
        """
        try:
            secret_hash = self._get_secret_hash(phone_number)
            
            self.client.confirm_sign_up(
                ClientId=self.client_id,
                SecretHash=secret_hash,
                Username=phone_number,
                ConfirmationCode=otp_code
            )
            
            return {
                'message': 'Phone number verified successfully. You can now login.',
                'phone_number': phone_number,
                'verified': True
            }
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            
            if error_code == 'CodeMismatchException':
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid OTP code"
                )
            elif error_code == 'ExpiredCodeException':
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="OTP code has expired. Please request a new one."
                )
            elif error_code == 'NotAuthorizedException':
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User is already confirmed or OTP is invalid"
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Verification failed: {error_message}"
                )
    
    def phone_login_initiate(self, phone_number: str) -> Dict:
        """
        Initiate phone login - sends OTP via SNS
        Uses CUSTOM_AUTH flow with SMS_MFA
        """
        try:
            secret_hash = self._get_secret_hash(phone_number)
            
            response = self.client.initiate_auth(
                ClientId=self.client_id,
                AuthFlow='CUSTOM_AUTH',
                AuthParameters={
                    'USERNAME': phone_number,
                    'SECRET_HASH': secret_hash
                }
            )
            
            if response.get('ChallengeName') == 'CUSTOM_CHALLENGE':
                return {
                    'session': response['Session'],
                    'challenge_name': response['ChallengeName'],
                    'message': 'OTP sent to your phone number'
                }
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Unexpected authentication flow"
                )
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            
            if error_code == 'UserNotFoundException':
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found. Please sign up first."
                )
            elif error_code == 'UserNotConfirmedException':
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Phone number not verified. Please complete signup verification."
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Login initiation failed: {error_message}"
                )
    
    def phone_login_verify(self, phone_number: str, session: str, otp_code: str) -> Dict:
        """
        Verify OTP and complete phone login
        Returns authentication tokens
        """
        try:
            secret_hash = self._get_secret_hash(phone_number)
            
            response = self.client.respond_to_auth_challenge(
                ClientId=self.client_id,
                ChallengeName='CUSTOM_CHALLENGE',
                Session=session,
                ChallengeResponses={
                    'USERNAME': phone_number,
                    'ANSWER': otp_code,
                    'SECRET_HASH': secret_hash
                }
            )
            
            if 'AuthenticationResult' in response:
                auth_result = response['AuthenticationResult']
                return {
                    'access_token': auth_result['AccessToken'],
                    'id_token': auth_result['IdToken'],
                    'refresh_token': auth_result['RefreshToken'],
                    'expires_in': auth_result['ExpiresIn'],
                    'token_type': 'Bearer'
                }
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Authentication failed - no tokens returned"
                )
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            
            if error_code == 'CodeMismatchException' or error_code == 'NotAuthorizedException':
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid OTP code"
                )
            elif error_code == 'ExpiredCodeException':
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="OTP code has expired. Please request a new one."
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Login verification failed: {error_message}"
                )
    
    def _generate_random_password(self) -> str:
        """
        Generate a random password for phone-based signup
        Phone users don't use passwords, but Cognito requires one
        """
        import secrets
        import string
        
        chars = string.ascii_letters + string.digits + "!@#$%^&*"
        password = ''.join(secrets.choice(chars) for _ in range(16))
        return password + "A1!"


# Singleton instance
_cognito_service: Optional[CognitoAuthService] = None


def get_cognito_service() -> CognitoAuthService:
    """Get or create Cognito service instance"""
    global _cognito_service
    if _cognito_service is None:
        _cognito_service = CognitoAuthService()
    return _cognito_service

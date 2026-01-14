"""
User Model
Stores authenticated user information from AWS Cognito
"""
from sqlalchemy import Column, String, Boolean, DateTime, Text, Integer, JSON
from sqlalchemy.sql import func
from datetime import datetime
from ..config.database import Base


class User(Base):
    """
    User model for storing authenticated user data
    Synced with AWS Cognito user pool
    """
    __tablename__ = "users"
    
    # Primary identifier (Cognito sub)
    id = Column(String(255), primary_key=True, index=True, comment="Cognito user sub (UUID)")
    
    # Authentication fields
    phone_number = Column(String(20), unique=True, nullable=True, index=True, comment="Phone number in E.164 format")
    phone_number_verified = Column(Boolean, default=False, nullable=False, comment="Phone verification status")
    
    # User profile fields
    name = Column(String(100), nullable=False, comment="User's full name")
    email = Column(String(255), unique=True, nullable=True, index=True, comment="Email address (optional)")
    email_verified = Column(Boolean, default=False, nullable=True, comment="Email verification status")
    
    # Extended profile information
    first_name = Column(String(50), nullable=True, comment="User's first name")
    last_name = Column(String(50), nullable=True, comment="User's last name")
    date_of_birth = Column(DateTime(timezone=True), nullable=True, comment="User's date of birth")
    gender = Column(String(20), nullable=True, comment="User's gender")
    country_code = Column(String(3), nullable=True, comment="ISO country code (e.g., IN, US)")
    timezone = Column(String(50), nullable=True, comment="User's timezone (e.g., Asia/Kolkata)")
    language = Column(String(10), nullable=True, default="en", comment="Preferred language code")
    
    # Account status
    is_active = Column(Boolean, default=True, nullable=False, comment="Account active status")
    is_deleted = Column(Boolean, default=False, nullable=False, comment="Soft delete flag")
    is_verified = Column(Boolean, default=False, nullable=False, comment="Full account verification status")
    is_premium = Column(Boolean, default=False, nullable=False, comment="Premium subscription status")
    
    # Cognito metadata
    cognito_username = Column(String(255), nullable=True, comment="Cognito username")
    cognito_status = Column(String(50), nullable=True, comment="Cognito user status")
    
    # Additional profile data
    profile_picture_url = Column(Text, nullable=True, comment="Profile picture URL")
    bio = Column(Text, nullable=True, comment="User bio/description")
    
    # Audit trail - Login tracking
    last_login_at = Column(DateTime(timezone=True), nullable=True, comment="Last login timestamp")
    last_login_ip = Column(String(45), nullable=True, comment="Last login IP address (IPv4/IPv6)")
    last_login_device = Column(String(255), nullable=True, comment="Last login device info")
    last_login_location = Column(String(255), nullable=True, comment="Last login location (city, country)")
    login_count = Column(Integer, default=0, nullable=False, comment="Total number of logins")
    
    # Audit trail - Account activity
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, comment="Account creation timestamp")
    created_ip = Column(String(45), nullable=True, comment="IP address at account creation")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False, comment="Last update timestamp")
    deleted_at = Column(DateTime(timezone=True), nullable=True, comment="Account deletion timestamp")
    
    # User preferences and settings
    preferences = Column(JSON, nullable=True, comment="User preferences as JSON (notifications, theme, etc.)")
    settings = Column(JSON, nullable=True, comment="User settings as JSON")
    
    # Additional metadata
    user_metadata = Column(JSON, nullable=True, comment="Additional JSON metadata")
    referral_code = Column(String(50), nullable=True, unique=True, index=True, comment="User's unique referral code")
    referred_by = Column(String(255), nullable=True, comment="ID of user who referred this user")
    
    def __repr__(self):
        return f"<User(id={self.id}, phone={self.phone_number}, name={self.name})>"
    
    def to_dict(self):
        """Convert user to dictionary"""
        return {
            "id": self.id,
            "phone_number": self.phone_number,
            "phone_number_verified": self.phone_number_verified,
            "name": self.name,
            "email": self.email,
            "email_verified": self.email_verified,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "date_of_birth": self.date_of_birth.isoformat() if self.date_of_birth else None,
            "gender": self.gender,
            "country_code": self.country_code,
            "timezone": self.timezone,
            "language": self.language,
            "is_active": self.is_active,
            "is_verified": self.is_verified,
            "is_premium": self.is_premium,
            "profile_picture_url": self.profile_picture_url,
            "bio": self.bio,
            "login_count": self.login_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
            "preferences": self.preferences,
            "settings": self.settings,
            "referral_code": self.referral_code,
            "user_metadata": self.user_metadata,
        }
    
    @classmethod
    def from_cognito(cls, cognito_user_data: dict, request_metadata: dict = None):
        """
        Create User instance from Cognito user data
        
        Args:
            cognito_user_data: Dictionary containing Cognito user attributes
            request_metadata: Optional dictionary with IP, device, location info
            
        Returns:
            User instance
        """
        user = cls(
            id=cognito_user_data.get("sub"),
            phone_number=cognito_user_data.get("phone_number"),
            phone_number_verified=cognito_user_data.get("phone_number_verified", False),
            name=cognito_user_data.get("name"),
            email=cognito_user_data.get("email"),
            email_verified=cognito_user_data.get("email_verified", False),
            cognito_username=cognito_user_data.get("username"),
            cognito_status=cognito_user_data.get("status"),
            first_name=cognito_user_data.get("given_name"),
            last_name=cognito_user_data.get("family_name"),
            language=cognito_user_data.get("locale", "en"),
        )
        
        # Add request metadata if provided
        if request_metadata:
            user.created_ip = request_metadata.get("ip_address")
            user.last_login_ip = request_metadata.get("ip_address")
            user.last_login_device = request_metadata.get("device")
            user.last_login_location = request_metadata.get("location")
        
        return user

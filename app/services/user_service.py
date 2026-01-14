"""
User Service
Handles user-related business logic and database operations
"""
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from datetime import datetime
from typing import Optional, Dict
from fastapi import HTTPException, status
import logging

from ..models.user import User

logger = logging.getLogger(__name__)


class UserService:
    """Service for managing user operations"""
    
    @staticmethod
    def create_user_from_cognito(db: Session, cognito_data: dict, request_metadata: dict = None) -> User:
        """
        Create or update user from Cognito authentication data
        
        Args:
            db: Database session
            cognito_data: User data from Cognito (sub, phone_number, name, etc.)
            request_metadata: Optional dict with ip_address, device, location, user_agent
            
        Returns:
            User instance
        """
        user_id = cognito_data.get("user_id") or cognito_data.get("sub")
        
        if not user_id:
            raise ValueError("User ID (sub) is required")
        
        # Check if user already exists
        existing_user = db.query(User).filter(User.id == user_id).first()
        
        if existing_user:
            # Update existing user on login
            existing_user.name = cognito_data.get("name", existing_user.name)
            existing_user.phone_number = cognito_data.get("phone_number", existing_user.phone_number)
            existing_user.phone_number_verified = cognito_data.get("phone_number_verified", existing_user.phone_number_verified)
            existing_user.email = cognito_data.get("email", existing_user.email)
            existing_user.email_verified = cognito_data.get("email_verified", existing_user.email_verified)
            existing_user.last_login_at = datetime.utcnow()
            existing_user.login_count = (existing_user.login_count or 0) + 1
            existing_user.updated_at = datetime.utcnow()
            
            # Update login metadata if provided
            if request_metadata:
                existing_user.last_login_ip = request_metadata.get("ip_address")
                existing_user.last_login_device = request_metadata.get("device")
                existing_user.last_login_location = request_metadata.get("location")
            
            db.commit()
            db.refresh(existing_user)
            
            logger.info(f"Updated user {user_id} on login (login count: {existing_user.login_count})")
            return existing_user
        else:
            # Create new user
            new_user = User(
                id=user_id,
                phone_number=cognito_data.get("phone_number"),
                phone_number_verified=cognito_data.get("phone_number_verified", False),
                name=cognito_data.get("name"),
                email=cognito_data.get("email"),
                email_verified=cognito_data.get("email_verified", False),
                cognito_username=cognito_data.get("username"),
                cognito_status=cognito_data.get("status"),
                first_name=cognito_data.get("given_name"),
                last_name=cognito_data.get("family_name"),
                language=cognito_data.get("locale", "en"),
                last_login_at=datetime.utcnow(),
                login_count=1
            )
            
            # Add creation and login metadata if provided
            if request_metadata:
                new_user.created_ip = request_metadata.get("ip_address")
                new_user.last_login_ip = request_metadata.get("ip_address")
                new_user.last_login_device = request_metadata.get("device")
                new_user.last_login_location = request_metadata.get("location")
            
            try:
                db.add(new_user)
                db.commit()
                db.refresh(new_user)
                
                logger.info(f"Created new user {user_id}")
                return new_user
            except IntegrityError as e:
                db.rollback()
                logger.error(f"Error creating user: {e}")
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="User with this phone number or email already exists"
                )
    
    @staticmethod
    def get_user_by_id(db: Session, user_id: str) -> Optional[User]:
        """Get user by ID"""
        return db.query(User).filter(User.id == user_id, User.is_deleted == False).first()
    
    @staticmethod
    def get_user_by_phone(db: Session, phone_number: str) -> Optional[User]:
        """Get user by phone number"""
        return db.query(User).filter(
            User.phone_number == phone_number,
            User.is_deleted == False
        ).first()
    
    @staticmethod
    def update_user(db: Session, user_id: str, update_data: dict) -> User:
        """
        Update user information
        
        Args:
            db: Database session
            user_id: User ID
            update_data: Dictionary of fields to update
            
        Returns:
            Updated User instance
        """
        user = UserService.get_user_by_id(db, user_id)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Update allowed fields
        allowed_fields = ["name", "email", "bio", "profile_picture_url"]
        
        for field, value in update_data.items():
            if field in allowed_fields and value is not None:
                setattr(user, field, value)
        
        user.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(user)
        
        logger.info(f"Updated user {user_id}")
        return user
    
    @staticmethod
    def deactivate_user(db: Session, user_id: str) -> User:
        """Deactivate user account (soft delete)"""
        user = UserService.get_user_by_id(db, user_id)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        user.is_active = False
        user.is_deleted = True
        user.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(user)
        
        logger.info(f"Deactivated user {user_id}")
        return user
    
    @staticmethod
    def update_last_login(db: Session, user_id: str) -> None:
        """Update user's last login timestamp"""
        user = UserService.get_user_by_id(db, user_id)
        
        if user:
            user.last_login_at = datetime.utcnow()
            db.commit()

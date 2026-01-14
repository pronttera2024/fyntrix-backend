from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status
from typing import Optional, Dict, Any
import logging

from ..models.user_preferences import UserPreferences

logger = logging.getLogger(__name__)


class UserPreferencesService:
    """Service for managing user preferences"""
    
    @staticmethod
    def get_preferences(db: Session, user_id: str) -> Optional[UserPreferences]:
        """
        Get user preferences by user_id
        
        Args:
            db: Database session
            user_id: User ID
            
        Returns:
            UserPreferences instance or None
        """
        return db.query(UserPreferences).filter(UserPreferences.user_id == user_id).first()
    
    @staticmethod
    def create_preferences(db: Session, user_id: str, preferences_data: Dict[str, Any]) -> UserPreferences:
        """
        Create user preferences
        
        Args:
            db: Database session
            user_id: User ID
            preferences_data: Dictionary with preference fields
            
        Returns:
            UserPreferences instance
        """
        try:
            preferences = UserPreferences(
                user_id=user_id,
                disclosure_accepted=preferences_data.get("disclosure_accepted", False),
                disclosure_version=preferences_data.get("disclosure_version"),
                universe=preferences_data.get("universe", "NIFTY50"),
                market_region=preferences_data.get("market_region", "India"),
                risk_profile=preferences_data.get("risk_profile", "Moderate"),
                trading_modes=preferences_data.get("trading_modes"),
                primary_mode=preferences_data.get("primary_mode"),
                auxiliary_modes=preferences_data.get("auxiliary_modes"),
            )
            
            db.add(preferences)
            db.commit()
            db.refresh(preferences)
            
            logger.info(f"Created preferences for user {user_id}")
            return preferences
            
        except IntegrityError as e:
            db.rollback()
            logger.error(f"Error creating preferences for user {user_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Preferences already exist for this user"
            )
    
    @staticmethod
    def update_preferences(db: Session, user_id: str, preferences_data: Dict[str, Any]) -> UserPreferences:
        """
        Update user preferences (full or partial)
        
        Args:
            db: Database session
            user_id: User ID
            preferences_data: Dictionary with preference fields to update
            
        Returns:
            Updated UserPreferences instance
        """
        preferences = db.query(UserPreferences).filter(UserPreferences.user_id == user_id).first()
        
        if not preferences:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Preferences not found for this user"
            )
        
        # Update only provided fields
        for key, value in preferences_data.items():
            if hasattr(preferences, key) and value is not None:
                setattr(preferences, key, value)
        
        try:
            db.commit()
            db.refresh(preferences)
            
            logger.info(f"Updated preferences for user {user_id}")
            return preferences
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error updating preferences for user {user_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update preferences"
            )
    
    @staticmethod
    def get_or_create_preferences(db: Session, user_id: str, defaults: Optional[Dict[str, Any]] = None) -> UserPreferences:
        """
        Get existing preferences or create with defaults
        
        Args:
            db: Database session
            user_id: User ID
            defaults: Default values if creating new preferences
            
        Returns:
            UserPreferences instance
        """
        preferences = UserPreferencesService.get_preferences(db, user_id)
        
        if not preferences:
            preferences_data = defaults or {}
            preferences = UserPreferencesService.create_preferences(db, user_id, preferences_data)
        
        return preferences

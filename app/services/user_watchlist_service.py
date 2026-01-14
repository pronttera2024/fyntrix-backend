from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status
from typing import List, Optional, Dict, Any
import logging

from ..models.watchlist import UserWatchlist

logger = logging.getLogger(__name__)


class UserWatchlistService:
    """Service for managing user watchlists"""
    
    @staticmethod
    def get_watchlist(db: Session, user_id: str) -> List[UserWatchlist]:
        """
        Get all watchlist entries for a user
        
        Args:
            db: Database session
            user_id: User ID
            
        Returns:
            List of UserWatchlist instances
        """
        return db.query(UserWatchlist).filter(
            UserWatchlist.user_id == user_id
        ).order_by(UserWatchlist.added_at.desc()).all()
    
    @staticmethod
    def add_to_watchlist(db: Session, user_id: str, symbol: str, exchange: Optional[str] = None, notes: Optional[str] = None) -> UserWatchlist:
        """
        Add a symbol to user's watchlist
        
        Args:
            db: Database session
            user_id: User ID
            symbol: Stock symbol
            exchange: Exchange (optional)
            notes: User notes (optional)
            
        Returns:
            UserWatchlist instance
        """
        try:
            watchlist_entry = UserWatchlist(
                user_id=user_id,
                symbol=symbol.upper(),
                exchange=exchange,
                notes=notes
            )
            
            db.add(watchlist_entry)
            db.commit()
            db.refresh(watchlist_entry)
            
            logger.info(f"Added {symbol} to watchlist for user {user_id}")
            return watchlist_entry
            
        except IntegrityError as e:
            db.rollback()
            logger.warning(f"Symbol {symbol} already in watchlist for user {user_id}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Symbol {symbol} is already in your watchlist"
            )
    
    @staticmethod
    def remove_from_watchlist(db: Session, user_id: str, symbol: str) -> bool:
        """
        Remove a symbol from user's watchlist
        
        Args:
            db: Database session
            user_id: User ID
            symbol: Stock symbol
            
        Returns:
            True if removed, False if not found
        """
        entry = db.query(UserWatchlist).filter(
            UserWatchlist.user_id == user_id,
            UserWatchlist.symbol == symbol.upper()
        ).first()
        
        if not entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Symbol {symbol} not found in watchlist"
            )
        
        db.delete(entry)
        db.commit()
        
        logger.info(f"Removed {symbol} from watchlist for user {user_id}")
        return True
    
    @staticmethod
    def update_watchlist_entry(db: Session, user_id: str, symbol: str, notes: Optional[str] = None, exchange: Optional[str] = None) -> UserWatchlist:
        """
        Update watchlist entry notes or exchange
        
        Args:
            db: Database session
            user_id: User ID
            symbol: Stock symbol
            notes: Updated notes (optional)
            exchange: Updated exchange (optional)
            
        Returns:
            Updated UserWatchlist instance
        """
        entry = db.query(UserWatchlist).filter(
            UserWatchlist.user_id == user_id,
            UserWatchlist.symbol == symbol.upper()
        ).first()
        
        if not entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Symbol {symbol} not found in watchlist"
            )
        
        if notes is not None:
            entry.notes = notes
        if exchange is not None:
            entry.exchange = exchange
        
        db.commit()
        db.refresh(entry)
        
        logger.info(f"Updated watchlist entry for {symbol}, user {user_id}")
        return entry
    
    @staticmethod
    def bulk_add_to_watchlist(db: Session, user_id: str, symbols: List[str]) -> List[UserWatchlist]:
        """
        Add multiple symbols to watchlist at once
        
        Args:
            db: Database session
            user_id: User ID
            symbols: List of stock symbols
            
        Returns:
            List of created UserWatchlist instances
        """
        added_entries = []
        
        for symbol in symbols:
            try:
                entry = UserWatchlist(
                    user_id=user_id,
                    symbol=symbol.upper()
                )
                db.add(entry)
                added_entries.append(entry)
            except IntegrityError:
                # Skip duplicates
                logger.warning(f"Symbol {symbol} already in watchlist for user {user_id}, skipping")
                continue
        
        try:
            db.commit()
            for entry in added_entries:
                db.refresh(entry)
            
            logger.info(f"Bulk added {len(added_entries)} symbols to watchlist for user {user_id}")
            return added_entries
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error bulk adding to watchlist for user {user_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to add symbols to watchlist"
            )
    
    @staticmethod
    def clear_watchlist(db: Session, user_id: str) -> int:
        """
        Clear all watchlist entries for a user
        
        Args:
            db: Database session
            user_id: User ID
            
        Returns:
            Number of entries deleted
        """
        count = db.query(UserWatchlist).filter(
            UserWatchlist.user_id == user_id
        ).delete()
        
        db.commit()
        
        logger.info(f"Cleared {count} watchlist entries for user {user_id}")
        return count
    
    @staticmethod
    def is_in_watchlist(db: Session, user_id: str, symbol: str) -> bool:
        """
        Check if a symbol is in user's watchlist
        
        Args:
            db: Database session
            user_id: User ID
            symbol: Stock symbol
            
        Returns:
            True if in watchlist, False otherwise
        """
        entry = db.query(UserWatchlist).filter(
            UserWatchlist.user_id == user_id,
            UserWatchlist.symbol == symbol.upper()
        ).first()
        
        return entry is not None

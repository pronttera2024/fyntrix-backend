"""
Token Monitor Service
Monitors Zerodha token expiry and sends reminders
"""

import os
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .notification_service import get_notification_service

logger = logging.getLogger(__name__)


class TokenMonitor:
    """
    Monitors Zerodha token expiry and sends timely reminders
    """
    
    def __init__(self):
        self.notification_service = get_notification_service()
        self.scheduler = AsyncIOScheduler()
        self.token_file = Path(__file__).parent.parent.parent / '.zerodha_token'
        self.token_metadata_file = Path(__file__).parent.parent.parent / '.zerodha_token_metadata.json'
        
        # Track last reminder sent
        self.last_reminder_sent = None
        self.reminder_intervals = [12, 6, 2, 1]  # Hours before expiry to send reminders
        
        logger.info("✓ Token monitor initialized")
    
    def get_token_expiry_time(self) -> Optional[datetime]:
        """
        Get token expiry time from metadata file
        
        Returns:
            Expiry datetime or None if not available
        """
        try:
            import json
            if self.token_metadata_file.exists():
                with open(self.token_metadata_file, 'r') as f:
                    metadata = json.load(f)
                    expiry_str = metadata.get('expires_at')
                    if expiry_str:
                        return datetime.fromisoformat(expiry_str)
        except Exception as e:
            logger.debug(f"Could not read token metadata: {e}")
        
        # Fallback: check token file modification time + 24 hours
        try:
            if self.token_file.exists():
                token_created = datetime.fromtimestamp(self.token_file.stat().st_mtime)
                return token_created + timedelta(hours=24)
        except Exception as e:
            logger.debug(f"Could not determine token expiry: {e}")
        
        return None
    
    def save_token_metadata(self, expires_at: datetime, user_name: Optional[str] = None):
        """Save token metadata for future reference"""
        try:
            import json
            metadata = {
                'expires_at': expires_at.isoformat(),
                'user_name': user_name,
                'last_updated': datetime.now().isoformat()
            }
            with open(self.token_metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
            logger.info(f"✓ Token metadata saved (expires: {expires_at})")
        except Exception as e:
            logger.error(f"Failed to save token metadata: {e}")
    
    async def check_token_expiry(self):
        """Check token expiry and send reminders if needed"""
        try:
            expiry_time = self.get_token_expiry_time()
            
            if not expiry_time:
                logger.debug("No token expiry time available")
                return
            
            now = datetime.now()
            time_remaining = expiry_time - now
            hours_remaining = time_remaining.total_seconds() / 3600
            
            # Token already expired
            if hours_remaining <= 0:
                logger.warning("⚠️  Zerodha token has EXPIRED")
                await self.handle_expired_token()
                return
            
            # Check if we should send a reminder
            for reminder_hour in self.reminder_intervals:
                if hours_remaining <= reminder_hour:
                    # Check if we already sent this reminder
                    if self.last_reminder_sent != reminder_hour:
                        logger.info(f"📧 Sending token expiry reminder ({int(hours_remaining)} hours remaining)")
                        
                        # Send reminder
                        success = self.notification_service.send_token_expiry_reminder(
                            hours_remaining=int(hours_remaining)
                        )
                        
                        if success:
                            self.last_reminder_sent = reminder_hour
                            logger.info(f"✓ Reminder sent for {reminder_hour}h interval")
                        else:
                            logger.warning(f"⚠️  Failed to send reminder")
                    break
            
            logger.debug(f"Token expires in {hours_remaining:.1f} hours")
            
        except Exception as e:
            logger.error(f"Error checking token expiry: {e}")
    
    async def handle_expired_token(self):
        """Handle expired token scenario"""
        try:
            # Send expiry notification (only once)
            if self.last_reminder_sent != "expired":
                self.notification_service.send_token_expired_notification()
                self.last_reminder_sent = "expired"
                logger.warning("⚠️  Token expired notification sent")
            
            # Delete token file to force fallback
            if self.token_file.exists():
                self.token_file.unlink()
                logger.info("✓ Expired token file removed")
            
            # Delete metadata
            if self.token_metadata_file.exists():
                self.token_metadata_file.unlink()
                logger.info("✓ Token metadata removed")
            
        except Exception as e:
            logger.error(f"Error handling expired token: {e}")
    
    def start_monitoring(self):
        """Start the token monitoring scheduler"""
        try:
            # Check every 30 minutes
            self.scheduler.add_job(
                self.check_token_expiry,
                CronTrigger(minute='*/30'),  # Every 30 minutes
                id='token_expiry_check',
                replace_existing=True
            )
            
            # Also check at specific times: 9 AM, 3 PM, 9 PM
            self.scheduler.add_job(
                self.check_token_expiry,
                CronTrigger(hour='9,15,21', minute='0'),
                id='token_expiry_check_scheduled',
                replace_existing=True
            )
            
            self.scheduler.start()
            logger.info("✓ Token monitoring started")
            logger.info("  - Checking every 30 minutes")
            logger.info("  - Special checks at 9 AM, 3 PM, 9 PM")
            
            # Do an immediate check
            asyncio.create_task(self.check_token_expiry())
            
        except Exception as e:
            logger.error(f"Failed to start token monitoring: {e}")
    
    def stop_monitoring(self):
        """Stop the token monitoring scheduler"""
        try:
            self.scheduler.shutdown()
            logger.info("✓ Token monitoring stopped")
        except Exception as e:
            logger.error(f"Error stopping token monitoring: {e}")
    
    def check_now(self) -> dict:
        """
        Manually trigger token check (for testing)
        
        Returns:
            Status dict with expiry info
        """
        expiry_time = self.get_token_expiry_time()
        
        if not expiry_time:
            return {
                "status": "no_token",
                "message": "No token found or expiry time unavailable"
            }
        
        now = datetime.now()
        time_remaining = expiry_time - now
        hours_remaining = time_remaining.total_seconds() / 3600
        
        if hours_remaining <= 0:
            return {
                "status": "expired",
                "message": "Token has expired",
                "expired_at": expiry_time.isoformat()
            }
        
        return {
            "status": "active",
            "message": f"Token expires in {hours_remaining:.1f} hours",
            "expires_at": expiry_time.isoformat(),
            "hours_remaining": hours_remaining
        }


# Global instance
_token_monitor = None

def get_token_monitor() -> TokenMonitor:
    """Get or create token monitor instance"""
    global _token_monitor
    if _token_monitor is None:
        _token_monitor = TokenMonitor()
    return _token_monitor


async def start_token_monitoring():
    """Start token monitoring (call this on app startup)"""
    monitor = get_token_monitor()
    monitor.start_monitoring()


def stop_token_monitoring():
    """Stop token monitoring (call this on app shutdown)"""
    monitor = get_token_monitor()
    monitor.stop_monitoring()

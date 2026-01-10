"""
Notifications API Router
Handles notification retrieval and management
"""

from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from ..services.notification_service import get_notification_service
from ..services.token_monitor import get_token_monitor

router = APIRouter(tags=["notifications"])


@router.get("/notifications")
async def get_notifications(
    unread_only: bool = False,
    limit: int = 50
) -> Dict[str, Any]:
    """
    Get notifications for the user
    
    Args:
        unread_only: Only return unread notifications
        limit: Maximum number of notifications to return
        
    Returns:
        List of notifications
    """
    service = get_notification_service()
    notifications = service.get_notifications(unread_only=unread_only, limit=limit)
    
    unread_count = sum(1 for n in service.notifications if not n.get('read', False))
    
    return {
        "notifications": notifications,
        "unread_count": unread_count,
        "total_count": len(service.notifications)
    }


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str) -> Dict[str, Any]:
    """Mark a notification as read"""
    service = get_notification_service()
    success = service.mark_as_read(notification_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    return {
        "status": "success",
        "message": "Notification marked as read"
    }


@router.get("/notifications/token-status")
async def get_token_status() -> Dict[str, Any]:
    """
    Get current Zerodha token status
    
    Returns:
        Token expiry information
    """
    monitor = get_token_monitor()
    status = monitor.check_now()
    
    return status


@router.post("/notifications/test-token-reminder")
async def test_token_reminder(hours_remaining: int = 2) -> Dict[str, Any]:
    """
    Test token expiry reminder (for testing)
    
    Args:
        hours_remaining: Simulate hours remaining
        
    Returns:
        Test result
    """
    service = get_notification_service()
    success = service.send_token_expiry_reminder(hours_remaining=hours_remaining)
    
    return {
        "status": "success" if success else "partial",
        "message": "Test reminder sent",
        "email_sent": success,
        "notification_created": True
    }


@router.post("/notifications/check-token-now")
async def check_token_now() -> Dict[str, Any]:
    """
    Manually trigger token expiry check
    
    Returns:
        Check result
    """
    monitor = get_token_monitor()
    await monitor.check_token_expiry()
    
    return {
        "status": "success",
        "message": "Token check completed"
    }

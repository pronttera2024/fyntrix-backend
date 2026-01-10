"""
Notification Service
Handles email notifications and in-app alerts
"""

import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from pathlib import Path
import json

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Unified notification service for email and in-app notifications
    Supports multiple channels: Email, SMS (future), Push (future)
    """
    
    def __init__(self):
        # Email configuration
        self.smtp_host = os.getenv('SMTP_HOST', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.smtp_user = os.getenv('SMTP_USER', '')
        self.smtp_password = os.getenv('SMTP_PASSWORD', '')
        self.from_email = os.getenv('SMTP_FROM_EMAIL', self.smtp_user)
        self.from_name = os.getenv('SMTP_FROM_NAME', 'ARISE Trading Platform')
        
        # User email (from environment or config)
        self.user_email = os.getenv('USER_EMAIL', '')
        self.user_name = os.getenv('USER_NAME', 'User')
        
        # Notification storage
        self.notifications_file = Path(__file__).parent.parent.parent / '.notifications.json'
        self.notifications: List[Dict[str, Any]] = []
        self._load_notifications()
        
        if self.smtp_user and self.smtp_password:
            logger.info("✓ Email service configured")
        else:
            logger.warning("⚠️  Email not configured. Set SMTP_USER and SMTP_PASSWORD")
    
    def _load_notifications(self):
        """Load notifications from file"""
        try:
            if self.notifications_file.exists():
                with open(self.notifications_file, 'r') as f:
                    self.notifications = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load notifications: {e}")
            self.notifications = []
    
    def _save_notifications(self):
        """Save notifications to file"""
        try:
            with open(self.notifications_file, 'w') as f:
                json.dump(self.notifications[-100:], f, indent=2)  # Keep last 100
        except Exception as e:
            logger.error(f"Failed to save notifications: {e}")
    
    def send_email(
        self,
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
        to_email: Optional[str] = None,
        priority: str = "normal"
    ) -> bool:
        """
        Send email notification
        
        Args:
            subject: Email subject
            body_text: Plain text body
            body_html: HTML body (optional)
            to_email: Recipient email (defaults to user_email)
            priority: "low", "normal", "high"
            
        Returns:
            True if sent successfully
        """
        if not self.smtp_user or not self.smtp_password:
            logger.warning("Email not configured. Notification logged only.")
            return False
        
        recipient = to_email or self.user_email
        if not recipient:
            logger.error("No recipient email configured")
            return False
        
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = recipient
            
            # Set priority
            if priority == "high":
                msg['X-Priority'] = '1'
                msg['Importance'] = 'high'
            elif priority == "low":
                msg['X-Priority'] = '5'
                msg['Importance'] = 'low'
            
            # Attach text and HTML parts
            msg.attach(MIMEText(body_text, 'plain'))
            if body_html:
                msg.attach(MIMEText(body_html, 'html'))
            
            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            
            logger.info(f"✓ Email sent to {recipient}: {subject}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False
    
    def create_notification(
        self,
        title: str,
        message: str,
        type: str = "info",
        action_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create in-app notification
        
        Args:
            title: Notification title
            message: Notification message
            type: "info", "warning", "error", "success"
            action_url: URL to navigate to (optional)
            metadata: Additional data (optional)
            
        Returns:
            Notification object
        """
        notification = {
            "id": f"notif_{datetime.now().timestamp()}",
            "title": title,
            "message": message,
            "type": type,
            "action_url": action_url,
            "metadata": metadata or {},
            "created_at": datetime.now().isoformat(),
            "read": False
        }
        
        self.notifications.append(notification)
        self._save_notifications()
        
        logger.info(f"✓ Notification created: {title}")
        return notification
    
    def get_notifications(
        self,
        unread_only: bool = False,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get notifications"""
        notifications = self.notifications
        
        if unread_only:
            notifications = [n for n in notifications if not n.get('read', False)]
        
        return notifications[-limit:]
    
    def mark_as_read(self, notification_id: str) -> bool:
        """Mark notification as read"""
        for notif in self.notifications:
            if notif.get('id') == notification_id:
                notif['read'] = True
                self._save_notifications()
                return True
        return False
    
    def send_token_expiry_reminder(
        self,
        hours_remaining: int,
        user_name: Optional[str] = None
    ) -> bool:
        """
        Send Zerodha token expiry reminder
        
        Args:
            hours_remaining: Hours until token expires
            user_name: User name for personalization
            
        Returns:
            True if notification sent
        """
        user_name = user_name or self.user_name
        
        # Email subject and body
        if hours_remaining <= 2:
            urgency = "URGENT"
            priority = "high"
            emoji = "🚨"
        elif hours_remaining <= 6:
            urgency = "IMPORTANT"
            priority = "normal"
            emoji = "⚠️"
        else:
            urgency = "Reminder"
            priority = "normal"
            emoji = "🔔"
        
        subject = f"{emoji} {urgency}: Zerodha Token Expiring in {hours_remaining} Hours"
        
        # Plain text body
        body_text = f"""
Hello {user_name},

Your Zerodha authentication token will expire in {hours_remaining} hours.

To continue receiving real-time market data from Zerodha, please re-authenticate:

1. Open ARISE Trading Platform: http://127.0.0.1:5178
2. Click on "Settings" or "Zerodha Authentication"
3. Complete the login process

If you don't re-authenticate, the system will automatically fall back to Yahoo Finance (with a 15-20 minute delay).

Best regards,
ARISE Trading Platform

---
This is an automated notification. You're receiving this because you authenticated with Zerodha.
"""
        
        # HTML body
        body_html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                   color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
        .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
        .warning {{ background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 20px 0; }}
        .urgent {{ background: #f8d7da; border-left: 4px solid #dc3545; padding: 15px; margin: 20px 0; }}
        .button {{ display: inline-block; background: #667eea; color: white; padding: 12px 30px; 
                   text-decoration: none; border-radius: 5px; margin: 20px 0; }}
        .steps {{ background: white; padding: 20px; border-radius: 5px; margin: 20px 0; }}
        .step {{ margin: 10px 0; padding-left: 30px; position: relative; }}
        .step::before {{ content: "→"; position: absolute; left: 0; color: #667eea; font-weight: bold; }}
        .footer {{ text-align: center; color: #888; font-size: 12px; margin-top: 30px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{emoji} Token Expiry {urgency}</h1>
            <p style="font-size: 18px; margin: 10px 0 0 0;">Your Zerodha authentication expires in {hours_remaining} hours</p>
        </div>
        <div class="content">
            <p>Hello <strong>{user_name}</strong>,</p>
            
            <div class="{'urgent' if hours_remaining <= 2 else 'warning'}">
                <strong>⏰ Time Remaining: {hours_remaining} hours</strong><br>
                Your Zerodha token will expire soon. Re-authenticate to continue receiving real-time data.
            </div>
            
            <h3>🔄 How to Re-authenticate:</h3>
            <div class="steps">
                <div class="step">Open ARISE Trading Platform</div>
                <div class="step">Go to Settings → Zerodha Authentication</div>
                <div class="step">Click "Generate Login URL"</div>
                <div class="step">Complete the Zerodha login process</div>
                <div class="step">Your token will be valid for another 24 hours</div>
            </div>
            
            <div style="text-align: center;">
                <a href="http://127.0.0.1:5178" class="button">Open ARISE Platform</a>
            </div>
            
            <p style="margin-top: 30px; color: #666;">
                <strong>What happens if I don't re-authenticate?</strong><br>
                The system will automatically fall back to Yahoo Finance. Your data will still be real, 
                but with a 15-20 minute delay instead of real-time.
            </p>
            
            <div class="footer">
                <p>This is an automated notification from ARISE Trading Platform</p>
                <p>You're receiving this because you authenticated with Zerodha</p>
            </div>
        </div>
    </div>
</body>
</html>
"""
        
        # Send email
        email_sent = self.send_email(
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            priority=priority
        )
        
        # Create in-app notification
        notification_type = "error" if hours_remaining <= 2 else "warning"
        self.create_notification(
            title=f"Zerodha Token Expiring Soon",
            message=f"Your token will expire in {hours_remaining} hours. Re-authenticate to continue real-time data.",
            type=notification_type,
            action_url="/settings/zerodha",
            metadata={
                "hours_remaining": hours_remaining,
                "expires_at": (datetime.now() + timedelta(hours=hours_remaining)).isoformat()
            }
        )
        
        return email_sent
    
    def send_token_expired_notification(self, user_name: Optional[str] = None) -> bool:
        """Send notification that token has expired"""
        user_name = user_name or self.user_name
        
        subject = "🔴 Zerodha Token Expired - Action Required"
        
        body_text = f"""
Hello {user_name},

Your Zerodha authentication token has EXPIRED.

The system has automatically switched to Yahoo Finance (with a 15-20 minute delay).

To restore real-time data from Zerodha, please re-authenticate:
http://127.0.0.1:5178/settings/zerodha

Best regards,
ARISE Trading Platform
"""
        
        body_html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #dc3545; color: white; padding: 30px; text-align: center; }}
        .content {{ background: #f9f9f9; padding: 30px; }}
        .alert {{ background: #f8d7da; border: 1px solid #dc3545; padding: 20px; border-radius: 5px; }}
        .button {{ display: inline-block; background: #dc3545; color: white; padding: 12px 30px; 
                   text-decoration: none; border-radius: 5px; margin: 20px 0; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔴 Token Expired</h1>
        </div>
        <div class="content">
            <div class="alert">
                <h3>Your Zerodha token has expired</h3>
                <p>The system is now using Yahoo Finance with a 15-20 minute delay.</p>
            </div>
            <p>To restore real-time data, please re-authenticate with Zerodha.</p>
            <div style="text-align: center;">
                <a href="http://127.0.0.1:5178/settings/zerodha" class="button">Re-authenticate Now</a>
            </div>
        </div>
    </div>
</body>
</html>
"""
        
        email_sent = self.send_email(
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            priority="high"
        )
        
        self.create_notification(
            title="Zerodha Token Expired",
            message="Your token has expired. System switched to Yahoo Finance. Re-authenticate for real-time data.",
            type="error",
            action_url="/settings/zerodha"
        )
        
        return email_sent


# Global instance
_notification_service = None

def get_notification_service() -> NotificationService:
    """Get or create notification service instance"""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service

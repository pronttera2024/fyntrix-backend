"""Create enhanced users table with audit fields

Revision ID: 0002_create_enhanced_users_table
Revises: 0001_exec_trading_tables
Create Date: 2026-01-14

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0002_create_enhanced_users_table"
down_revision = "0001_exec_trading_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        # Primary identifier
        sa.Column("id", sa.String(length=255), primary_key=True, comment="Cognito user sub (UUID)"),
        
        # Authentication fields
        sa.Column("phone_number", sa.String(length=20), nullable=True, unique=True, comment="Phone number in E.164 format"),
        sa.Column("phone_number_verified", sa.Boolean(), nullable=False, server_default="false", comment="Phone verification status"),
        
        # User profile fields
        sa.Column("name", sa.String(length=100), nullable=False, comment="User's full name"),
        sa.Column("email", sa.String(length=255), nullable=True, unique=True, comment="Email address (optional)"),
        sa.Column("email_verified", sa.Boolean(), nullable=True, server_default="false", comment="Email verification status"),
        
        # Extended profile information
        sa.Column("first_name", sa.String(length=50), nullable=True, comment="User's first name"),
        sa.Column("last_name", sa.String(length=50), nullable=True, comment="User's last name"),
        sa.Column("date_of_birth", sa.DateTime(timezone=True), nullable=True, comment="User's date of birth"),
        sa.Column("gender", sa.String(length=20), nullable=True, comment="User's gender"),
        sa.Column("country_code", sa.String(length=3), nullable=True, comment="ISO country code (e.g., IN, US)"),
        sa.Column("timezone", sa.String(length=50), nullable=True, comment="User's timezone (e.g., Asia/Kolkata)"),
        sa.Column("language", sa.String(length=10), nullable=True, server_default="en", comment="Preferred language code"),
        
        # Account status
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true", comment="Account active status"),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false", comment="Soft delete flag"),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default="false", comment="Full account verification status"),
        sa.Column("is_premium", sa.Boolean(), nullable=False, server_default="false", comment="Premium subscription status"),
        
        # Cognito metadata
        sa.Column("cognito_username", sa.String(length=255), nullable=True, comment="Cognito username"),
        sa.Column("cognito_status", sa.String(length=50), nullable=True, comment="Cognito user status"),
        
        # Additional profile data
        sa.Column("profile_picture_url", sa.Text(), nullable=True, comment="Profile picture URL"),
        sa.Column("bio", sa.Text(), nullable=True, comment="User bio/description"),
        
        # Audit trail - Login tracking
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True, comment="Last login timestamp"),
        sa.Column("last_login_ip", sa.String(length=45), nullable=True, comment="Last login IP address (IPv4/IPv6)"),
        sa.Column("last_login_device", sa.String(length=255), nullable=True, comment="Last login device info"),
        sa.Column("last_login_location", sa.String(length=255), nullable=True, comment="Last login location (city, country)"),
        sa.Column("login_count", sa.Integer(), nullable=False, server_default="0", comment="Total number of logins"),
        
        # Audit trail - Account activity
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), comment="Account creation timestamp"),
        sa.Column("created_ip", sa.String(length=45), nullable=True, comment="IP address at account creation"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), comment="Last update timestamp"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True, comment="Account deletion timestamp"),
        
        # User preferences and settings (JSON columns)
        sa.Column("preferences", postgresql.JSON(astext_type=sa.Text()), nullable=True, comment="User preferences as JSON (notifications, theme, etc.)"),
        sa.Column("settings", postgresql.JSON(astext_type=sa.Text()), nullable=True, comment="User settings as JSON"),
        
        # Additional metadata
        sa.Column("user_metadata", postgresql.JSON(astext_type=sa.Text()), nullable=True, comment="Additional JSON metadata"),
        sa.Column("referral_code", sa.String(length=50), nullable=True, unique=True, comment="User's unique referral code"),
        sa.Column("referred_by", sa.String(length=255), nullable=True, comment="ID of user who referred this user"),
    )
    
    # Create indexes for frequently queried columns
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_phone_number", "users", ["phone_number"])
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_referral_code", "users", ["referral_code"])
    op.create_index("ix_users_is_active", "users", ["is_active"])
    op.create_index("ix_users_created_at", "users", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_users_created_at", table_name="users")
    op.drop_index("ix_users_is_active", table_name="users")
    op.drop_index("ix_users_referral_code", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_phone_number", table_name="users")
    op.drop_index("ix_users_id", table_name="users")
    op.drop_table("users")

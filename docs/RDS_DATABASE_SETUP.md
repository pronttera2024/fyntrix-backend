# RDS Database Setup & User Table Integration

Complete guide to connect your Fyntrix backend to AWS RDS PostgreSQL and integrate user creation with authentication.

---

## 🎯 Overview

Your application now has:
- ✅ **Enhanced User Model** with comprehensive audit fields
- ✅ **Database Integration** in auth endpoints (signup, login, phone auth)
- ✅ **Request Metadata Tracking** (IP, device, location, login count)
- ✅ **Alembic Migration** ready to create the users table

---

## 📋 Database Credentials

```
Host: fyntrix-db.crqq2weawp2p.ap-south-1.rds.amazonaws.com
Port: 5432
User: fintrixAdmin
Password: fintriX-2026
Database: postgres
```

**Connection String:**
```
postgresql://fintrixAdmin:fintriX-2026@fyntrix-db.crqq2weawp2p.ap-south-1.rds.amazonaws.com:5432/postgres
```

---

## 🚀 Setup Steps

### Step 1: Update Your .env File

Copy `.env.example` to `.env` and update the DATABASE_URL:

```bash
cp .env.example .env
```

Edit `.env` and ensure this line is present:
```bash
DATABASE_URL=postgresql://fintrixAdmin:fintriX-2026@fyntrix-db.crqq2weawp2p.ap-south-1.rds.amazonaws.com:5432/postgres
```

**For Render.com deployment**, add this as an environment variable in your Render dashboard.

---

### Step 2: Install Dependencies

Ensure you have all required packages:

```bash
pip install -r requirements.txt
```

Key dependencies needed:
- `sqlalchemy` - ORM for database operations
- `alembic` - Database migrations
- `psycopg2-binary` - PostgreSQL adapter
- `fastapi` - Web framework
- `boto3` - AWS Cognito integration

---

### Step 3: Test Database Connection

Test the connection before running migrations:

```bash
python3 -c "from app.config.database import get_database_config; config = get_database_config(); print('✅ Connected!' if config.test_connection() else '❌ Failed')"
```

**Expected output:**
```
INFO:app.config.database:Using PostgreSQL database
INFO:app.config.database:Database connection test successful
✅ Connected!
```

---

### Step 4: Run Database Migrations

Create the users table with all audit fields:

```bash
# Run the migration
alembic upgrade head
```

**Expected output:**
```
INFO  [alembic.runtime.migration] Running upgrade 0001_exec_trading_tables -> 0002_create_enhanced_users_table, Create enhanced users table with audit fields
```

---

### Step 5: Verify Table Creation

Connect to your database and verify the users table:

```bash
psql "postgresql://fintrixAdmin:fintriX-2026@fyntrix-db.crqq2weawp2p.ap-south-1.rds.amazonaws.com:5432/postgres"
```

Inside psql:
```sql
-- List all tables
\dt

-- Describe users table structure
\d users

-- Check if table is empty
SELECT COUNT(*) FROM users;

-- Exit
\q
```

---

## 📊 Users Table Schema

The enhanced users table includes:

### **Authentication Fields**
- `id` (Primary Key) - Cognito user sub (UUID)
- `phone_number` - E.164 format, unique, indexed
- `phone_number_verified` - Boolean
- `email` - Unique, indexed, optional
- `email_verified` - Boolean

### **Profile Information**
- `name` - Full name (required)
- `first_name`, `last_name` - Optional
- `date_of_birth` - DateTime
- `gender` - String
- `country_code` - ISO code (e.g., IN, US)
- `timezone` - e.g., Asia/Kolkata
- `language` - Default: "en"

### **Account Status**
- `is_active` - Active status (default: true)
- `is_deleted` - Soft delete flag (default: false)
- `is_verified` - Full verification status
- `is_premium` - Premium subscription flag

### **Audit Trail - Login Tracking**
- `last_login_at` - Timestamp
- `last_login_ip` - IPv4/IPv6 address
- `last_login_device` - Device type (Mobile/Desktop/Tablet)
- `last_login_location` - City, country
- `login_count` - Total logins (auto-incremented)

### **Audit Trail - Account Activity**
- `created_at` - Account creation timestamp
- `created_ip` - IP at signup
- `updated_at` - Last update timestamp
- `deleted_at` - Deletion timestamp (soft delete)

### **User Preferences & Settings**
- `preferences` - JSON (notifications, theme, etc.)
- `settings` - JSON (user settings)
- `metadata` - JSON (additional data)

### **Referral System**
- `referral_code` - Unique referral code
- `referred_by` - ID of referring user

### **Cognito Metadata**
- `cognito_username` - Cognito username
- `cognito_status` - Cognito user status

### **Additional Profile**
- `profile_picture_url` - Profile image URL
- `bio` - User bio/description

---

## 🔄 How User Creation Works

### **1. Email Signup Flow** (`/auth/signup`)

```python
# User signs up with email/password
POST /auth/signup
{
  "email": "user@example.com",
  "password": "SecurePass123!",
  "name": "John Doe"
}

# What happens:
1. Cognito creates user account
2. User record created in RDS database with:
   - Cognito sub as ID
   - Email, name, email_verified
   - IP address, device info
   - created_at, login_count = 1
3. Returns auth tokens
```

### **2. Email Login Flow** (`/auth/login`)

```python
# User logs in
POST /auth/login
{
  "email": "user@example.com",
  "password": "SecurePass123!"
}

# What happens:
1. Cognito authenticates user
2. Database record updated with:
   - last_login_at = now
   - last_login_ip = request IP
   - last_login_device = detected device
   - login_count += 1
3. Returns auth tokens
```

### **3. Phone Signup Flow** (`/auth/phone/signup`)

```python
# User signs up with phone
POST /auth/phone/signup
{
  "phone_number": "+919876543210",
  "name": "John Doe"
}

# What happens:
1. Cognito creates user, sends OTP
2. User record created in database
3. User verifies OTP via /auth/phone/verify-signup
4. Database updated with phone_number_verified = true
```

### **4. Phone Login Flow** (`/auth/phone/login`)

```python
# User initiates login
POST /auth/phone/login
{
  "phone_number": "+919876543210"
}

# User verifies OTP
POST /auth/phone/login/verify
{
  "phone_number": "+919876543210",
  "session": "session_token",
  "otp_code": "123456"
}

# What happens:
1. Cognito sends OTP
2. User verifies OTP
3. Database updated with login metadata
4. Returns auth tokens
```

---

## 🧪 Testing the Integration

### Test 1: Create a New User

```bash
curl -X POST http://localhost:8000/auth/signup \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "TestPass123!",
    "name": "Test User"
  }'
```

### Test 2: Verify User in Database

```sql
-- Connect to database
psql "postgresql://fintrixAdmin:fintriX-2026@fyntrix-db.crqq2weawp2p.ap-south-1.rds.amazonaws.com:5432/postgres"

-- Check user was created
SELECT 
  id, 
  name, 
  email, 
  email_verified,
  created_ip,
  last_login_ip,
  login_count,
  created_at
FROM users
ORDER BY created_at DESC
LIMIT 5;
```

### Test 3: Login and Check Audit Trail

```bash
# Login with the user
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "TestPass123!"
  }'
```

```sql
-- Check login count increased
SELECT 
  id, 
  name, 
  login_count,
  last_login_at,
  last_login_ip,
  last_login_device
FROM users
WHERE email = 'test@example.com';
```

---

## 🔧 Troubleshooting

### Issue: "relation 'users' does not exist"

**Solution:** Run migrations
```bash
alembic upgrade head
```

### Issue: "password authentication failed"

**Solution:** Verify credentials in .env match RDS settings
```bash
# Check current DATABASE_URL
echo $DATABASE_URL

# Or check in Python
python3 -c "import os; from dotenv import load_dotenv; load_dotenv(); print(os.getenv('DATABASE_URL'))"
```

### Issue: "could not connect to server"

**Solution:** Check RDS security group allows your IP
1. Go to AWS RDS Console
2. Select your database
3. Click on VPC security group
4. Add inbound rule for PostgreSQL (port 5432) from your IP

For Render.com, add Render's IP ranges to security group.

### Issue: "SSL connection required"

**Solution:** Add SSL mode to connection string
```bash
DATABASE_URL=postgresql://fintrixAdmin:fintriX-2026@fyntrix-db.crqq2weawp2p.ap-south-1.rds.amazonaws.com:5432/postgres?sslmode=require
```

---

## 🚀 Deployment to Render.com

### Step 1: Add Environment Variable

In Render dashboard:
1. Go to your service
2. Click "Environment"
3. Add new environment variable:
   - **Key:** `DATABASE_URL`
   - **Value:** `postgresql://fintrixAdmin:fintriX-2026@fyntrix-db.crqq2weawp2p.ap-south-1.rds.amazonaws.com:5432/postgres`

### Step 2: Run Migrations on Render

Add to your `render.yaml` or run manually:

```yaml
services:
  - type: web
    name: fyntrix-backend
    env: python
    buildCommand: "pip install -r requirements.txt && alembic upgrade head"
    startCommand: "uvicorn app.main:app --host 0.0.0.0 --port $PORT"
```

Or run manually via Render shell:
```bash
alembic upgrade head
```

---

## 📈 Monitoring & Analytics

### Useful Queries

**User Growth:**
```sql
SELECT 
  DATE(created_at) as signup_date,
  COUNT(*) as new_users
FROM users
WHERE is_deleted = false
GROUP BY DATE(created_at)
ORDER BY signup_date DESC
LIMIT 30;
```

**Active Users:**
```sql
SELECT COUNT(*) as active_users
FROM users
WHERE is_active = true 
  AND is_deleted = false;
```

**Login Activity:**
```sql
SELECT 
  name,
  email,
  login_count,
  last_login_at,
  last_login_device
FROM users
WHERE last_login_at > NOW() - INTERVAL '7 days'
ORDER BY last_login_at DESC;
```

**User Devices:**
```sql
SELECT 
  last_login_device,
  COUNT(*) as user_count
FROM users
WHERE last_login_device IS NOT NULL
GROUP BY last_login_device;
```

---

## 🔐 Security Best Practices

1. **Never commit .env file** - Already in .gitignore ✅
2. **Use strong passwords** - Current password meets requirements ✅
3. **Enable SSL connections** - Add `?sslmode=require` to DATABASE_URL
4. **Restrict RDS security group** - Only allow necessary IPs
5. **Regular backups** - Enable automated backups in RDS
6. **Monitor failed login attempts** - Track in application logs
7. **Rotate credentials** - Change RDS password periodically

---

## 📚 Next Steps

1. ✅ Database connected to RDS
2. ✅ Users table created with audit fields
3. ✅ Auth endpoints integrated with database
4. ✅ Request metadata tracking enabled
5. 🔄 Deploy to Render.com
6. 🔄 Configure RDS security group for Render IPs
7. 🔄 Test production signup/login flow
8. 🔄 Set up monitoring and alerts
9. 🔄 Implement user profile endpoints
10. 🔄 Add user analytics dashboard

---

## 🆘 Support

If you encounter issues:

1. Check application logs: `tail -f logs/app.log`
2. Check database connection: Run test command from Step 3
3. Verify migrations: `alembic current`
4. Check RDS status in AWS Console
5. Review security group rules

---

## 📝 Summary

Your Fyntrix backend now has:

- **Complete user management** with RDS PostgreSQL
- **Comprehensive audit trail** tracking all user activity
- **Automatic user creation** on signup and login
- **Request metadata capture** (IP, device, location)
- **Production-ready database schema** with proper indexes
- **Scalable architecture** ready for growth

All authentication endpoints now automatically create and update user records in your RDS database! 🎉

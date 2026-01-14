# AWS RDS PostgreSQL Setup Guide

Complete guide to set up AWS RDS PostgreSQL database for Fyntrix backend with user authentication.

---

## Overview

This guide covers:
1. Creating an AWS RDS PostgreSQL instance
2. Configuring security groups and network access
3. Connecting your application to RDS
4. Running database migrations
5. Best practices for production

---

## Step 1: Create RDS PostgreSQL Instance

### 1.1 Go to RDS Console
- Open **AWS Console** → **RDS** → **Databases**
- Click **Create database**

### 1.2 Choose Database Creation Method
- Select **Standard create** (for full control)

### 1.3 Engine Options
- **Engine type**: PostgreSQL
- **Version**: PostgreSQL 15.x or latest (recommended)

### 1.4 Templates
- **Production**: For production workloads (Multi-AZ, automated backups)
- **Dev/Test**: For development (Single-AZ, lower cost)
- **Free tier**: For testing (limited to db.t3.micro, 20GB storage)

**Recommendation**: Start with **Free tier** or **Dev/Test** for initial setup

### 1.5 Settings
- **DB instance identifier**: `fyntrix-db` (or your preferred name)
- **Master username**: `fyntrix_admin`
- **Master password**: Create a strong password (save it securely!)
- **Confirm password**: Re-enter password

**Important**: Save these credentials - you'll need them for DATABASE_URL

### 1.6 Instance Configuration
- **DB instance class**: 
  - Free tier: `db.t3.micro` (1 vCPU, 1 GB RAM)
  - Dev/Test: `db.t3.small` (2 vCPU, 2 GB RAM)
  - Production: `db.t3.medium` or higher

### 1.7 Storage
- **Storage type**: General Purpose SSD (gp3) - recommended
- **Allocated storage**: 20 GB (minimum for free tier)
- **Storage autoscaling**: Enable (max 100 GB for free tier)

### 1.8 Availability & Durability
- **Multi-AZ deployment**: 
  - Production: Enable (for high availability)
  - Dev/Test: Disable (to save costs)

### 1.9 Connectivity
- **Compute resource**: Don't connect to an EC2 compute resource
- **VPC**: Default VPC (or your custom VPC)
- **Subnet group**: default
- **Public access**: **Yes** (for development - allows connection from your local machine)
  - **Production**: Consider using VPN or bastion host instead
- **VPC security group**: Create new
  - **Name**: `fyntrix-db-sg`
- **Availability Zone**: No preference

### 1.10 Database Authentication
- **Database authentication**: Password authentication

### 1.11 Additional Configuration
- **Initial database name**: `fyntrix_db`
- **DB parameter group**: default.postgres15
- **Backup**:
  - Retention period: 7 days (free tier allows up to 7 days)
  - Backup window: No preference
- **Encryption**: Enable encryption at rest (recommended)
- **Performance Insights**: Disable (to save costs) or Enable for 7 days free
- **Monitoring**: Enable Enhanced monitoring (optional)
- **Maintenance**:
  - Auto minor version upgrade: Enable
  - Maintenance window: No preference

### 1.12 Create Database
- Review all settings
- Click **Create database**
- Wait 5-10 minutes for database to be created

---

## Step 2: Configure Security Group

### 2.1 Find Your Security Group
- Go to **RDS** → **Databases** → Select your database
- Under **Connectivity & security**, click on the VPC security group

### 2.2 Edit Inbound Rules
- Click **Edit inbound rules**
- Click **Add rule**

**For Development (Local Access)**:
- **Type**: PostgreSQL
- **Protocol**: TCP
- **Port**: 5432
- **Source**: My IP (your current IP address)
- **Description**: Local development access

**For Production (Application Access)**:
- **Type**: PostgreSQL
- **Protocol**: TCP
- **Port**: 5432
- **Source**: Security group of your EC2/ECS/Lambda (or VPC CIDR)
- **Description**: Application access

### 2.3 Save Rules
- Click **Save rules**

**Security Note**: Never use `0.0.0.0/0` (anywhere) for production databases!

---

## Step 3: Get Database Connection Details

### 3.1 Find Endpoint
- Go to **RDS** → **Databases** → Select your database
- Under **Connectivity & security**, find:
  - **Endpoint**: `fyntrix-db.xxxxxxxxxxxxx.us-east-1.rds.amazonaws.com`
  - **Port**: `5432`

### 3.2 Construct DATABASE_URL

Format:
```
postgresql://username:password@endpoint:port/database_name
```

Example:
```
postgresql://fyntrix_admin:YourPassword123@fyntrix-db.c9akqwerty.us-east-1.rds.amazonaws.com:5432/fyntrix_db
```

**Important**: Replace with your actual values!

---

## Step 4: Update .env File

Add the DATABASE_URL to your `.env` file:

```bash
# Database Configuration
DATABASE_URL=postgresql://fyntrix_admin:YourPassword123@fyntrix-db.xxxxx.us-east-1.rds.amazonaws.com:5432/fyntrix_db

# SQL Query Logging (optional - for debugging)
SQL_ECHO=false
```

**Never commit .env file to git!** (Already in .gitignore)

---

## Step 5: Test Database Connection

### 5.1 Install PostgreSQL Client (Optional)
```bash
# macOS
brew install postgresql

# Ubuntu/Debian
sudo apt-get install postgresql-client

# Windows
# Download from https://www.postgresql.org/download/windows/
```

### 5.2 Test Connection
```bash
psql "postgresql://fyntrix_admin:YourPassword123@fyntrix-db.xxxxx.us-east-1.rds.amazonaws.com:5432/fyntrix_db"
```

If successful, you'll see:
```
psql (15.x)
SSL connection (protocol: TLSv1.3, cipher: TLS_AES_256_GCM_SHA384, bits: 256, compression: off)
Type "help" for help.

fyntrix_db=>
```

Type `\q` to exit.

---

## Step 6: Run Database Migrations

### 6.1 Create Initial Migration
```bash
# Navigate to project directory
cd /Users/adeeb/Documents/Pronttera/Fyntrix/fyntix-backend

# Create migration for User table
alembic revision --autogenerate -m "Create users table"
```

This will create a new migration file in `migrations/versions/`

### 6.2 Review Migration
Open the generated migration file and verify it creates the users table correctly.

### 6.3 Apply Migration
```bash
# Run migrations
alembic upgrade head
```

You should see:
```
INFO  [alembic.runtime.migration] Running upgrade -> xxxxx, Create users table
```

### 6.4 Verify Tables Created
```bash
# Connect to database
psql "postgresql://fyntrix_admin:YourPassword@endpoint:5432/fyntrix_db"

# List tables
\dt

# Should show:
#  Schema |      Name       | Type  |     Owner      
# --------+-----------------+-------+----------------
#  public | alembic_version | table | fyntrix_admin
#  public | users           | table | fyntrix_admin

# Describe users table
\d users

# Exit
\q
```

---

## Step 7: Update Application Code

### 7.1 Update main.py to Initialize Database

Add database initialization to your FastAPI app:

```python
# In app/main.py
from .config.database import init_database

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logging.getLogger(__name__).info("Starting application...")
    
    # Initialize database
    try:
        init_database()
        logging.getLogger(__name__).info("Database initialized successfully")
    except Exception as e:
        logging.getLogger(__name__).error(f"Database initialization failed: {e}")
    
    # ... rest of startup code
    
    yield
    
    # Shutdown
    # ... shutdown code
```

### 7.2 Update Auth Router to Save Users

Modify the phone login verify endpoint to save users to database:

```python
# In app/routers/auth.py
from sqlalchemy.orm import Session
from ..config.database import get_db
from ..services.user_service import UserService

@router.post("/phone/login/verify")
async def phone_login_verify(
    request: PhoneLoginVerifyRequest,
    cognito: CognitoAuthService = Depends(get_cognito_service),
    db: Session = Depends(get_db)
):
    # Verify OTP and get tokens
    result = cognito.phone_login_verify(
        phone_number=request.phone_number,
        session=request.session,
        otp_code=request.otp_code
    )
    
    # Get user info from Cognito
    user_info = cognito.get_user_info(access_token=result['access_token'])
    
    # Create or update user in database
    user = UserService.create_user_from_cognito(db, user_info)
    
    return AuthResponse(
        access_token=result['access_token'],
        id_token=result['id_token'],
        refresh_token=result['refresh_token'],
        expires_in=result['expires_in'],
        token_type=result['token_type']
    )
```

---

## Step 8: Test Complete Flow

### 8.1 Start Application
```bash
python3 -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 8.2 Test Signup
```bash
curl -X POST http://localhost:8000/auth/phone/signup \
  -H "Content-Type: application/json" \
  -d '{
    "phone_number": "+919876543210",
    "name": "Test User"
  }'
```

### 8.3 Verify User in Database
```bash
psql "postgresql://fyntrix_admin:YourPassword@endpoint:5432/fyntrix_db"

SELECT * FROM users;
```

You should see the user record!

---

## Production Best Practices

### 1. Security
- ✅ Use strong passwords (min 16 characters, mixed case, numbers, symbols)
- ✅ Enable encryption at rest
- ✅ Enable encryption in transit (SSL/TLS)
- ✅ Use IAM database authentication (advanced)
- ✅ Restrict security group to only application servers
- ✅ Never expose RDS publicly in production
- ✅ Use AWS Secrets Manager for credentials
- ✅ Enable deletion protection

### 2. Backups
- ✅ Enable automated backups (7-35 days retention)
- ✅ Take manual snapshots before major changes
- ✅ Test backup restoration regularly
- ✅ Enable point-in-time recovery

### 3. Monitoring
- ✅ Enable Enhanced Monitoring
- ✅ Set up CloudWatch alarms for:
  - CPU utilization > 80%
  - Free storage < 10%
  - Database connections > 80% of max
  - Read/Write latency spikes
- ✅ Enable Performance Insights
- ✅ Monitor slow query logs

### 4. Performance
- ✅ Use connection pooling (already configured in database.py)
- ✅ Create indexes on frequently queried columns
- ✅ Monitor and optimize slow queries
- ✅ Use read replicas for read-heavy workloads
- ✅ Enable query caching where appropriate

### 5. Cost Optimization
- ✅ Right-size your instance (start small, scale up)
- ✅ Use Reserved Instances for production (up to 60% savings)
- ✅ Delete old snapshots
- ✅ Use gp3 storage instead of gp2 (better price/performance)
- ✅ Monitor and optimize storage usage

---

## Troubleshooting

### Issue: Cannot connect to database
**Solution**:
- Check security group allows your IP on port 5432
- Verify endpoint and port are correct
- Ensure database is in "Available" state
- Check VPC and subnet configuration

### Issue: "password authentication failed"
**Solution**:
- Verify username and password are correct
- Check for special characters in password (may need URL encoding)
- Ensure you're using master username, not database name

### Issue: "SSL connection required"
**Solution**:
Add `?sslmode=require` to DATABASE_URL:
```
postgresql://user:pass@endpoint:5432/db?sslmode=require
```

### Issue: "too many connections"
**Solution**:
- Reduce pool_size in database.py
- Check for connection leaks (always close sessions)
- Upgrade to larger instance class

### Issue: Migration fails
**Solution**:
- Check DATABASE_URL is correct in .env
- Verify database exists
- Check alembic.ini configuration
- Review migration file for errors

---

## Cost Estimate

### Free Tier (First 12 Months)
- **Instance**: db.t3.micro - Free
- **Storage**: 20 GB - Free
- **Backups**: 20 GB - Free
- **Total**: $0/month

### After Free Tier (Dev/Test)
- **Instance**: db.t3.small - ~$25/month
- **Storage**: 20 GB gp3 - ~$2.50/month
- **Backups**: 20 GB - ~$2/month
- **Total**: ~$30/month

### Production (Recommended)
- **Instance**: db.t3.medium (Multi-AZ) - ~$120/month
- **Storage**: 100 GB gp3 - ~$12/month
- **Backups**: 100 GB - ~$10/month
- **Total**: ~$142/month

**Note**: Prices vary by region and are subject to change.

---

## Useful Commands

### Database Operations
```bash
# Connect to database
psql "postgresql://user:pass@endpoint:5432/dbname"

# List databases
\l

# List tables
\dt

# Describe table
\d table_name

# Run SQL query
SELECT * FROM users LIMIT 10;

# Exit
\q
```

### Alembic Migrations
```bash
# Create new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Show current version
alembic current

# Show migration history
alembic history
```

### Application Commands
```bash
# Start server
python3 -m uvicorn app.main:app --reload

# Run with specific .env file
python3 -m uvicorn app.main:app --reload --env-file .env.production

# Check database connection
python3 -c "from app.config.database import get_database_config; get_database_config().test_connection()"
```

---

## Next Steps

1. ✅ Set up AWS RDS PostgreSQL instance
2. ✅ Configure security groups
3. ✅ Update .env with DATABASE_URL
4. ✅ Run database migrations
5. ✅ Test user registration and login
6. ✅ Set up CloudWatch monitoring
7. ✅ Configure automated backups
8. ✅ Implement connection pooling (already done)
9. ✅ Add database indexes for performance
10. ✅ Set up staging environment

---

## Support Resources

- [AWS RDS Documentation](https://docs.aws.amazon.com/rds/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)

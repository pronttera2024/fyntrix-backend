# Fyntrix Backend - Render Deployment Guide

## 🚀 Quick Deploy to Render

### Prerequisites
- GitHub account with this repository
- Render account (free tier available)
- API keys for:
  - OpenAI (required)
  - Finnhub or Alpha Vantage (at least one required)

---

## Step 1: Prepare Your Repository

Ensure these files are in your repository:
- ✅ `Dockerfile` (production-ready)
- ✅ `requirements.txt` (Python dependencies)
- ✅ `requirements_phase2.txt` (additional dependencies)
- ✅ `.dockerignore` (excludes unnecessary files)
- ✅ `render.yaml` (optional - for automatic configuration)

---

## Step 2: Deploy on Render

### Option A: Using Render Dashboard (Recommended)

1. **Go to Render Dashboard**
   - Visit https://dashboard.render.com/
   - Click "New +" → "Web Service"

2. **Connect Repository**
   - Connect your GitHub/GitLab account
   - Select this repository: `llq_fyntrix`

3. **Configure Service**
   ```
   Name: fyntrix-backend
   Region: Oregon (US West)
   Branch: main (or your default branch)
   Root Directory: backend
   Environment: Docker
   Plan: Starter ($7/month) or Free
   ```

4. **Add Environment Variables**
   Click "Advanced" → "Add Environment Variable":
   
   **Required:**
   ```bash
   OPENAI_API_KEY=sk-proj-xxxxx
   OPENAI_DAILY_BUDGET=10.0
   OPENAI_MAX_RPM=60
   
   # At least one market data API:
   FINNHUB_API_KEY=your_finnhub_key
   ALPHA_VANTAGE_API_KEY=your_alpha_vantage_key
   
   # Application settings:
   DEBUG=False
   LOG_LEVEL=INFO
   PYTHONUNBUFFERED=1
   ```
   
   **Optional:**
   ```bash
   ANTHROPIC_API_KEY=your_anthropic_key
   MASSIVE_API_KEY=your_massive_key
   ```

5. **Deploy**
   - Click "Create Web Service"
   - Render will automatically build and deploy your Docker container
   - Wait 5-10 minutes for first deployment

### Option B: Using render.yaml (Infrastructure as Code)

1. Push `render.yaml` to your repository
2. In Render Dashboard:
   - Click "New +" → "Blueprint"
   - Select your repository
   - Render will auto-detect `render.yaml`
3. Add secret environment variables in the dashboard
4. Click "Apply"

---

## Step 3: Verify Deployment

Once deployed, your service will be available at:
```
https://fyntrix-backend.onrender.com
```

### Test Endpoints:

**Health Check:**
```bash
curl https://fyntrix-backend.onrender.com/health
# Expected: {"ok": true}
```

**API Documentation:**
```
https://fyntrix-backend.onrender.com/docs
```

---

## Step 4: Configure Frontend

Update your frontend `.env` file:

```bash
# /frontend/.env
VITE_API_BASE_URL=https://fyntrix-backend.onrender.com
```

Then rebuild and redeploy your frontend.

---

## 🔧 Dockerfile Explanation

```dockerfile
# Python 3.11 slim image (smaller size)
FROM python:3.11-slim

# Prevent Python from writing .pyc files and buffering stdout/stderr
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install system dependencies (gcc for some Python packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libpq-dev

# Install Python dependencies (cached layer)
COPY requirements.txt requirements_phase2.txt ./
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r requirements_phase2.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/data /app/cache /app/.cache /app/migrations

# Expose port (Render provides PORT env variable)
EXPOSE 8000

# Run with uvicorn (production ASGI server)
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
```

---

## 📊 Monitoring & Logs

### View Logs:
1. Go to your service in Render Dashboard
2. Click "Logs" tab
3. Monitor real-time application logs

### Metrics:
- CPU usage
- Memory usage
- Request count
- Response times

All available in the "Metrics" tab.

---

## 🔄 Auto-Deploy on Git Push

Render automatically deploys when you push to your connected branch:

```bash
git add .
git commit -m "Update backend"
git push origin main
```

Render will:
1. Detect the push
2. Rebuild the Docker image
3. Deploy the new version
4. Zero-downtime deployment

---

## 💰 Pricing

**Free Tier:**
- 750 hours/month
- Spins down after 15 minutes of inactivity
- Cold start delay (~30 seconds)

**Starter Plan ($7/month):**
- Always on
- No cold starts
- 512MB RAM
- Recommended for production

**Standard Plan ($25/month):**
- 2GB RAM
- Better performance
- Ideal for high traffic

---

## 🐛 Troubleshooting

### Build Fails:
```bash
# Check requirements.txt for version conflicts
# Ensure all dependencies are compatible with Python 3.11
```

### Health Check Fails:
```bash
# Verify /health endpoint exists in app/main.py
# Check logs for startup errors
```

### Out of Memory:
```bash
# Upgrade to Starter or Standard plan
# Optimize memory usage in code
# Reduce concurrent workers
```

### Environment Variables Not Loading:
```bash
# Ensure variables are set in Render Dashboard
# Check for typos in variable names
# Restart service after adding variables
```

---

## 🔐 Security Best Practices

1. **Never commit `.env` files** (already in `.gitignore`)
2. **Use Render's secret environment variables** for API keys
3. **Enable HTTPS** (automatic on Render)
4. **Rotate API keys regularly**
5. **Monitor usage and logs** for suspicious activity

---

## 📚 Additional Resources

- [Render Documentation](https://render.com/docs)
- [FastAPI Deployment Guide](https://fastapi.tiangolo.com/deployment/)
- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)

---

## ✅ Deployment Checklist

- [ ] Repository pushed to GitHub/GitLab
- [ ] `Dockerfile` configured correctly
- [ ] All dependencies in `requirements.txt`
- [ ] `.dockerignore` excludes unnecessary files
- [ ] Environment variables prepared
- [ ] Render service created
- [ ] Environment variables added to Render
- [ ] Service deployed successfully
- [ ] Health check passing
- [ ] API documentation accessible
- [ ] Frontend configured with backend URL
- [ ] Monitoring and alerts set up

---

## 🎉 Success!

Your Fyntrix backend is now running on Render with:
- ✅ Production-ready Docker container
- ✅ Automatic deployments on git push
- ✅ Health checks and monitoring
- ✅ Secure environment variable management
- ✅ Scalable infrastructure

**Live URL:** `https://fyntrix-backend.onrender.com`

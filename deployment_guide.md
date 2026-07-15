# Ads Analytics Tool - Railway Deployment Guide

This guide describes how to deploy the Ads Analytics Tool on [Railway](https://railway.app) connected to a PostgreSQL database.

---

## Deployment Architecture

The deployment consists of:
1. **App Service (Worker)**: Running our containerized background daemon (`scheduler.py`) which runs the daily sync.
2. **PostgreSQL Database Service**: Automatically provisioned by Railway. The database credentials and connection string (`DATABASE_URL`) are automatically linked and injected into the App Service.
3. **Database Migrations on Startup**: The `start.sh` script executes `alembic upgrade head` to automatically set up tables, views, and indexes before starting the scheduler.

---

## Method 1: Deploying via GitHub (Recommended)

### Step 1: Push Code to GitHub
Initialize git and push the project files to a new GitHub repository:
```bash
git init
git add .
git commit -m "Initial commit for Railway deployment"
# Create a repository on GitHub and link it
git remote add origin <your-github-repo-url>
git branch -M main
git push -u origin main
```

### Step 2: Create a Railway Project
1. Log in to your [Railway Dashboard](https://railway.app).
2. Click **New Project** in the upper right.
3. Select **Deploy from GitHub repo** and connect your repository.

### Step 3: Add PostgreSQL Database
1. Inside your Railway project canvas, click **+ New** (or **Add Service**).
2. Select **Database** -> **Add PostgreSQL**.
3. Railway will provision the Postgres database. Once created, it automatically injects a `DATABASE_URL` environment variable into your project scope.

### Step 4: Configure App Variables
In the **App Service** settings under the **Variables** tab, add your external credentials:
- `GEMINI_API_KEY`: (Optional) Your Google Gemini API Key.
- `META_ACCESS_TOKEN`: (Optional) Your Meta Graph API Access Token.
- `DEVELOPER_TOKEN`: (Optional) Your Google Ads developer token.
- `DATABASE_URL`: Automatically linked by Railway (points to your Postgres database instance).

### Step 5: Deploy
Railway will automatically build the `Dockerfile`, run the `start.sh` entrypoint (migrating the database schema and views), and launch the `scheduler.py` daemon. You can watch the build logs and application logs in the Railway Dashboard.

---

## Method 2: Deploying via Railway CLI

If you have the Railway CLI installed, you can deploy directly from your local terminal:

### Step 1: Install and Login
```bash
npm install -g @railway/cli
railway login
```

### Step 2: Initialize Project
Inside your project directory:
```bash
railway init
```
Follow the prompts to name your project.

### Step 3: Add PostgreSQL
```bash
railway add
```
Select **PostgreSQL** from the options.

### Step 4: Deploy and Set Variables
Set your API keys:
```bash
railway variables set GEMINI_API_KEY="your-gemini-key"
railway variables set META_ACCESS_TOKEN="your-meta-token"
```
Deploy the service:
```bash
railway up
```

---

## Monitoring and Logs

You can monitor the deployment directly from the dashboard:
- **Build Logs**: View the docker container building process.
- **Deploy Logs**: View the live standard output showing database migrations applying and scheduler daemon executing the daily sync:
  ```
  === DATABASE MIGRATION ===
  Running Alembic database migrations...
  INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
  INFO  [alembic.runtime.migration] Will assume transactional DDL.
  INFO  [alembic.runtime.migration] Running upgrade -> 3a72552c6152, Initial schema
  INFO  [alembic.runtime.migration] Running upgrade 3a72552c6152 -> afed2a44586f, Add analysis views
  INFO  [alembic.runtime.migration] Running upgrade afed2a44586f -> 2a4da60c9a8e, Add proposals table
  Database migrations successfully applied.

  === SCHEDULER DAEMON ===
  Starting scheduled daily sync daemon...
  2026-07-15 15:00:00,000 [INFO] scheduler_daemon: Triggering scheduled sync job...
  ```

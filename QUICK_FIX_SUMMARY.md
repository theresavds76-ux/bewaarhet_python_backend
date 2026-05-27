# QUICK FIX SUMMARY - Bewaarhet Activation Token Issue

## The Problem (Why status=400)

```
Production logs:
- activation failed | error=RuntimeError
- activation request | status=400
```

**Root Cause:** `VERIFICATION_TOKEN_SECRET` environment variable is **NOT SET** on your VPS.

When missing:
1. Token generation in worker tries to use this secret
2. Falls back to `DROPBOX_APP_SECRET` or other secrets
3. Falls back logic fails → `RuntimeError: No token secret configured`
4. Activation server catches this → returns status=400

Result: **All activation links fail immediately** with "invalid or expired" error.

---

## The Fix (What You Need to Do)

### On Your VPS:

**EXACTLY WHAT ENV VAR TO SET:**

```env
VERIFICATION_TOKEN_SECRET=<your-secure-random-value>
VERIFICATION_TOKEN_TTL_HOURS=72
```

### How to get the secure value:

```bash
# SSH to your VPS and run this command
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# This outputs something like:
# AbCdEfGhIjKlMnOpQrStUvWxYz1234567890
```

### Where to put it:

**File:** `/opt/bewaarhet/.env`

**Location in file:** After the Dropbox section, before OCR section

```env
# Dropbox
DROPBOX_APP_KEY=zcxi5ny3jufu8u4
DROPBOX_APP_SECRET=7iif54cwrz6nuhj
DROPBOX_REFRESH_TOKEN=km6yAcOKMtEAAAAAAAAAAQYeLEg6_0uSkwcqNvF3n8t8zFtRIssmF4NAnw2A7f2-
DROPBOX_BASE_PATH=/Bewaar het/Klanten

# ← ADD THESE TWO LINES HERE ↓
VERIFICATION_TOKEN_SECRET=<paste-your-generated-secret-here>
VERIFICATION_TOKEN_TTL_HOURS=72

# OCR.space
OCR_SPACE_API_KEY=K83580702388957
```

### Deploy:

```bash
# 1. Edit .env on VPS
ssh user@your-vps
sudo nano /opt/bewaarhet/.env
# Add the two lines above, save

# 2. Restart containers
cd /opt/bewaarhet
sudo docker-compose -f docker-compose.production.yml restart bewaarhet_activation bewaarhet_worker

# 3. Verify (wait 10 seconds first)
sleep 10
sudo docker logs bewaarhet_activation --tail 20 | grep -E "RuntimeError|Activation server started"
```

---

## Why This Works

✓ **Token Generation (worker):**
- Uses `VERIFICATION_TOKEN_SECRET` to sign activation tokens with HMAC-SHA256
- Token format: `<base64_payload>.<base64_signature>`

✓ **Token Validation (activation server):**
- Uses same `VERIFICATION_TOKEN_SECRET` to verify signature
- If secret matches → validates email, checks expiry, activates customer
- If secret missing → RuntimeError → status=400

✓ **Both containers load same `.env`:**
- `docker-compose.production.yml` mounts: `${BEWAARHET_ENV_FILE:-/opt/bewaarhet/.env}`
- Both `bewaarhet_worker` and `bewaarhet_activation` share the same env file
- So they'll both have the same secret = tokens work

---

## Verification Checklist

After deploying, verify:

```bash
# ✓ No RuntimeError in activation logs
sudo docker logs bewaarhet_activation | grep RuntimeError
# (should output nothing)

# ✓ Activation server started successfully
sudo docker logs bewaarhet_activation | grep "Activation server started"
# (should show the startup message)

# ✓ Environment variable is set
sudo docker exec bewaarhet_activation env | grep VERIFICATION_TOKEN_SECRET
# (should show: VERIFICATION_TOKEN_SECRET=<your-secret>)

# ✓ Test endpoint
curl -i "https://bewaarhet.nl/activeer?token=invalid-test"
# Should return: 400 Bad Request (NOT 500 Internal Server Error)
```

---

## What Changed (Code Patches)

### 1. customer_onboarding.py
**Before:** Unclear error when secret missing  
**After:** Clear error message explaining what's wrong

### 2. activation_server.py
**Before:** Generic `RuntimeError` logging  
**After:** Distinguishes between RuntimeError (config) vs ValueError (token issue)

### 3. .env.production
**Before:** No `VERIFICATION_TOKEN_SECRET` mentioned  
**After:** Added with clear instructions

### 4. DEPLOYMENT_RUNBOOK.md
**Before:** No explicit mention of token secret requirement  
**After:** Full section on how to generate and set it

### 5. New Files
- `ACTIVATION_TOKEN_FIX.md` - Detailed technical explanation
- `setup_token_secret.py` - Automated setup helper
- `VPS_DEPLOYMENT_CHECKLIST.md` - Step-by-step deployment guide
- `QUICK_FIX_SUMMARY.md` - This file

---

## Important Notes

⚠️ **Don't:**
- Commit `.env` to git (already in .gitignore)
- Share `VERIFICATION_TOKEN_SECRET` value
- Use same secret across multiple services
- Change the secret frequently (invalidates existing tokens)

✓ **Do:**
- Keep it the same on all production containers
- Store it safely (password manager, vault)
- Rotate only when necessary (users lose old activation links)
- Use the same value for both `bewaarhet_worker` AND `bewaarhet_activation`

---

## Rollback (If Needed)

```bash
# If this breaks things, restore backup
sudo cp /opt/bewaarhet/.env.backup-* /opt/bewaarhet/.env
sudo docker-compose -f docker-compose.production.yml restart bewaarhet_activation bewaarhet_worker
```

---

## Files You Need to Deploy

1. **Code patches** (auto-deployed with git pull):
   - `bewaarhet/customer_onboarding.py` ✓
   - `bewaarhet/activation_server.py` ✓
   - `.env.production` ✓
   - `DEPLOYMENT_RUNBOOK.md` ✓

2. **New documentation** (for reference):
   - `ACTIVATION_TOKEN_FIX.md` (technical details)
   - `VPS_DEPLOYMENT_CHECKLIST.md` (step-by-step)
   - `setup_token_secret.py` (helper script)
   - `QUICK_FIX_SUMMARY.md` (this file)

3. **VPS-only** (you set this, NOT in git):
   - `VERIFICATION_TOKEN_SECRET` env var in `/opt/bewaarhet/.env`

---

## The Exact Command You Need

```bash
# 1. Generate the secret value
python3 -c "import secrets; echo=$(secrets.token_urlsafe(32)); echo \"Add to .env:\" ; echo \"VERIFICATION_TOKEN_SECRET=$echo\" ; echo \"VERIFICATION_TOKEN_TTL_HOURS=72\""

# 2. SSH to VPS and edit the .env file manually OR use the automated script
ssh user@your-vps
cd /opt/bewaarhet
python3 setup_token_secret.py

# 3. Restart
sudo docker-compose -f docker-compose.production.yml restart bewaarhet_activation bewaarhet_worker

# Done! ✓
```

---

**Status:** ✓ READY TO DEPLOY  
**Date:** 2026-05-27  
**Patch Complexity:** LOW (config only, no business logic changes)  
**Breaking Changes:** NONE

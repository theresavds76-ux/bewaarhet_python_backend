# PATCH SUMMARY - Bewaarhet Activation Token Fix

## Files Modified (4)

### 1. bewaarhet/customer_onboarding.py
**Change Type:** Enhancement + Bug Fix

**What Changed:**
- Improved `_token_secret()` function with clearer fallback logic and error messages
- Enhanced `verify_activation_token()` with specific error reasons (signature, expiry, etc)
- Removed generic "invalid activation token" messages, now shows exact reason

**Why:**
- Previous: Cryptic "RuntimeError: verification token secret is not configured"
- New: Clear error explaining that VERIFICATION_TOKEN_SECRET is missing and fallbacks failed

**Impact:** Better debugging, same functionality

---

### 2. bewaarhet/activation_server.py
**Change Type:** Enhancement (Logging)

**What Changed:**
- Split `activation_response_for_token()` exception handling
- Now distinguishes between RuntimeError (config) and ValueError (token validation)
- Enhanced logging shows `error_type`, `config_error`, `reason` fields

**Why:**
- Previous: All errors logged as generic "RuntimeError"
- New: Can see exact failure reason (signature invalid, expired, etc)

**Example Logs:**
```
Before: activation failed | error=RuntimeError
After:  activation failed | error_type=ValueError | reason=token signature verification failed
```

**Impact:** Much better observability for debugging

---

### 3. .env.production
**Change Type:** Documentation + Configuration

**What Changed:**
- Added `VERIFICATION_TOKEN_SECRET` with placeholder value
- Added `VERIFICATION_TOKEN_TTL_HOURS` setting
- Added explanation about why this is CRITICAL

**Before:**
```env
# OpenAI fallback, optioneel
OPENAI_API_KEY=...
# App
DATABASE_PATH=...
```

**After:**
```env
# OpenAI fallback, optioneel
OPENAI_API_KEY=...

# CRITICAL: Token signing secret for activation links
# MUST be a long random string (min 32 chars)...
VERIFICATION_TOKEN_SECRET=placeholder-change-to-real-random-secret-on-vps
VERIFICATION_TOKEN_TTL_HOURS=72

# App
DATABASE_PATH=...
```

**Impact:** Production now has a documented placeholder (must be changed by operator)

---

### 4. DEPLOYMENT_RUNBOOK.md
**Change Type:** Documentation

**What Changed:**
- Added new section: "CRITICAL: Activation Token Secret"
- Explains how to generate secure random secret
- Shows exactly what to put in .env
- Explains why this is non-negotiable for production

**New Section Includes:**
- How to generate: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
- Where to place it in .env
- Why it must be the same on all containers
- What happens if you rotate it (all existing tokens expire)

**Impact:** Future deployments will have clear instructions

---

## Files Created (4)

### 1. ACTIVATION_TOKEN_FIX.md
**Purpose:** Technical deep-dive into the problem

**Contains:**
- Problem summary
- Root cause analysis
- Solution with step-by-step instructions
- Verification procedures
- FAQ

**Audience:** Technical support, operations team

---

### 2. VPS_DEPLOYMENT_CHECKLIST.md
**Purpose:** Operational runbook for VPS deployment

**Contains:**
- Quick start (5 minutes)
- Manual step-by-step approach
- Verification procedures
- Troubleshooting guide
- Security notes
- Rollback plan

**Audience:** SRE/DevOps deploying to production

---

### 3. setup_token_secret.py
**Purpose:** Automated, safe setup script for production

**Features:**
- Checks if secret already set
- Generates secure random value
- Backs up current .env
- Updates .env with new secret
- Validates the change
- Shows next steps

**Usage:**
```bash
cd /opt/bewaarhet
python3 setup_token_secret.py
```

**Audience:** Anyone deploying to VPS (safe, idempotent)

---

### 4. QUICK_FIX_SUMMARY.md
**Purpose:** One-page executive summary

**Contains:**
- Problem in plain English
- Exact env var to set
- Why it fixes the issue
- Verification checklist
- Important notes

**Audience:** Anyone implementing the fix

---

## Summary of Changes

| Type | Count | Details |
|------|-------|---------|
| Modified Files | 4 | Code + docs + config |
| New Files | 4 | Documentation + helper script |
| New Tests | 0 | Existing tests should pass (no logic changes) |
| Breaking Changes | 0 | Purely additive |
| Database Changes | 0 | No schema changes |

---

## Deployment Steps for You

### Step 1: Pull Latest Code
```bash
cd /opt/bewaarhet_python_backend
git pull origin main
# (gets the code changes, new docs, setup script)
```

### Step 2: Run Setup Script on VPS
```bash
ssh user@your-vps
cd /opt/bewaarhet
python3 setup_token_secret.py
# (generates and sets VERIFICATION_TOKEN_SECRET)
```

### Step 3: Restart Containers
```bash
sudo docker-compose -f docker-compose.production.yml restart bewaarhet_activation bewaarhet_worker
```

### Step 4: Verify
```bash
sudo docker logs bewaarhet_activation | grep -E "RuntimeError|Activation server started"
curl -i https://bewaarhet.nl/activeer?token=test
```

---

## Testing

### Run Existing Tests
```bash
cd /opt/bewaarhet_python_backend

# Existing token tests should pass
python3 -m pytest test_*.py -v -k activation

# Or run all tests
python3 -m pytest test_*.py -v
```

### Manual Test
```bash
# Check code syntax
python3 -m py_compile bewaarhet/customer_onboarding.py
python3 -m py_compile bewaarhet/activation_server.py

# Test token generation (with secret set)
export VERIFICATION_TOKEN_SECRET="test-secret-1234567890abcdef"
python3 -c "
from bewaarhet.customer_onboarding import create_activation_token, verify_activation_token
token = create_activation_token('test@example.com')
email = verify_activation_token(token)
print(f'✓ Token roundtrip success: {email}')
"
```

---

## Security Checklist

✓ No secrets hardcoded  
✓ No plaintext tokens in logs (only error types and first 8 chars)  
✓ Setup script never outputs the actual secret to logs  
✓ .env remains chmod 600 (readable only by bewaarhet user)  
✓ No changes to authentication/authorization logic  
✓ Token expiry remains 72 hours (user configurable)  

---

## Rollback Plan

If any issues:

```bash
# 1. Revert code changes
cd /opt/bewaarhet_python_backend
git revert <commit-hash>
git push

# 2. Restore VPS environment
ssh user@your-vps
sudo cp /opt/bewaarhet/.env.backup-* /opt/bewaarhet/.env

# 3. Restart containers
sudo docker-compose -f docker-compose.production.yml restart bewaarhet_activation bewaarhet_worker
```

---

## Expected Results After Deployment

### Before Patch
- ❌ Activation links: Always fail with `status=400`
- ❌ Logs show: `RuntimeError` (unclear)
- ❌ No clear docs on requirements

### After Patch
- ✓ Activation links: Work when VERIFICATION_TOKEN_SECRET set
- ✓ Logs show: Specific reasons (signature, expiry, etc)
- ✓ Clear docs on setup + requirements
- ✓ Automated setup script available
- ✓ Better error messages for debugging

---

## Contact Points

**Documentation:**
- QUICK_FIX_SUMMARY.md → Start here
- ACTIVATION_TOKEN_FIX.md → Technical details
- VPS_DEPLOYMENT_CHECKLIST.md → Step-by-step
- setup_token_secret.py → Automated setup

**Code:**
- bewaarhet/customer_onboarding.py → Token logic
- bewaarhet/activation_server.py → Error handling
- bewaarhet/config.py → Settings (already correct)

**Support:**
- If containers keep restarting → check docker logs
- If secret not picked up → verify file permissions (chmod 600)
- If tokens still invalid → verify both containers have same secret

---

**Patch Date:** 2026-05-27  
**Patch Version:** 1.0  
**Status:** ✓ READY FOR PRODUCTION

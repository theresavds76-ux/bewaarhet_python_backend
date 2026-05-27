# VPS Production Deployment Checklist - Activation Token Fix

## Date: 2026-05-27
## Issue: Activation links return status=400 with "invalid or expired" error

---

## QUICK START (5 minutes)

### On your VPS, run:

```bash
# 1. SSH into VPS
ssh user@bewaarhet-vps

# 2. Navigate to project
cd /opt/bewaarhet

# 3. Run the automated setup script
python3 setup_token_secret.py

# 4. When prompted, answer "yes" to generate and set VERIFICATION_TOKEN_SECRET

# 5. Set proper permissions
sudo chmod 600 .env
sudo chown bewaarhet:bewaarhet .env

# 6. Restart containers
sudo docker-compose -f docker-compose.production.yml restart bewaarhet_activation bewaarhet_worker

# 7. Verify (wait 10 seconds for containers to restart)
sleep 10
sudo docker logs bewaarhet_activation --tail 20 | grep -E "startup|error|RuntimeError"
```

---

## MANUAL STEPS (if script doesn't work)

### Step 1: Backup Current Environment

```bash
cd /opt/bewaarhet
sudo cp .env .env.backup-$(date +%Y%m%d-%H%M%S)
echo "Backup created: $(sudo ls -lh .env.backup* | tail -1)"
```

### Step 2: Generate Secure Secret

```bash
# Run this command to generate a 32-character random secret
python3 -c "import secrets; print('VERIFICATION_TOKEN_SECRET=' + secrets.token_urlsafe(32))"
```

**Copy the output** - you'll need it in next step.

Example output:
```
VERIFICATION_TOKEN_SECRET=A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6
```

### Step 3: Edit .env File

```bash
sudo nano /opt/bewaarhet/.env
```

**Find this section:**
```env
# Dropbox
DROPBOX_APP_KEY=zcxi5ny3jufu8u4
DROPBOX_APP_SECRET=7iif54cwrz6nuhj
DROPBOX_REFRESH_TOKEN=km6yAcOKMtEAAAAAAAAAAQYeLEg6_0uSkwcqNvF3n8t8zFtRIssmF4NAnw2A7f2-
DROPBOX_BASE_PATH=/Bewaar het/Klanten
```

**Add these lines right after it (before OCR section):**
```env

# ==========================================
# CRITICAL: Token signing secret for activation links
# DO NOT SHARE THIS - Keep it private
# ==========================================
VERIFICATION_TOKEN_SECRET=<paste-your-generated-secret-here>
VERIFICATION_TOKEN_TTL_HOURS=72
```

Replace `<paste-your-generated-secret-here>` with the value from Step 2.

**Save and exit:** Ctrl+X, Y, Enter

### Step 4: Verify File was Updated

```bash
grep VERIFICATION_TOKEN_SECRET /opt/bewaarhet/.env
```

Should output:
```
VERIFICATION_TOKEN_SECRET=A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6
```

### Step 5: Set Proper Permissions

```bash
sudo chmod 600 /opt/bewaarhet/.env
sudo chown bewaarhet:bewaarhet /opt/bewaarhet/.env
ls -l /opt/bewaarhet/.env
```

Should show:
```
-rw------- 1 bewaarhet bewaarhet .... .env
```

### Step 6: Restart Containers

```bash
cd /opt/bewaarhet
sudo docker-compose -f docker-compose.production.yml restart bewaarhet_activation bewaarhet_worker
```

Wait 10 seconds for containers to fully restart.

### Step 7: Verify Containers are Running

```bash
sudo docker ps | grep bewaarhet
```

Should show both `bewaarhet_activation` and `bewaarhet_worker` with status `Up`.

---

## VERIFICATION

### Check Activation Server Logs

```bash
sudo docker logs bewaarhet_activation --tail 30
```

**Look for:**
- ✓ NO `RuntimeError` or `No token secret configured`
- ✓ Should see: `Activation server started | host=0.0.0.0 | port=8080`
- ✓ Should see activation requests with status codes (200, 400, etc)

### Check Worker Logs

```bash
sudo docker logs bewaarhet_worker --tail 30
```

**Look for:**
- ✓ NO `RuntimeError: verification token secret is not configured`
- ✓ Should see normal worker startup messages

### Test Activation Endpoint

```bash
# Test the activation endpoint (will fail with invalid token, but won't have RuntimeError)
curl -i "https://bewaarhet.nl/activeer?token=test123"
```

**Expected response:**
- Status: `400 Bad Request` (token invalid - this is EXPECTED)
- NOT: `500 Internal Server Error` (config error - this would be BAD)
- NOT: `RuntimeError` in response

### Real-World Test

1. Create a test customer account
2. Request an activation link
3. Click the link
4. Check logs for specific error (not RuntimeError): 
   - `token signature verification failed` (if secret wrong - contact me)
   - `token expired` (if old token)
   - `status=200` (activation succeeded)

---

## TROUBLESHOOTING

### Problem: Still seeing RuntimeError after restart

**Solution:**
```bash
# 1. Verify the secret is in .env
grep VERIFICATION_TOKEN_SECRET /opt/bewaarhet/.env

# 2. Check if it's empty
if grep -q 'VERIFICATION_TOKEN_SECRET=$' /opt/bewaarhet/.env; then
    echo "ERROR: VERIFICATION_TOKEN_SECRET is empty!"
    echo "Re-run the setup script or manual steps"
fi

# 3. Force hard restart
sudo docker-compose -f docker-compose.production.yml down
sleep 5
sudo docker-compose -f docker-compose.production.yml up -d bewaarhet_activation bewaarhet_worker
sleep 10
sudo docker logs bewaarhet_activation --tail 20
```

### Problem: Permission denied on .env

**Solution:**
```bash
sudo ls -la /opt/bewaarhet/.env
sudo chmod 600 /opt/bewaarhet/.env
sudo chown bewaarhet:bewaarhet /opt/bewaarhet/.env
```

### Problem: Containers keep restarting

**Solution:**
```bash
# Check what's wrong
sudo docker logs bewaarhet_activation
sudo docker logs bewaarhet_worker

# If it's a Python syntax error, check the files
sudo docker-compose -f docker-compose.production.yml config

# Roll back if needed
sudo cp /opt/bewaarhet/.env.backup-* /opt/bewaarhet/.env
sudo docker-compose -f docker-compose.production.yml restart
```

### Problem: Need to get the exact env vars being used

```bash
# Show what the container is seeing (VERIFICATION_TOKEN_SECRET will be redacted)
sudo docker exec bewaarhet_activation env | grep -i token
sudo docker exec bewaarhet_worker env | grep -i token
```

---

## SECURITY NOTES

⚠️ **NEVER:**
- Commit `.env` to git
- Share `VERIFICATION_TOKEN_SECRET` value with anyone
- Log the full token value (only log hashes/first 8 chars)
- Use the same secret for multiple services

✓ **DO:**
- Store the secret in a password manager / vault
- Keep `.env` chmod 600 (readable only by bewaarhet user)
- Rotate the secret every 6-12 months (invalidates old tokens, users get new activation links)
- Monitor logs for suspicious token validation errors

---

## AFTER DEPLOYMENT

### Verify Activation Flow Works

1. **Create test account via admin panel or API:**
   ```bash
   # Or use your admin interface
   curl -X POST https://bewaarhet.nl/api/v1/admin/create-trial-account \
     -H "Authorization: Bearer <admin-token>" \
     -H "Content-Type: application/json" \
     -d '{"email":"test@example.com"}'
   ```

2. **Check database for pending customer:**
   ```bash
   sudo sqlite3 /opt/bewaarhet/data/bewaarhet.sqlite3
   > SELECT email, status FROM customers WHERE email='test@example.com';
   ```

3. **Manually trigger email or generate activation link:**
   ```bash
   # Check worker logs to see if activation link was sent
   sudo docker logs bewaarhet_worker --tail 50 | grep test@example.com
   ```

4. **Click activation link or simulate:**
   ```bash
   # Get the token from logs (last ~50 chars)
   curl -i "https://bewaarhet.nl/activeer?token=<token-from-logs>"
   ```

5. **Verify customer status changed:**
   ```bash
   sudo sqlite3 /opt/bewaarhet/data/bewaarhet.sqlite3
   > SELECT email, status FROM customers WHERE email='test@example.com';
   ```
   Should show: `test@example.com | active`

---

## ROLLBACK PLAN

If something breaks:

```bash
# 1. Restore backup
sudo cp /opt/bewaarhet/.env.backup-YYYYMMDD-HHMMSS /opt/bewaarhet/.env

# 2. Restart containers
sudo docker-compose -f docker-compose.production.yml restart bewaarhet_activation bewaarhet_worker

# 3. Contact support if issues continue
```

---

## CHANGES INCLUDED IN THIS PATCH

### Files Modified:
1. **bewaarhet/customer_onboarding.py**
   - Improved token secret selection logic
   - Better error messages (now shows what's actually missing)
   
2. **bewaarhet/activation_server.py**
   - Enhanced error logging to distinguish RuntimeError vs ValueError
   - Now logs specific error types and reasons

3. **.env.production**
   - Added `VERIFICATION_TOKEN_SECRET` placeholder
   - Added explanation about the requirement

4. **DEPLOYMENT_RUNBOOK.md**
   - Added explicit section on token secret setup
   - Clarified why this is CRITICAL for production

### Files Created:
1. **ACTIVATION_TOKEN_FIX.md** - Detailed problem analysis
2. **setup_token_secret.py** - Automated setup script
3. **VPS_DEPLOYMENT_CHECKLIST.md** - This file

---

## Support

If issues persist after following this checklist:

1. **Collect logs:**
   ```bash
   sudo docker logs bewaarhet_activation > activation.log
   sudo docker logs bewaarhet_worker > worker.log
   cat /opt/bewaarhet/data/logs/* | tail -100 > app.log
   ```

2. **Check environment:**
   ```bash
   sudo docker exec bewaarhet_activation env | grep -E "VERIFICATION|DATABASE" > env_state.log
   ```

3. **Share these logs with development team (redact secrets!)**

---

**Last Updated:** 2026-05-27  
**Patch Version:** 1.0

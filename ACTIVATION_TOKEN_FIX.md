# Activation Token Fix - Production VPS Patch

## Problem Summary
Activation links fail with `status=400` because:
- `VERIFICATION_TOKEN_SECRET` environment variable is **NOT SET** in production
- Token generation and validation fail with `RuntimeError: No token secret configured`
- This affects both `bewaarhet_worker` (token generation) and `bewaarhet_activation` (token validation)

## Root Cause
The token signing secret falls back to `DROPBOX_APP_SECRET` or `ZOHO_APP_PASSWORD` if `VERIFICATION_TOKEN_SECRET` is missing. This is unreliable and insecure. If ALL secrets are empty, tokens fail immediately.

## Solution

### Step 1: Generate a Secure Token Secret

SSH to your VPS and run:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Example output:
```
Z3t5KpQvR8sL9mN2xY1aB4cD6eF7gH0jI9k
```

**COPY THIS VALUE** - you'll need it in Step 2.

### Step 2: Update `/opt/bewaarhet/.env` on VPS

1. **Backup the current .env:**
   ```bash
   sudo cp /opt/bewaarhet/.env /opt/bewaarhet/.env.backup-$(date +%Y%m%d)
   ```

2. **Edit `/opt/bewaarhet/.env`:**
   ```bash
   sudo nano /opt/bewaarhet/.env
   ```

3. **Find the section with Dropbox credentials** (look for `DROPBOX_APP_KEY=`, `DROPBOX_APP_SECRET=`, etc.)

4. **Add these two lines RIGHT AFTER the Dropbox section and BEFORE the OCR section:**
   ```env
   # Token signing secret for activation links (REQUIRED - see ACTIVATION_TOKEN_FIX.md)
   VERIFICATION_TOKEN_SECRET=<paste-your-generated-secret-here>
   VERIFICATION_TOKEN_TTL_HOURS=72
   ```

   Replace `<paste-your-generated-secret-here>` with the secret from Step 1.

5. **Save and exit** (Ctrl+X, Y, Enter in nano)

### Step 3: Verify File Permissions

```bash
# Ensure .env is readable only by bewaarhet user
sudo chmod 600 /opt/bewaarhet/.env
sudo chown bewaarhet:bewaarhet /opt/bewaarhet/.env
```

### Step 4: Restart Containers

Both containers must restart to pick up the new `.env` values:

```bash
# If using docker-compose (from the project directory):
sudo docker-compose -f docker-compose.production.yml restart bewaarhet_activation bewaarhet_worker

# If using docker directly:
sudo docker restart bewaarhet_activation bewaarhet_worker
```

### Step 5: Verify

Check logs to confirm no more RuntimeError:

```bash
# Check activation server logs
sudo docker logs bewaarhet_activation --tail 50

# Check worker logs  
sudo docker logs bewaarhet_worker --tail 50

# Look for patterns like:
# ✓ No "RuntimeError" or "No token secret configured"
# ✓ Activation requests should show "status=200" or "status=400" (but NOT RuntimeError)
```

Test an activation link manually:
```bash
curl -i "https://bewaarhet.nl/activeer?token=test-token-here"
```

Should return `400 Bad Request` with "token invalid" message (not `500 Internal Server Error`).

## Important Notes

- **Same secret everywhere:** Both `bewaarhet_activation` and `bewaarhet_worker` MUST have the same `VERIFICATION_TOKEN_SECRET`
- **Never rotate:** Changing this secret will invalidate all existing activation tokens. Plan ahead.
- **Keep secret:** Do NOT commit this to git. Store only in VPS `/opt/bewaarhet/.env`
- **Backup:** Save your secret somewhere safe (password manager, vault)
- **Logging:** Improved logging in the patch will now show specific token validation errors (signature, expiry, etc)

## Code Changes in This Patch

1. **customer_onboarding.py:**
   - Improved `_token_secret()` to fail faster with clear error message
   - Enhanced `verify_activation_token()` with specific error reasons
   - Better logging for debugging

2. **.env.production:**
   - Added `VERIFICATION_TOKEN_SECRET` placeholder
   - Added `VERIFICATION_TOKEN_TTL_HOURS` with explanation

3. **activation_server.py:**
   - Enhanced error logging to distinguish RuntimeError vs ValueError
   - Logs now show: `error_type`, `config_error`, `reason` fields

4. **DEPLOYMENT_RUNBOOK.md:**
   - Added explicit section on generating and setting `VERIFICATION_TOKEN_SECRET`
   - Explained why this is CRITICAL for production

## Rollback (If Needed)

```bash
sudo cp /opt/bewaarhet/.env.backup-20260527 /opt/bewaarhet/.env
sudo docker-compose -f docker-compose.production.yml restart bewaarhet_activation bewaarhet_worker
```

## FAQ

**Q: What if I lose my VERIFICATION_TOKEN_SECRET?**
A: You can change it (invalidating all old tokens), but existing users with old activation links will need new ones.

**Q: Can I use my Dropbox secret instead?**
A: Not recommended - the code has a fallback for backward compatibility, but it's insecure and unreliable. Use a dedicated `VERIFICATION_TOKEN_SECRET`.

**Q: Why is this 72 hours?**
A: Allows users 3 days to activate their account before expiry. Adjust `VERIFICATION_TOKEN_TTL_HOURS` if needed.

**Q: How do I know it's working?**
A: Test with a real activation link. Check logs for "activation failed | error_type=..." messages. If you see specific reasons (signature, expiry), it's working.

---

**Deployment Date:** 2026-05-27  
**Related Issue:** Activation links return status=400 with RuntimeError

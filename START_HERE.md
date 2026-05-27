# ⚡ START HERE - Activation Link Fix - Action Required

**Date:** 2026-05-27  
**Status:** ✅ PATCHES READY - REQUIRES VPS ACTION  
**Urgency:** HIGH - All activation links currently broken  

---

## 🎯 What's Wrong

Activation links on bewaarhet.nl fail with error:
```
status=400 | error=RuntimeError: verification token secret is not configured
```

**Why:** VPS environment is missing `VERIFICATION_TOKEN_SECRET` env var.

---

## ✅ What's Been Fixed

All code patches are ready. You now have:

### Code Patches (Already Applied - git pull to get)
1. ✓ Better error logging in `bewaarhet/customer_onboarding.py`
2. ✓ Enhanced exception handling in `bewaarhet/activation_server.py`
3. ✓ Config template in `.env.production`
4. ✓ Deployment instructions in `DEPLOYMENT_RUNBOOK.md`

### Helper Resources (New files created)
1. ✓ `QUICK_FIX_SUMMARY.md` - 1-page summary (start here)
2. ✓ `ACTIVATION_TOKEN_FIX.md` - Technical deep-dive
3. ✓ `VPS_DEPLOYMENT_CHECKLIST.md` - Step-by-step guide
4. ✓ `setup_token_secret.py` - Automated setup script
5. ✓ `PATCH_SUMMARY.md` - What changed

---

## 🚀 REQUIRED VPS ACTION (You Do This)

### The Exact Env Var You Must Set

On your VPS `/opt/bewaarhet/.env`, add:

```env
VERIFICATION_TOKEN_SECRET=<your-secure-random-secret>
VERIFICATION_TOKEN_TTL_HOURS=72
```

### How to Get the Secret

Run this command **on your VPS**:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Example output:
```
AbCdEfGhIjKlMnOpQrStUvWxYz1234567890AB
```

**Copy this value** → paste into `.env` after the DROPBOX section.

### Deployment (5 minutes)

**Option A: Automated (Recommended)**

```bash
ssh user@your-vps
cd /opt/bewaarhet
python3 setup_token_secret.py
# Follow prompts, it will:
# - Generate secret
# - Backup current .env
# - Add to .env
# - Show next steps
```

**Option B: Manual**

```bash
ssh user@your-vps
sudo nano /opt/bewaarhet/.env

# Find: DROPBOX_BASE_PATH=/Bewaar het/Klanten
# Add after it:
# VERIFICATION_TOKEN_SECRET=<paste-secret-from-above>
# VERIFICATION_TOKEN_TTL_HOURS=72

# Save (Ctrl+X, Y, Enter)
```

### Restart Containers

```bash
cd /opt/bewaarhet
sudo docker-compose -f docker-compose.production.yml restart bewaarhet_activation bewaarhet_worker
```

### Verify It Works

```bash
# Wait 10 seconds
sleep 10

# Check logs (should NOT see RuntimeError)
sudo docker logs bewaarhet_activation | tail -20 | grep -iE "runtimeerror|activated|failed"

# Test endpoint (should return 400, not 500)
curl -i https://bewaarhet.nl/activeer?token=invalid-test
```

---

## 📋 What You Get

After deploying:

✅ Activation links work  
✅ Clear error logging for debugging  
✅ Same secret on both containers (worker + activation)  
✅ 72-hour token expiry (configurable)  
✅ Documented setup for future deployments  

---

## 🔍 Understanding the Fix

### Why It Failed Before
1. Worker tries to sign activation tokens
2. Needs `VERIFICATION_TOKEN_SECRET` → **NOT SET** on VPS
3. Falls back to other secrets (Dropbox, Zoho)
4. If all empty → `RuntimeError`
5. Activation server can't verify tokens → `status=400`

### Why It Works Now
1. Both containers load **same** `/opt/bewaarhet/.env`
2. `VERIFICATION_TOKEN_SECRET` is now set properly
3. Worker signs tokens with this secret
4. Activation server validates with same secret
5. Signature match → token valid → customer activated

---

## 📁 Reference Documents

**For Quick Summary:**
- `QUICK_FIX_SUMMARY.md` ← Start here for overview

**For VPS Deployment:**
- `VPS_DEPLOYMENT_CHECKLIST.md` ← Step-by-step guide
- `setup_token_secret.py` ← Automated setup

**For Technical Details:**
- `ACTIVATION_TOKEN_FIX.md` ← Deep-dive analysis
- `PATCH_SUMMARY.md` ← What changed in code

**For Future Deployments:**
- `DEPLOYMENT_RUNBOOK.md` ← Updated with token secret section

---

## ⚠️ Important Notes

| Topic | Details |
|-------|---------|
| **Keep Secret** | Never share `VERIFICATION_TOKEN_SECRET` value |
| **Keep Safe** | Don't commit `.env` to git (already in .gitignore) |
| **Same Everywhere** | Both containers MUST have identical secret |
| **Don't Rotate** | Changing secret invalidates all active tokens (users lose access) |
| **File Permissions** | Keep `.env` as `chmod 600` (readable only by bewaarhet user) |

---

## 🆘 Troubleshooting

### Still seeing RuntimeError after restart?

```bash
# Check if secret is actually in .env
grep VERIFICATION_TOKEN_SECRET /opt/bewaarhet/.env

# Check if it's empty
if grep -q 'VERIFICATION_TOKEN_SECRET=$' /opt/bewaarhet/.env; then
    echo "ERROR: Secret is empty! Redo the setup."
fi

# Force hard restart
sudo docker-compose -f docker-compose.production.yml down
sleep 5
sudo docker-compose -f docker-compose.production.yml up -d bewaarhet_activation bewaarhet_worker
sleep 10
sudo docker logs bewaarhet_activation
```

### Permission denied on .env?

```bash
sudo chmod 600 /opt/bewaarhet/.env
sudo chown bewaarhet:bewaarhet /opt/bewaarhet/.env
```

### Containers keep crashing?

```bash
# Show detailed error
sudo docker logs bewaarhet_activation
sudo docker logs bewaarhet_worker

# Restore backup if needed
sudo cp /opt/bewaarhet/.env.backup-* /opt/bewaarhet/.env
sudo docker-compose -f docker-compose.production.yml restart
```

---

## ✓ Deployment Checklist

Before you deploy:
- [ ] Read `QUICK_FIX_SUMMARY.md`
- [ ] SSH access to VPS ready
- [ ] Git pull to get latest code
- [ ] Generated the random secret (`python3 -c "import secrets; print(...);"`)

During deployment:
- [ ] Added `VERIFICATION_TOKEN_SECRET` to `/opt/bewaarhet/.env`
- [ ] Added `VERIFICATION_TOKEN_TTL_HOURS=72`
- [ ] Set correct file permissions (`chmod 600 .env`)
- [ ] Restarted containers
- [ ] Waited 10 seconds for startup

After deployment:
- [ ] Checked logs (no RuntimeError)
- [ ] Tested endpoint (returns 400, not 500)
- [ ] Verified env var is set (`docker exec ... env | grep VERIFICATION`)
- [ ] Tested with real activation link

---

## 🎉 Success Criteria

You'll know it's fixed when:

```bash
# ✓ No RuntimeError in logs
sudo docker logs bewaarhet_activation | grep RuntimeError
# (should output nothing)

# ✓ Activation server healthy
sudo docker logs bewaarhet_activation | grep "Activation server started"
# (should show startup message)

# ✓ Endpoint returns proper status
curl -i https://bewaarhet.nl/activeer?token=test
# (should return 400 Bad Request, not 500 or RuntimeError)

# ✓ Real token works
# Create test customer, click activation link
# Should see: "Your account is now active!"
# (not: "invalid or expired")
```

---

## 📞 Need Help?

1. **Logs won't start:** Check `docker logs` output for Python errors
2. **Secret not picked up:** Verify it's in correct location in `.env`
3. **Permissions issues:** Use `sudo` for container commands
4. **Need to rollback:** Restore `.env.backup-*` and restart

Contact development team with:
- Output of `sudo docker logs bewaarhet_activation --tail 50`
- Output of `sudo docker logs bewaarhet_worker --tail 50`
- Confirmation that `.env` has VERIFICATION_TOKEN_SECRET set

---

## 📅 Timeline

- **Code patches:** ✓ Ready (pull from git)
- **VPS action:** ⏳ Next (set env var + restart)
- **Verification:** ⏳ After restart (check logs)
- **Testing:** ⏳ Final (test with real activation link)

---

**Status: READY FOR DEPLOYMENT** ✅  
**Estimated Time: 10-15 minutes**  
**Risk Level: LOW** (config only, no code logic changes)  
**Rollback: Easy** (restore `.env` backup, restart)

---

**Next Step:** SSH to VPS and run `python3 setup_token_secret.py` OR read `VPS_DEPLOYMENT_CHECKLIST.md` for manual steps.

#!/usr/bin/env python3
"""
Safe setup script for VERIFICATION_TOKEN_SECRET on production VPS.

Usage:
  ssh user@vps
  cd /opt/bewaarhet
  python3 setup_token_secret.py

This script:
1. Checks if VERIFICATION_TOKEN_SECRET is already set
2. Generates a secure random secret
3. Backs up the current .env
4. Adds VERIFICATION_TOKEN_SECRET to .env
5. Validates the change
"""

import os
import sys
import secrets
import shutil
from pathlib import Path
from datetime import datetime


def main():
    env_path = Path('.env')
    
    if not env_path.exists():
        print(f"ERROR: {env_path} not found in current directory")
        print("Run this script from /opt/bewaarhet")
        sys.exit(1)
    
    # Read current .env
    env_content = env_path.read_text(encoding='utf-8')
    
    # Check if already set
    if 'VERIFICATION_TOKEN_SECRET=' in env_content:
        lines = env_content.split('\n')
        for line in lines:
            if line.startswith('VERIFICATION_TOKEN_SECRET='):
                current_value = line.split('=', 1)[1].strip()
                if current_value and not current_value.startswith('placeholder'):
                    print(f"✓ VERIFICATION_TOKEN_SECRET is already set")
                    print(f"  Current value length: {len(current_value)} chars")
                    print(f"  (showing first 8 chars: {current_value[:8]}...)")
                    response = input("\nReplace with a new secret? (yes/no): ").strip().lower()
                    if response != 'yes':
                        print("Cancelled.")
                        sys.exit(0)
                break
    
    # Generate new secret
    print("\nGenerating secure random secret...")
    new_secret = secrets.token_urlsafe(32)
    print(f"✓ Generated: {new_secret}")
    print(f"  Length: {len(new_secret)} chars")
    
    # Backup
    backup_path = env_path.with_name(f'.env.backup-{datetime.now().strftime("%Y%m%d-%H%M%S")}')
    shutil.copy2(env_path, backup_path)
    print(f"\n✓ Backup created: {backup_path}")
    
    # Update .env
    if 'VERIFICATION_TOKEN_SECRET=' in env_content:
        # Replace existing
        lines = []
        for line in env_content.split('\n'):
            if line.startswith('VERIFICATION_TOKEN_SECRET='):
                lines.append(f'VERIFICATION_TOKEN_SECRET={new_secret}')
            else:
                lines.append(line)
        new_content = '\n'.join(lines)
    else:
        # Find insertion point (after Dropbox section, before OCR section)
        lines = env_content.split('\n')
        insert_index = None
        
        for i, line in enumerate(lines):
            if 'OCR_SPACE_API_KEY=' in line or '# OCR' in line:
                insert_index = i
                break
        
        if insert_index is None:
            print("\nWARNING: Could not find insertion point for VERIFICATION_TOKEN_SECRET")
            print("Adding at end of file instead")
            new_content = env_content + f'\n\n# Token signing secret (CRITICAL for activation links)\nVERIFICATION_TOKEN_SECRET={new_secret}\nVERIFICATION_TOKEN_TTL_HOURS=72\n'
        else:
            lines.insert(insert_index, f'# Token signing secret (CRITICAL for activation links)')
            lines.insert(insert_index + 1, f'VERIFICATION_TOKEN_SECRET={new_secret}')
            lines.insert(insert_index + 2, f'VERIFICATION_TOKEN_TTL_HOURS=72')
            new_content = '\n'.join(lines)
    
    # Write updated .env
    env_path.write_text(new_content, encoding='utf-8')
    print(f"\n✓ Updated {env_path}")
    
    # Verify
    updated_content = env_path.read_text(encoding='utf-8')
    if f'VERIFICATION_TOKEN_SECRET={new_secret}' in updated_content:
        print(f"✓ Verification successful: VERIFICATION_TOKEN_SECRET is now set")
    else:
        print(f"ERROR: Verification failed!")
        sys.exit(1)
    
    print("\n" + "="*60)
    print("NEXT STEPS:")
    print("="*60)
    print("1. Verify file permissions:")
    print("   sudo chmod 600 .env")
    print("   sudo chown bewaarhet:bewaarhet .env")
    print("\n2. Restart containers:")
    print("   sudo docker-compose -f docker-compose.production.yml restart bewaarhet_activation bewaarhet_worker")
    print("\n3. Check logs:")
    print("   sudo docker logs bewaarhet_activation --tail 20")
    print("   sudo docker logs bewaarhet_worker --tail 20")
    print("\n4. Look for token validation errors (not RuntimeError):")
    print("   Should see specific reasons: signature, expiry, etc.")
    print("="*60)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nCancelled.")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        sys.exit(1)

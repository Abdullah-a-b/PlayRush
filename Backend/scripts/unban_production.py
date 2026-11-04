"""Target one production account using Azure settings, never the local .env."""
import argparse
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--email")
    parser.add_argument("--check-connection", action="store_true")
    parser.add_argument("--app", default="playrush-server")
    parser.add_argument("--resource-group", default="playrush-rg")
    args = parser.parse_args()
    if not args.check_connection and (not args.email or "@" not in args.email):
        parser.error("Provide the exact account email with --email.")
    az = shutil.which("az")
    if not az:
        print("Azure CLI is missing. Install it and run az login.")
        return 1
    result = subprocess.run([az, "webapp", "config", "appsettings", "list",
        "--name", args.app, "--resource-group", args.resource_group,
        "--query", "[?name=='DATABASE_URL'].value | [0]", "--output", "json",
        "--only-show-errors"], capture_output=True, text=True)
    # Never print Azure output: it can contain credentials.
    if result.returncode:
        print("Cannot read Azure app settings. Check az login and access to the app.")
        return 1
    import json
    try:
        database_url = json.loads(result.stdout)
        if not isinstance(database_url, str) or not database_url.startswith("postgresql"):
            raise ValueError()
    except Exception:
        print("DATABASE_URL is missing or invalid in the Azure app settings.")
        return 1
    from sqlalchemy import create_engine, text
    engine = None
    try:
        engine = create_engine(database_url, connect_args={"connect_timeout": 15}, hide_parameters=True)
        with engine.begin() as conn:
            conn.execute(text("SELECT 1"))
            if args.check_connection:
                print("Production database connection OK. No accounts were read or changed.")
                return 0
            email = args.email.strip()
            row = conn.execute(text("UPDATE users SET is_banned = FALSE, anticheat_score = 0 WHERE email = :email RETURNING id"), {"email": email}).first()
            if row is None:
                print("No matching account. Nothing changed.")
                return 2
            if conn.execute(text("SELECT to_regclass('player_penalties')")).scalar():
                conn.execute(text("UPDATE player_penalties SET expires_at = NOW() WHERE user_id = :uid AND (expires_at IS NULL OR expires_at > NOW())"), {"uid": row[0]})
            verified = conn.execute(text("SELECT is_banned, anticheat_score FROM users WHERE id = :uid"), {"uid": row[0]}).one()
            if verified[0] or verified[1] != 0:
                raise RuntimeError()
        print("Production account unbanned. Anti-cheat score reset. Please sign in again.")
        return 0
    except Exception as exc:
        # Database exceptions may contain URLs or SQL parameters. Show type only.
        print("Production operation failed (" + type(exc).__name__ + "). No partial changes were committed.")
        print("Check network access and the database firewall. Connection details are not displayed.")
        return 1
    finally:
        database_url = None
        if engine is not None:
            engine.dispose()

if __name__ == "__main__":
    sys.exit(main())

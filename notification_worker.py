"""Run once from cron/systemd or continuously; SMTP requires --send."""
import argparse
import os
import smtplib
import ssl
import time

from dotenv import load_dotenv

load_dotenv()

from adapters.repository import SQLiteMeetings
from services.notifications import dispatch
from settings import DATA


def smtp_send(message):
    host = os.environ["SMTP_HOST"]
    port = int(os.getenv("SMTP_PORT", "587"))
    with smtplib.SMTP(host, port, timeout=20) as smtp:
        if os.getenv("SMTP_STARTTLS", "1") == "1":
            smtp.starttls(context=ssl.create_default_context())
        if os.getenv("SMTP_USER"):
            smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        smtp.send_message(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--send", action="store_true", help="Deliver approved assignments using configured SMTP")
    parser.add_argument("--interval", type=int, default=0, help="Seconds between runs; 0 runs once")
    args = parser.parse_args()
    if args.interval < 0:
        parser.error("interval must be nonnegative")
    if args.send and not all(os.getenv(name) for name in ("SMTP_HOST", "SMTP_FROM")):
        parser.error("SMTP_HOST and SMTP_FROM are required with --send")
    repo = SQLiteMeetings(DATA / "meetings.sqlite3")
    while True:
        try:
            count = dispatch(repo, DATA / "outbox", send=smtp_send if args.send else None,
                             sender=os.getenv("SMTP_FROM", "alem@localhost"))
            print(f"{'Sent' if args.send else 'Prepared'}: {count}", flush=True)
        except (OSError, smtplib.SMTPException, ValueError) as exc:
            print(f"Delivery failed ({type(exc).__name__}); retry on next run.", flush=True)
            if not args.interval:
                raise
        if not args.interval:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()

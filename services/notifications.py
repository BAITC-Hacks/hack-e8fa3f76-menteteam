"""Durable local mail spool and opt-in SMTP delivery."""
import hashlib
import re
from datetime import date, timedelta
from email.message import EmailMessage
from email.utils import formatdate
from pathlib import Path
from typing import Callable

from adapters.repository import SQLiteMeetings


def valid_email(value: str) -> bool:
    return bool(re.fullmatch(r"[^\s@<>\r\n]+@[^\s@<>\r\n]+\.[^\s@<>\r\n]+", value))


def dispatch(repo: SQLiteMeetings, outbox: Path, today: date | None = None,
             send: Callable[[EmailMessage], None] | None = None,
             sender: str = "alem@localhost") -> int:
    today = today or date.today()
    count = 0
    outbox.mkdir(parents=True, exist_ok=True)
    for meeting in repo.list():
        for task in meeting.tasks:
            if not task.approved or task.status == "Выполнено" or not valid_email(task.email):
                continue
            content = f"{task.title}\0{task.owner}\0{task.email}\0{task.deadline}\0{task.due_date}\0{task.evidence}"
            revision = hashlib.sha256(content.encode()).hexdigest()
            kinds = [("Поручение", revision)]
            if task.due_date and task.due_date < today:
                kinds.append(("Просрочено", f"{task.due_date}:{today}"))
            elif task.due_date and task.due_date <= today + timedelta(days=3):
                kinds.append(("Скоро срок", f"{task.due_date}:{today}"))
            for kind, period in kinds:
                mode = "smtp" if send else "spool"
                key = hashlib.sha256(f"{meeting.id}:{task.id}:{kind}:{period}:{mode}".encode()).hexdigest()
                with repo.notification(key, meeting=meeting) as pending:
                    if not pending:
                        continue
                    message = EmailMessage()
                    message["From"], message["To"] = sender, task.email
                    message["Subject"] = " ".join(f"{kind}: {task.title}".splitlines())
                    message["Date"] = formatdate(localtime=True)
                    message["Message-ID"] = f"<{key}@alem.local>"
                    message.set_content(f"Совещание: {meeting.title}\nОтветственный: {task.owner}\n"
                                        f"Поручение: {task.title}\nСрок: {task.due_date or task.deadline}\n"
                                        f"Цитата [{task.timestamp:.1f} с]: {task.evidence}\n")
                    if send:
                        send(message)
                    else:
                        target = outbox / f"{key}.eml"
                        target.write_bytes(message.as_bytes())
                        target.chmod(0o600)
                    count += 1
    return count

"""Explicit synthetic fixtures for demonstrating the review workflow without models."""
from datetime import date

from core.grounding import build_result, rename_participants
from core.models import Segment


def demo_meeting():
    segments = [
        Segment(id="seg-1", speaker="SPEAKER_00", start=0, end=7,
                text="Айжан, подготовь бюджет проекта до 2026-09-25. Это срочно."),
        Segment(id="seg-2", speaker="SPEAKER_01", start=7, end=13,
                text="Жақсы, мен бюджет дайындаймын. Данияр, есепті ертең жібер."),
        Segment(id="seg-3", speaker="SPEAKER_02", start=13, end=19,
                text="Келістік. Отправлю отчёт. Запуск пилота согласовали на октябрь."),
    ]
    result = build_result("Демо • Русский + қазақша", segments, "ru/kk", {
        "summary": "Команда согласовала подготовку бюджета и отчёта. Пилот запланирован на октябрь.",
        "decisions": ["Запуск пилота — в октябре."],
        "tasks": [
            {"title": "Подготовить бюджет проекта", "owner": "Айжан", "deadline": "до 2026-09-25",
             "evidence": segments[0].text, "urgency": "Высокая", "area": "Финансы"},
            {"title": "Есепті жіберу", "owner": "Данияр", "deadline": "ертең",
             "evidence": segments[1].text, "area": "Отчётность"},
        ]}, date(2026, 9, 23))
    result = rename_participants(result, {"SPEAKER_00": "Куратор", "SPEAKER_01": "Айжан", "SPEAKER_02": "Данияр"})
    result.warnings = ["Демонстрационные данные: синтетический транскрипт и заранее заданное извлечение. Модели не запускались."]
    return result

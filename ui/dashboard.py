from datetime import date, timedelta

import streamlit as st


def render_dashboard(meetings):
    today = date.today()
    tasks = [(meeting, task) for meeting in meetings for task in meeting.tasks]
    active = [(m, t) for m, t in tasks if t.status == "В работе"]
    overdue = [(m, t) for m, t in active if t.due_date and t.due_date < today]
    upcoming = [(m, t) for m, t in active if t.due_date and today <= t.due_date <= today + timedelta(days=3)]
    cols = st.columns(4)
    for col, title, value in zip(cols, ["Совещаний", "В работе", "Просрочено", "Ближайшие 3 дня"],
                                  [len(meetings), len(active), len(overdue), len(upcoming)]):
        col.metric(title, value)
    if not tasks:
        st.info("Добавьте запись или откройте демонстрацию — здесь появятся поручения и сроки.")
        return
    status = st.segmented_control("Показать", ["Все", "В работе", "Просрочено", "Выполнено", "Черновики"], default="Все")
    search = st.text_input("Поиск по поручениям, людям и совещаниям", placeholder="Например: Айжан или бюджет")
    rows = []
    for meeting, task in tasks:
        derived = "Просрочено" if task.status == "В работе" and task.due_date and task.due_date < today else task.status
        if status == "Черновики" and task.approved:
            continue
        if status not in (None, "Все", "Черновики") and status != derived:
            continue
        if search.casefold() not in f"{meeting.title} {task.title} {task.owner} {task.area}".casefold():
            continue
        rows.append({"Поручение": task.title, "Ответственный": task.owner, "Срок": str(task.due_date or task.deadline),
                     "Статус": derived, "Проверка": "Проверено" if task.approved else "Черновик",
                     "Срочность": task.urgency, "Направление": task.area, "Совещание": meeting.title})
    st.dataframe(rows, hide_index=True, use_container_width=True)
    st.caption("Напоминания создаёт отдельный локальный worker. Календарные сроки отсчитываются по дате на сервере.")

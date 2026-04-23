import io
import re
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

DEFAULT_EXCEL_FILENAME = "OXI ESTADO.xlsm"
PAGE_TITLE = "Dashboard OXI / Qamaqi"


@dataclass
class CalendarHelper:
    workdays: list[pd.Timestamp]

    def __post_init__(self):
        self.workdays = sorted(pd.to_datetime(self.workdays).normalize().unique())
        self.workday_set = set(self.workdays)
        self.position = {day: idx for idx, day in enumerate(self.workdays)}

    def next_working_day(self, value):
        dt = pd.Timestamp(value).normalize()
        if dt in self.workday_set:
            return dt
        for day in self.workdays:
            if day >= dt:
                return day
        while dt.weekday() >= 5:
            dt += pd.Timedelta(days=1)
        return dt

    def previous_working_day(self, value, n=1):
        dt = self.next_working_day(value)
        idx = self.position.get(dt)
        if idx is not None and idx - n >= 0:
            return self.workdays[idx - n]
        while n > 0:
            dt -= pd.Timedelta(days=1)
            if dt.weekday() < 5:
                n -= 1
        return dt

    def add_working_days(self, value, n=0):
        dt = self.next_working_day(value)
        if n == 0:
            return dt
        idx = self.position.get(dt)
        if idx is not None:
            target = idx + n
            if 0 <= target < len(self.workdays):
                return self.workdays[target]
            if target < 0:
                return self.workdays[0]
        step = 1 if n > 0 else -1
        remaining = abs(n)
        while remaining > 0:
            dt += pd.Timedelta(days=step)
            if dt.weekday() < 5:
                remaining -= 1
        return dt

    def business_days_between(self, start, end):
        if pd.isna(start) or pd.isna(end):
            return np.nan
        start = self.next_working_day(start)
        end = self.next_working_day(end)
        if start == end:
            return 0
        sign = 1
        if end < start:
            start, end = end, start
            sign = -1
        idx_start = self.position.get(start)
        idx_end = self.position.get(end)
        if idx_start is not None and idx_end is not None:
            return sign * (idx_end - idx_start)
        return sign * int(np.busday_count(start.date(), end.date()))


st.set_page_config(page_title=PAGE_TITLE, layout="wide", initial_sidebar_state="expanded")

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.2rem; padding-bottom: 1.2rem;}
    .main-title {font-size: 2rem; font-weight: 700; margin-bottom: .2rem;}
    .subtitle {color: #5b6470; margin-bottom: 1rem;}
    div[data-testid="stMetricValue"] {font-size: 1.65rem;}
    div[data-testid="stMetric"] {background: #f7f9fc; border: 1px solid #e8edf5; padding: .75rem; border-radius: 14px;}
    .section-card {background: #ffffff; border: 1px solid #e9eef5; border-radius: 18px; padding: 1rem 1rem .25rem 1rem; margin-bottom: 1rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


def normalize_text(value):
    if pd.isna(value):
        return ""
    text = str(value).strip().lower()
    return re.sub(r"\s+", " ", text)



def title_case_safe(value):
    if pd.isna(value):
        return ""
    return str(value).strip()



def clean_columns(df):
    frame = df.copy()
    frame.columns = [str(col).strip() for col in frame.columns]
    keep_mask = ~pd.Series(frame.columns).astype(str).str.startswith("Unnamed")
    return frame.loc[:, keep_mask.values]



def find_sheet_name(xls, requested_name):
    requested_norm = normalize_text(requested_name)
    normalized = {normalize_text(name): name for name in xls.sheet_names}
    if requested_norm in normalized:
        return normalized[requested_norm]
    for norm_name, real_name in normalized.items():
        if requested_norm in norm_name or norm_name in requested_norm:
            return real_name
    raise ValueError(f"No se encontró la hoja '{requested_name}'. Hojas disponibles: {xls.sheet_names}")



def read_workbook(source):
    xls = pd.ExcelFile(source)
    estado = clean_columns(pd.read_excel(source, sheet_name=find_sheet_name(xls, "Estado qamaqi")))
    tareas = clean_columns(pd.read_excel(source, sheet_name=find_sheet_name(xls, "Tareas")))
    desplegables = clean_columns(pd.read_excel(source, sheet_name=find_sheet_name(xls, "Desplegables")))
    calendario = clean_columns(pd.read_excel(source, sheet_name=find_sheet_name(xls, "dim_calendario")))
    try:
        proyectos = clean_columns(pd.read_excel(source, sheet_name=find_sheet_name(xls, "Lista proyectos")))
    except Exception:
        proyectos = pd.DataFrame()
    return {
        "estado": estado,
        "tareas": tareas,
        "desplegables": desplegables,
        "calendario": calendario,
        "proyectos": proyectos,
        "sheet_names": xls.sheet_names,
    }


@st.cache_data(show_spinner=False)
def load_data_from_path(path):
    return read_workbook(path)


@st.cache_data(show_spinner=False)
def load_data_from_bytes(file_bytes):
    return read_workbook(io.BytesIO(file_bytes))



def build_calendar_helper(cal_df):
    cal = cal_df.copy()
    cal = cal[cal["Fecha"].notna()].copy()
    cal["Fecha"] = pd.to_datetime(cal["Fecha"], errors="coerce").dt.normalize()
    laborable_col = next((c for c in cal.columns if normalize_text(c) == "día laborable"), "Día laborable")
    cal["es_laborable"] = cal[laborable_col].astype(str).str.strip().str.lower().isin(["sí", "si", "true", "1", "yes"])
    return CalendarHelper(cal.loc[cal["es_laborable"], "Fecha"].dropna().tolist())



def prepare_data(raw):
    estado = raw["estado"].copy()
    tareas = raw["tareas"].copy()
    desplegables = raw["desplegables"].copy()
    calendario = raw["calendario"].copy()
    proyectos = raw["proyectos"].copy()

    estado = estado[estado.get("Proyecto").notna()].copy()
    tareas = tareas[tareas.get("Asunto breve").notna()].copy()
    if "LISTA CATEGORIAS" in desplegables.columns:
        desplegables = desplegables[desplegables["LISTA CATEGORIAS"].notna()].copy()
    else:
        raise ValueError("La hoja Desplegables no contiene la columna 'LISTA CATEGORIAS'.")

    calendario["Fecha"] = pd.to_datetime(calendario["Fecha"], errors="coerce").dt.normalize()
    estado["Fecha"] = pd.to_datetime(estado["Fecha"], errors="coerce").dt.normalize()
    if "Fecha2" in estado.columns:
        estado["Fecha2"] = pd.to_datetime(estado["Fecha2"], errors="coerce", unit="D", origin="1899-12-30")
    if "Fecha" in tareas.columns:
        tareas["Fecha"] = pd.to_datetime(tareas["Fecha"], errors="coerce").dt.normalize()
    if "orden" in tareas.columns:
        tareas["orden"] = pd.to_numeric(tareas["orden"], errors="coerce")

    estado["categoria_norm"] = estado["categoria 1"].map(normalize_text)
    estado["asunto_norm"] = estado["Asunto breve"].map(normalize_text)
    estado["tarea_norm"] = estado.get("Tarea asociada", pd.Series(index=estado.index)).map(normalize_text)

    tareas["categoria_norm"] = tareas["categoria 1"].map(normalize_text)
    tareas["asunto_norm"] = tareas["Asunto breve"].map(normalize_text)
    tareas["tarea_norm"] = tareas["Id tarea"].map(normalize_text)

    desplegables["categoria_norm"] = desplegables["LISTA CATEGORIAS"].map(normalize_text)
    desplegables["LISTA CATEGORIAS"] = desplegables["LISTA CATEGORIAS"].astype(str).str.strip()

    stage_catalog = [value for value in desplegables["LISTA CATEGORIAS"].tolist() if str(value).strip()]
    task_catalog = (
        tareas[["Id tarea", "orden", "categoria 1", "categoria_norm", "Asunto breve", "asunto_norm"]]
        .dropna(subset=["Asunto breve"])
        .copy()
    )
    task_catalog["categoria 1"] = task_catalog["categoria 1"].fillna("")
    task_catalog["orden"] = task_catalog["orden"].fillna(9999)
    task_catalog = task_catalog.sort_values(["categoria_norm", "orden", "Id tarea", "Asunto breve"])

    helper = build_calendar_helper(calendario)

    available_projects = []
    if not proyectos.empty and "Nombre corto proyecto" in proyectos.columns:
        available_projects.extend(proyectos["Nombre corto proyecto"].dropna().astype(str).str.strip().tolist())
    available_projects.extend(estado["Proyecto"].dropna().astype(str).str.strip().tolist())
    seen = set()
    project_list = []
    for name in available_projects:
        if name and name not in seen:
            seen.add(name)
            project_list.append(name)
    if not project_list:
        project_list = ["Proyecto demo"]

    return {
        "estado": estado,
        "tareas": tareas,
        "desplegables": desplegables,
        "calendario": calendario,
        "helper": helper,
        "stages": stage_catalog,
        "task_catalog": task_catalog,
        "projects": project_list,
        "sheet_names": raw["sheet_names"],
    }



def create_placeholder_tasks(stage_name):
    base = title_case_safe(stage_name)
    return pd.DataFrame(
        {
            "Id tarea": [f"{base[:3].upper()}-A", f"{base[:3].upper()}-B"],
            "orden": [1, 2],
            "categoria 1": [stage_name, stage_name],
            "categoria_norm": [normalize_text(stage_name), normalize_text(stage_name)],
            "Asunto breve": [f"Inicio de {base}", f"Cierre de {base}"],
            "asunto_norm": [normalize_text(f"Inicio de {base}"), normalize_text(f"Cierre de {base}")],
        }
    )



def planned_duration(index_in_stage):
    return 2 if index_in_stage % 4 == 0 else 1



def choose_current_project(estado_df, project_names):
    if estado_df.empty:
        return project_names[0]
    last_dates = (
        estado_df.groupby("Proyecto", dropna=True)["Fecha"]
        .max()
        .reset_index()
        .sort_values("Fecha", ascending=False)
    )
    if last_dates.empty:
        return project_names[0]
    return str(last_dates.iloc[0]["Proyecto"])



def build_demo_schedule(prepared):
    helper = prepared["helper"]
    estado = prepared["estado"]
    stages = prepared["stages"]
    task_catalog = prepared["task_catalog"]
    project_names = prepared["projects"]

    current_project = choose_current_project(estado, project_names)
    milestone_rows = []
    stage_rows = []

    for project_name in project_names:
        project_events = estado[estado["Proyecto"].astype(str).str.strip() == project_name].copy()
        if project_events.empty:
            seed_date = helper.workdays[0]
        else:
            seed_date = helper.next_working_day(project_events["Fecha"].min())

        by_task = (
            project_events.dropna(subset=["tarea_norm", "Fecha"])
            .groupby("tarea_norm", dropna=False)["Fecha"]
            .min()
            .to_dict()
        )
        by_asunto = (
            project_events.dropna(subset=["asunto_norm", "Fecha"])
            .groupby("asunto_norm", dropna=False)["Fecha"]
            .min()
            .to_dict()
        )

        planned_cursor = seed_date
        last_completed_real_end = project_events["Fecha"].max() if not project_events.empty else seed_date
        current_project_delay = 2 if project_name == current_project else 1
        first_missing_seen = False
        stage_delay_applied = False

        for stage_name in stages:
            stage_norm = normalize_text(stage_name)
            stage_tasks = task_catalog[task_catalog["categoria_norm"] == stage_norm].copy()
            if stage_tasks.empty:
                stage_tasks = create_placeholder_tasks(stage_name)
            stage_tasks = stage_tasks.sort_values(["orden", "Id tarea", "Asunto breve"]).reset_index(drop=True)

            stage_plan_start = None
            stage_plan_end = None
            stage_real_start = None
            stage_real_end = None
            stage_statuses = []

            for idx, row in stage_tasks.iterrows():
                duration_days = planned_duration(idx)
                plan_start = helper.next_working_day(planned_cursor)
                plan_end = helper.add_working_days(plan_start, duration_days)
                planned_cursor = helper.add_working_days(plan_end, 0)

                task_key = normalize_text(row.get("Id tarea"))
                subject_key = normalize_text(row.get("Asunto breve"))
                observed_end = by_task.get(task_key) or by_asunto.get(subject_key)

                if observed_end is not None and not pd.isna(observed_end):
                    observed_end = helper.next_working_day(observed_end)
                    real_end = observed_end
                    real_start = helper.previous_working_day(real_end, max(duration_days - 1, 0))
                    status = "Completado"
                    observed_flag = True
                    last_completed_real_end = max(last_completed_real_end, real_end)
                else:
                    observed_flag = False
                    if not first_missing_seen:
                        status = "En curso"
                        real_start = helper.add_working_days(max(last_completed_real_end, plan_start), current_project_delay)
                        real_end = helper.add_working_days(real_start, duration_days)
                        first_missing_seen = True
                        stage_delay_applied = True
                    else:
                        status = "Pendiente"
                        base_start = max(last_completed_real_end, plan_start)
                        carry_delay = current_project_delay if stage_delay_applied else 0
                        real_start = helper.add_working_days(base_start, carry_delay)
                        real_end = helper.add_working_days(real_start, duration_days)
                    last_completed_real_end = max(last_completed_real_end, real_end)

                delay_days = helper.business_days_between(plan_end, real_end)

                stage_plan_start = plan_start if stage_plan_start is None else min(stage_plan_start, plan_start)
                stage_plan_end = plan_end if stage_plan_end is None else max(stage_plan_end, plan_end)
                stage_real_start = real_start if stage_real_start is None else min(stage_real_start, real_start)
                stage_real_end = real_end if stage_real_end is None else max(stage_real_end, real_end)
                stage_statuses.append(status)

                milestone_rows.append(
                    {
                        "Proyecto": project_name,
                        "Etapa": stage_name,
                        "Etapa normalizada": stage_norm,
                        "Id tarea": row.get("Id tarea", ""),
                        "Hito": row.get("Asunto breve", ""),
                        "Duración programada (días hábiles)": duration_days,
                        "Fecha inicio proyectada": plan_start,
                        "Fecha fin proyectada": plan_end,
                        "Fecha inicio real": real_start,
                        "Fecha fin real": real_end,
                        "Atraso (días hábiles)": delay_days,
                        "Estado": status,
                        "Completado observado": observed_flag,
                    }
                )

            if all(value == "Completado" for value in stage_statuses):
                stage_status = "Completada"
            elif "En curso" in stage_statuses:
                stage_status = "En curso"
            elif any(value == "Completado" for value in stage_statuses):
                stage_status = "En curso"
            elif stage_delay_applied:
                stage_status = "Retrasada"
            else:
                stage_status = "No iniciada"

            stage_rows.append(
                {
                    "Proyecto": project_name,
                    "Etapa": stage_name,
                    "Fecha inicio proyectada": stage_plan_start,
                    "Fecha fin proyectada": stage_plan_end,
                    "Fecha inicio real": stage_real_start,
                    "Fecha fin real": stage_real_end,
                    "Atraso (días hábiles)": helper.business_days_between(stage_plan_end, stage_real_end),
                    "Estado etapa": stage_status,
                    "Hitos en etapa": len(stage_tasks),
                }
            )

    milestones = pd.DataFrame(milestone_rows)
    stages_df = pd.DataFrame(stage_rows)

    summary_rows = []
    for project_name, group in milestones.groupby("Proyecto"):
        stage_progress = stages_df[stages_df["Proyecto"] == project_name].copy()
        first_open_stage = stage_progress.loc[stage_progress["Estado etapa"] != "Completada", "Etapa"]
        current_stage = first_open_stage.iloc[0] if not first_open_stage.empty else stage_progress.iloc[-1]["Etapa"]

        total_tasks = len(group)
        completed = int((group["Estado"] == "Completado").sum())
        in_progress = int((group["Estado"] == "En curso").sum())
        pending = int((group["Estado"] == "Pendiente").sum())
        progress_pct = round(((completed + 0.5 * in_progress) / total_tasks) * 100, 1) if total_tasks else 0.0

        if completed == 0 and in_progress == 0:
            project_status = "No iniciado"
        elif pending == 0 and in_progress == 0:
            project_status = "Completado"
        elif stage_progress["Atraso (días hábiles)"].fillna(0).max() > 0:
            project_status = "Retrasado"
        else:
            project_status = "En curso"

        summary_rows.append(
            {
                "Proyecto": project_name,
                "Etapa actual": current_stage,
                "Fecha inicio proyectada": group["Fecha inicio proyectada"].min(),
                "Fecha fin proyectada": group["Fecha fin proyectada"].max(),
                "Fecha inicio real": group["Fecha inicio real"].min(),
                "Fecha fin real": group.loc[group["Estado"] == "Completado", "Fecha fin real"].max(),
                "Fecha fin real estimada": group["Fecha fin real"].max(),
                "Tareas completadas": completed,
                "Tareas en curso": in_progress,
                "Tareas pendientes": pending,
                "% avance": progress_pct,
                "Estado proyecto": project_status,
                "Atraso total (días hábiles)": helper.business_days_between(
                    group["Fecha fin proyectada"].max(), group["Fecha fin real"].max()
                ),
            }
        )

    project_summary = pd.DataFrame(summary_rows)
    return milestones, stages_df, project_summary, current_project



def format_date(value):
    if pd.isna(value):
        return "—"
    return pd.Timestamp(value).strftime("%d/%m/%Y")



def filter_data(milestones, stages_df, summary_df):
    st.sidebar.header("Filtros")
    projects = sorted(summary_df["Proyecto"].dropna().unique().tolist())
    stages = sorted(stages_df["Etapa"].dropna().unique().tolist())
    states = sorted(summary_df["Estado proyecto"].dropna().unique().tolist())

    selected_projects = st.sidebar.multiselect("Proyecto", options=projects, default=projects)
    selected_stages = st.sidebar.multiselect("Etapa", options=stages, default=stages)
    selected_states = st.sidebar.multiselect("Estado del proyecto", options=states, default=states)

    date_min = pd.to_datetime(milestones["Fecha inicio proyectada"].min()).date()
    date_max = pd.to_datetime(milestones["Fecha fin real"].max()).date()
    selected_range = st.sidebar.date_input(
        "Rango de fechas",
        value=(date_min, date_max),
        min_value=date_min,
        max_value=date_max,
    )
    if isinstance(selected_range, tuple) and len(selected_range) == 2:
        start_date, end_date = selected_range
    else:
        start_date, end_date = date_min, date_max

    summary_filtered = summary_df[
        summary_df["Proyecto"].isin(selected_projects)
        & summary_df["Estado proyecto"].isin(selected_states)
    ].copy()

    milestones_filtered = milestones[
        milestones["Proyecto"].isin(summary_filtered["Proyecto"])
        & milestones["Etapa"].isin(selected_stages)
        & (milestones["Fecha inicio proyectada"].dt.date >= start_date)
        & (milestones["Fecha fin real"].dt.date <= end_date)
    ].copy()

    stages_filtered = stages_df[
        stages_df["Proyecto"].isin(summary_filtered["Proyecto"])
        & stages_df["Etapa"].isin(selected_stages)
        & (stages_df["Fecha inicio proyectada"].dt.date >= start_date)
        & (stages_df["Fecha fin real"].dt.date <= end_date)
    ].copy()

    valid_projects = milestones_filtered["Proyecto"].unique().tolist()
    summary_filtered = summary_filtered[summary_filtered["Proyecto"].isin(valid_projects)].copy()
    return milestones_filtered, stages_filtered, summary_filtered



def add_kpis(summary_df, milestones_df):
    total_projects = len(summary_df)
    total_tasks = len(milestones_df)
    avg_progress = round(summary_df["% avance"].mean(), 1) if not summary_df.empty else 0.0
    delayed_projects = int((summary_df["Estado proyecto"] == "Retrasado").sum()) if not summary_df.empty else 0
    completed_tasks = int((milestones_df["Estado"] == "Completado").sum()) if not milestones_df.empty else 0
    pending_tasks = int((milestones_df["Estado"] == "Pendiente").sum()) if not milestones_df.empty else 0

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Proyectos", total_projects)
    c2.metric("Tareas / hitos", total_tasks)
    c3.metric("Avance promedio", f"{avg_progress}%")
    c4.metric("Proyectos retrasados", delayed_projects)
    c5.metric("Tareas completadas", completed_tasks)
    c6.metric("Tareas pendientes", pending_tasks)



def chart_progress(summary_df):
    if summary_df.empty:
        return go.Figure()
    data = summary_df.sort_values("% avance", ascending=True)
    fig = px.bar(
        data,
        x="% avance",
        y="Proyecto",
        orientation="h",
        text="% avance",
        title="Avance por proyecto",
    )
    fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
    fig.update_layout(height=max(360, 90 + 70 * len(data)), xaxis_title="% avance", yaxis_title="")
    return fig



def chart_tasks_stack(summary_df):
    if summary_df.empty:
        return go.Figure()
    data = summary_df[["Proyecto", "Tareas completadas", "Tareas en curso", "Tareas pendientes"]].melt(
        id_vars="Proyecto", var_name="Tipo", value_name="Cantidad"
    )
    fig = px.bar(
        data,
        x="Proyecto",
        y="Cantidad",
        color="Tipo",
        title="Tareas completadas vs en curso vs pendientes",
    )
    fig.update_layout(height=max(360, 100 + 60 * summary_df.shape[0]), xaxis_title="", yaxis_title="N° de tareas")
    return fig



def chart_project_status(summary_df):
    if summary_df.empty:
        return go.Figure()
    status_counts = summary_df["Estado proyecto"].value_counts().reset_index()
    status_counts.columns = ["Estado", "Cantidad"]
    fig = px.pie(status_counts, names="Estado", values="Cantidad", hole=0.58, title="Estado de proyectos")
    fig.update_layout(height=360)
    return fig



def chart_timeline_burndown(milestones_df):
    if milestones_df.empty:
        return go.Figure()
    planned = (
        milestones_df.groupby("Fecha fin proyectada", dropna=True)
        .size()
        .sort_index()
        .cumsum()
        .reset_index(name="Programado acumulado")
    )
    real = (
        milestones_df.groupby("Fecha fin real", dropna=True)
        .size()
        .sort_index()
        .cumsum()
        .reset_index(name="Real acumulado")
    )
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=planned["Fecha fin proyectada"], y=planned["Programado acumulado"], mode="lines+markers", name="Programado"))
    fig.add_trace(go.Scatter(x=real["Fecha fin real"], y=real["Real acumulado"], mode="lines+markers", name="Real / demo"))
    fig.update_layout(title="Curva acumulada de hitos", height=360, xaxis_title="Fecha", yaxis_title="Hitos acumulados")
    return fig



def chart_stage_heatmap(milestones_df):
    if milestones_df.empty:
        return go.Figure()
    matrix = (
        milestones_df.pivot_table(index="Etapa", columns="Estado", values="Id tarea", aggfunc="count", fill_value=0)
        .reset_index()
    )
    heat = matrix.set_index("Etapa")
    fig = px.imshow(
        heat,
        text_auto=True,
        aspect="auto",
        title="Heatmap de hitos por etapa y estado",
        labels=dict(x="Estado", y="Etapa", color="Cantidad"),
    )
    fig.update_layout(height=max(360, 80 + 45 * heat.shape[0]))
    return fig



def chart_delay_by_stage(stages_df):
    if stages_df.empty:
        return go.Figure()
    data = stages_df.sort_values("Atraso (días hábiles)", ascending=False)
    fig = px.bar(
        data,
        x="Atraso (días hábiles)",
        y="Etapa",
        color="Estado etapa",
        orientation="h",
        title="Retraso por etapa",
    )
    fig.update_layout(height=max(360, 80 + 50 * len(data)), xaxis_title="Días hábiles", yaxis_title="")
    return fig



def chart_stage_load(milestones_df):
    if milestones_df.empty:
        return go.Figure()
    data = milestones_df.groupby("Etapa", dropna=True).size().reset_index(name="Hitos")
    data = data.sort_values("Hitos", ascending=False)
    fig = px.bar(data, x="Etapa", y="Hitos", title="Carga de hitos por etapa")
    fig.update_layout(height=360, xaxis_title="", yaxis_title="N° de hitos")
    return fig



def chart_documents_over_time(estado_df, selected_projects):
    docs = estado_df[estado_df["Proyecto"].isin(selected_projects)].copy()
    if docs.empty:
        return go.Figure()
    docs = docs.groupby("Fecha", dropna=True).size().reset_index(name="Documentos")
    fig = px.bar(docs, x="Fecha", y="Documentos", title="Documentos registrados por fecha")
    fig.update_layout(height=360, xaxis_title="Fecha", yaxis_title="Documentos")
    return fig



def chart_top_senders(estado_df, selected_projects):
    docs = estado_df[estado_df["Proyecto"].isin(selected_projects)].copy()
    if docs.empty or "Remitente" not in docs.columns:
        return go.Figure()
    docs = docs.groupby("Remitente", dropna=True).size().reset_index(name="Documentos")
    docs = docs.sort_values("Documentos", ascending=False).head(10)
    fig = px.bar(docs, x="Documentos", y="Remitente", orientation="h", title="Top remitentes")
    fig.update_layout(height=360, yaxis_title="", xaxis_title="Documentos")
    return fig



def create_gantt_stage_chart(stages_df):
    if stages_df.empty:
        return go.Figure()
    gantt = pd.concat(
        [
            stages_df.assign(Cronograma="Programado", Inicio=stages_df["Fecha inicio proyectada"], Fin=stages_df["Fecha fin proyectada"]),
            stages_df.assign(Cronograma="Real", Inicio=stages_df["Fecha inicio real"], Fin=stages_df["Fecha fin real"]),
        ],
        ignore_index=True,
    )
    fig = px.timeline(
        gantt,
        x_start="Inicio",
        x_end="Fin",
        y="Etapa",
        color="Cronograma",
        hover_data=["Proyecto", "Estado etapa", "Atraso (días hábiles)"],
        title="Gantt ejecutivo por etapas: programado vs real",
    )
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(height=max(420, 120 + 55 * len(stages_df)))
    return fig



def create_gantt_milestone_chart(milestones_df):
    if milestones_df.empty:
        return go.Figure()
    gantt = pd.concat(
        [
            milestones_df.assign(Cronograma="Programado", Inicio=milestones_df["Fecha inicio proyectada"], Fin=milestones_df["Fecha fin proyectada"]),
            milestones_df.assign(Cronograma="Real", Inicio=milestones_df["Fecha inicio real"], Fin=milestones_df["Fecha fin real"]),
        ],
        ignore_index=True,
    )
    gantt["Etiqueta"] = gantt["Etapa"] + " · " + gantt["Hito"]
    fig = px.timeline(
        gantt,
        x_start="Inicio",
        x_end="Fin",
        y="Etiqueta",
        color="Cronograma",
        hover_data=["Proyecto", "Etapa", "Id tarea", "Estado", "Atraso (días hábiles)"],
        title="Gantt detallado por hitos: programado vs real",
    )
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(height=min(1400, max(500, 180 + 26 * len(milestones_df))))
    return fig



def create_delay_scatter(milestones_df):
    if milestones_df.empty:
        return go.Figure()
    fig = px.scatter(
        milestones_df,
        x="Fecha fin proyectada",
        y="Atraso (días hábiles)",
        color="Estado",
        size="Duración programada (días hábiles)",
        hover_data=["Proyecto", "Etapa", "Hito", "Id tarea"],
        title="Dispersión de retrasos por hito",
    )
    fig.update_layout(height=360)
    return fig



def render_summary_table(summary_df):
    if summary_df.empty:
        st.info("No hay proyectos para mostrar con los filtros actuales.")
        return
    display = summary_df.copy()
    for col in [
        "Fecha inicio proyectada",
        "Fecha fin proyectada",
        "Fecha inicio real",
        "Fecha fin real",
        "Fecha fin real estimada",
    ]:
        display[col] = display[col].apply(format_date)
    display = display.rename(columns={"% avance": "Avance %"})
    st.dataframe(display, use_container_width=True, hide_index=True)



def render_milestone_table(milestones_df):
    if milestones_df.empty:
        st.info("No hay hitos para mostrar con los filtros actuales.")
        return
    display = milestones_df.copy()
    for col in [
        "Fecha inicio proyectada",
        "Fecha fin proyectada",
        "Fecha inicio real",
        "Fecha fin real",
    ]:
        display[col] = display[col].apply(format_date)
    st.dataframe(display, use_container_width=True, hide_index=True, height=520)



def get_default_excel_path():
    script_dir = Path(__file__).resolve().parent
    return str(script_dir / DEFAULT_EXCEL_FILENAME)


def main():
    st.markdown(f"<div class='main-title'>{PAGE_TITLE}</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='subtitle'>Prueba de concepto para seguimiento de proyectos, documentos, etapas e hitos con cronograma programado vs real.</div>",
        unsafe_allow_html=True,
    )

    st.sidebar.header("Fuente de datos")
    uploaded_file = st.sidebar.file_uploader("Subir Excel (.xlsx / .xlsm)", type=["xlsx", "xlsm"])
    excel_path = st.sidebar.text_input(
        "Ruta local del Excel",
        value=get_default_excel_path(),
        help="Por defecto, el dashboard busca el archivo OXI ESTADO.xlsm en la misma carpeta donde está este script.",
    )

    try:
        if uploaded_file is not None:
            raw = load_data_from_bytes(uploaded_file.getvalue())
            source_label = uploaded_file.name
        else:
            raw = load_data_from_path(excel_path)
            source_label = excel_path
    except Exception as exc:
        st.error(f"No se pudo leer el Excel: {exc}")
        st.stop()

    try:
        prepared = prepare_data(raw)
        milestones, stages_df, summary_df, current_project = build_demo_schedule(prepared)
    except Exception as exc:
        st.error(f"No se pudo transformar la información: {exc}")
        st.stop()

    st.sidebar.caption(f"Archivo cargado: {source_label}")
    st.sidebar.caption("Sugerencia: coloca OXI ESTADO.xlsm en la misma carpeta que este .py para no depender de rutas largas.")
    st.sidebar.caption(f"Hojas detectadas: {', '.join(prepared['sheet_names'])}")
    st.sidebar.info(
        f"La demo usa los datos reales disponibles y completa los faltantes con fechas consistentes. El proyecto más reciente se marca con un retraso controlado de 2 días hábiles: {current_project}."
    )

    milestones_f, stages_f, summary_f = filter_data(milestones, stages_df, summary_df)
    selected_projects = summary_f["Proyecto"].tolist()
    estado_df = prepared["estado"]

    add_kpis(summary_f, milestones_f)

    tab1, tab2, tab3, tab4 = st.tabs(["Resumen ejecutivo", "Gantt y cronograma", "Documentos e hitos", "Datos base"])

    with tab1:
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(chart_progress(summary_f), use_container_width=True)
            st.plotly_chart(chart_project_status(summary_f), use_container_width=True)
            st.plotly_chart(chart_stage_heatmap(milestones_f), use_container_width=True)
        with c2:
            st.plotly_chart(chart_tasks_stack(summary_f), use_container_width=True)
            st.plotly_chart(chart_timeline_burndown(milestones_f), use_container_width=True)
            st.plotly_chart(chart_delay_by_stage(stages_f), use_container_width=True)

        st.markdown("### Resumen de proyectos")
        render_summary_table(summary_f)

    with tab2:
        st.plotly_chart(create_gantt_stage_chart(stages_f), use_container_width=True)
        st.plotly_chart(create_gantt_milestone_chart(milestones_f), use_container_width=True)
        st.plotly_chart(create_delay_scatter(milestones_f), use_container_width=True)

    with tab3:
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(chart_stage_load(milestones_f), use_container_width=True)
            st.plotly_chart(chart_documents_over_time(estado_df, selected_projects), use_container_width=True)
        with c2:
            st.plotly_chart(chart_top_senders(estado_df, selected_projects), use_container_width=True)

        st.markdown("### Detalle de hitos")
        render_milestone_table(milestones_f)

    with tab4:
        st.markdown("### Vista de datos transformados")
        st.markdown("**Resumen de proyectos**")
        render_summary_table(summary_f)
        st.markdown("**Etapas**")
        st.dataframe(stages_f, use_container_width=True, hide_index=True, height=360)
        st.markdown("**Hitos**")
        render_milestone_table(milestones_f)


if __name__ == "__main__":
    main()

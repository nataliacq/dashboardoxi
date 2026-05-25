from datetime import datetime
from time import time
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

SHEET_ID = "1s05TfnAHtRQpnjX0iwOcLsWVX1rCfz_v"
CALENDAR_CSV = Path(__file__).with_name("month_weeks_2020_2030.csv")


def _csv_url() -> str:
    return (
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
        f"/export?format=csv&_t={int(time() * 1000)}"
    )


def cargar_hoja() -> pd.DataFrame:
    df = pd.read_csv(_csv_url(), skiprows=[1])
    df.columns = df.columns.str.strip()
    df = df.loc[:, ~df.columns.str.startswith("Unnamed")]
    df = df.loc[:, df.columns != ""]
    return df


@st.cache_data
def cargar_calendario_semanas() -> pd.DataFrame:
    df = pd.read_csv(CALENDAR_CSV)
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    return df


def find_col(df: pd.DataFrame, *candidatos: str) -> str:
    import unicodedata

    def norm(s: str) -> str:
        s = unicodedata.normalize("NFKD", str(s))
        return "".join(c for c in s if not unicodedata.combining(c)).strip().lower()

    cols_norm = {norm(c): c for c in df.columns}
    for cand in candidatos:
        cand_norm = norm(cand)
        if cand_norm in cols_norm:
            return cols_norm[cand_norm]
        for norm_col, real_col in cols_norm.items():
            if norm_col.startswith(cand_norm):
                return real_col
    raise KeyError(f"Ninguna de {candidatos} encontrada en {list(df.columns)}")


def elegir_columna_proyecto(df: pd.DataFrame) -> str:
    candidatos = [
        "Proyecto",
        "Proyecto nombre corto",
        "Nombre proyecto",
        "Nombre fase",
        "Fase",
        "Id fase",
    ]
    columnas = list(df.columns)
    for candidato in candidatos:
        for col in columnas:
            if str(col).strip().lower() == candidato.strip().lower():
                return col
    return columnas[0]


def parse_fecha(serie: pd.Series) -> pd.Series:
    return pd.to_datetime(serie, dayfirst=True, errors="coerce")


def count_business_days(start, end) -> int | None:
    if pd.isna(start) or pd.isna(end):
        return None
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    if end_ts < start_ts:
        return 0
    return len(pd.bdate_range(start_ts, end_ts))


def truncate_text(value: str, max_chars: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def lighten_color(hex_color: str, factor: float = 0.55) -> str:
    r, g, b = hex_to_rgb(hex_color)
    new_rgb = (
        int(r + (255 - r) * factor),
        int(g + (255 - g) * factor),
        int(b + (255 - b) * factor),
    )
    return rgb_to_hex(new_rgb)


def day_num(value) -> float | None:
    if pd.isna(value):
        return None
    return float(pd.Timestamp(value).toordinal())


def add_period_trace(
    fig: go.Figure,
    label: str,
    start,
    end,
    y0: float,
    y1: float,
    fill_color: str,
    line_color: str,
    hover_label: str,
    visible_start: float,
    visible_end: float,
):
    if pd.isna(start) or pd.isna(end):
        return

    start_num = day_num(start)
    end_num = day_num(end)

    if end_num < visible_start or start_num > visible_end:
        return

    clipped_start = max(start_num, visible_start)
    clipped_end = min(end_num, visible_end)
    center_y = (y0 + y1) / 2

    if start_num == end_num:
        if not (visible_start <= start_num <= visible_end):
            return
        fig.add_trace(
            go.Scatter(
                x=[start_num],
                y=[center_y],
                mode="markers",
                marker=dict(size=11, color=fill_color, line=dict(color=line_color, width=1)),
                showlegend=False,
                hovertemplate=(
                    f"<b>{label}</b><br>{hover_label}: {start.strftime('%d/%m/%Y')}"
                    "<extra></extra>"
                ),
            )
        )
        return

    fig.add_shape(
        type="rect",
        x0=clipped_start,
        x1=clipped_end,
        y0=y0,
        y1=y1,
        fillcolor=fill_color,
        line=dict(width=0),
        layer="above",
    )

    center_x = clipped_start + (clipped_end - clipped_start) / 2
    fig.add_trace(
        go.Scatter(
            x=[center_x],
            y=[center_y],
            mode="markers",
            marker=dict(size=18, color="rgba(0,0,0,0)"),
            showlegend=False,
            hovertemplate=(
                f"<b>{label}</b><br>{hover_label}: {start.strftime('%d/%m/%Y')} -> "
                f"{end.strftime('%d/%m/%Y')}<extra></extra>"
            ),
        )
    )


def add_highlight_business_window(
    fig: go.Figure,
    start,
    business_days: int,
    y0: float,
    y1: float,
    fill_color: str,
    visible_start: float,
    visible_end: float,
    label: str,
):
    if pd.isna(start):
        return

    start_ts = pd.Timestamp(start)
    end_ts = start_ts + pd.tseries.offsets.BDay(max(business_days - 1, 0))
    start_num = day_num(start_ts)
    end_num = day_num(end_ts)

    if end_num < visible_start or start_num > visible_end:
        return

    clipped_start = max(start_num, visible_start)
    clipped_end = min(end_num, visible_end)
    fig.add_shape(
        type="rect",
        x0=clipped_start,
        x1=clipped_end,
        y0=y0,
        y1=y1,
        fillcolor=fill_color,
        line=dict(width=0),
        layer="above",
    )
    center_x = clipped_start + (clipped_end - clipped_start) / 2
    center_y = (y0 + y1) / 2
    fig.add_trace(
        go.Scatter(
            x=[center_x],
            y=[center_y],
            mode="markers",
            marker=dict(size=18, color="rgba(0,0,0,0)"),
            showlegend=False,
            hovertemplate=(
                f"<b>{label}</b><br>Plazo maximo: "
                f"{start_ts.strftime('%d/%m/%Y')} -> {end_ts.strftime('%d/%m/%Y')}"
                "<extra></extra>"
            ),
        )
    )


st.set_page_config(page_title="Estado OXI", layout="wide")
st.title("Estado OXI")

if st.sidebar.button("Actualizar"):
    st.rerun()

try:
    with st.spinner("Cargando datos desde Google Sheets..."):
        df = cargar_hoja()
    st.caption(f"Ultima carga: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
except Exception as exc:
    st.error(f"No se pudo cargar el Google Sheet: {exc}")
    st.stop()

if df.empty:
    st.warning("La hoja no tiene filas para mostrar.")
    st.stop()

try:
    calendar_df = cargar_calendario_semanas()
except Exception as exc:
    st.error(f"No se pudo cargar el calendario de semanas: {exc}")
    st.stop()

tab_estado, tab_resumen = st.tabs(["Estado por proyecto", "Resumen de proyectos"])

with tab_estado:
    st.subheader("Estado por proyecto")
    col_proyecto = elegir_columna_proyecto(df)
    valores = df[col_proyecto].dropna().astype(str).str.strip()
    valores = sorted([v for v in valores.unique().tolist() if v])

    if not valores:
        st.warning(f"No hay valores para mostrar en '{col_proyecto}'.")
        st.stop()

    default_project = "villa sur"
    default_index = 0
    for i, value in enumerate(valores):
        if value.strip().lower() == default_project:
            default_index = i
            break

    proyecto_sel = st.selectbox("Proyecto", valores, index=default_index)
    df_filtrado = df[df[col_proyecto].astype(str).str.strip() == proyecto_sel].copy()
    st.caption(f"Columna usada: {col_proyecto}")

    try:
        col_fase = find_col(df_filtrado, "Nombre fase", "Fase")
        col_tarea = find_col(df_filtrado, "Tarea")
        col_solicitante = find_col(df_filtrado, "Solicitante")
        col_destinatario = find_col(df_filtrado, "Destiantario", "Destinatario")
        col_real_inicio = find_col(df_filtrado, "Fecha solicitud")
        col_real_fin = find_col(df_filtrado, "Fecha recepcion", "Fecha recepción")
        col_proj_inicio = find_col(
            df_filtrado,
            "Fecha solicitud proyectado actualizado MAX",
            "Fecha solicitud proyectado actualizado.1",
            "Fecha solicitud proyectado actualizado",
        )
        col_proj_fin = find_col(
            df_filtrado,
            "Fecha recepcion proyectado actualizado MAX",
            "Fecha recepción proyectado actualizado MAX",
            "Fecha recepcion proyectado actualizado.1",
            "Fecha recepcion proyectado actualizado",
        )
    except KeyError as exc:
        st.error(f"Faltan columnas para construir el Gantt: {exc}")
        st.stop()

    for col in [col_real_inicio, col_real_fin, col_proj_inicio, col_proj_fin]:
        df_filtrado[col] = parse_fecha(df_filtrado[col])

    resumen_df = df_filtrado.copy()
    resumen_df["_dur_real"] = resumen_df.apply(
        lambda r: count_business_days(r.get(col_real_inicio), r.get(col_real_fin)), axis=1
    )
    resumen_df["_dur_proj"] = resumen_df.apply(
        lambda r: count_business_days(r.get(col_proj_inicio), r.get(col_proj_fin)), axis=1
    )

    inicio_real = resumen_df[col_real_inicio].dropna().min()
    fin_real = resumen_df[col_real_fin].dropna().max()
    fin_proyectado = resumen_df[col_proj_fin].dropna().max()

    fase_actual = "-"
    fase_actual_df = resumen_df.copy()
    fase_actual_df["_fase_nombre"] = (
        fase_actual_df[col_fase].fillna("").astype(str).str.strip().replace("", "Sin fase")
    )
    fase_actual_df["_fecha_ref"] = fase_actual_df[col_real_fin]
    fase_actual_df["_fecha_ref"] = fase_actual_df["_fecha_ref"].fillna(fase_actual_df[col_real_inicio])
    fase_actual_df["_fecha_ref"] = fase_actual_df["_fecha_ref"].fillna(fase_actual_df[col_proj_fin])
    fase_actual_df["_fecha_ref"] = fase_actual_df["_fecha_ref"].fillna(fase_actual_df[col_proj_inicio])
    fase_actual_df = fase_actual_df.dropna(subset=["_fecha_ref"]).sort_values("_fecha_ref")
    if not fase_actual_df.empty:
        fase_actual = str(fase_actual_df.iloc[-1]["_fase_nombre"]).strip() or "-"

    dias_retraso = None
    if pd.notna(fin_real) and pd.notna(fin_proyectado) and fin_real > fin_proyectado:
        dias_retraso = count_business_days(fin_proyectado, fin_real)

    def fmt_fecha(value) -> str:
        if pd.isna(value):
            return "-"
        return pd.Timestamp(value).strftime("%d/%m/%Y")

    metric_cols = st.columns(5)
    metric_cols[0].metric("Fase actual", fase_actual)
    metric_cols[1].metric("Inicio real", fmt_fecha(inicio_real))
    metric_cols[2].metric("Fin real", fmt_fecha(fin_real))
    metric_cols[3].metric("Fin proyectado", fmt_fecha(fin_proyectado))
    metric_cols[4].metric("Dias de retraso", dias_retraso if dias_retraso is not None else "-")

    fase_counts = (
        resumen_df[col_fase]
        .fillna("Sin fase")
        .astype(str)
        .str.strip()
        .replace("", "Sin fase")
        .value_counts()
        .head(8)
        .reset_index()
    )
    fase_counts.columns = ["Fase", "Cantidad"]

    chart_col1 = st.columns(1)[0]
    with chart_col1:
        fig_fases = go.Figure(
            go.Bar(
                x=fase_counts["Cantidad"],
                y=fase_counts["Fase"],
                orientation="h",
                marker_color="#2D8CFF",
            )
        )
        fig_fases.update_layout(
            title="Tareas por fase",
            height=280,
            margin=dict(l=10, r=10, t=40, b=10),
            paper_bgcolor="white",
            plot_bgcolor="white",
            xaxis=dict(showgrid=True, gridcolor="#E5E7EB"),
            yaxis=dict(autorange="reversed"),
        )
        st.plotly_chart(fig_fases, use_container_width=True)

    subtab_inicial, subtab_actualizada = st.tabs(
        ["Proyeccion inicial", "Proyeccion actualizada"]
    )

    fase_series = df_filtrado[col_fase].fillna("").astype(str).str.strip()
    fase_series = fase_series.where(fase_series != "", "Sin fase")
    df_filtrado["_fase_plot"] = fase_series

    rows = []
    fases = []
    for fase in df_filtrado["_fase_plot"].tolist():
        if fase not in fases:
            fases.append(fase)

    for fase in fases:
        subfase = df_filtrado[df_filtrado["_fase_plot"] == fase].copy()

        phase_real_start = subfase[col_real_inicio].dropna().min()
        phase_real_end = subfase[col_real_fin].dropna().max()
        phase_proj_start = subfase[col_proj_inicio].dropna().min()
        phase_proj_end = subfase[col_proj_fin].dropna().max()

        if not (
            pd.isna(phase_real_start)
            and pd.isna(phase_real_end)
            and pd.isna(phase_proj_start)
            and pd.isna(phase_proj_end)
        ):
            rows.append(
                {
                    "kind": "phase",
                    "label": fase,
                    "tarea": fase.upper(),
                    "solicitante": "",
                    "destinatario": "",
                    "real_inicio": phase_real_start,
                    "real_fin": phase_real_end,
                    "proj_inicio": phase_proj_start,
                    "proj_fin": phase_proj_end,
                }
            )

        for _, item in subfase.iterrows():
            tarea = str(item.get(col_tarea, "")).strip() or "Sin tarea"
            solicitante = str(item.get(col_solicitante, "")).strip()
            destinatario = str(item.get(col_destinatario, "")).strip()
            real_inicio = item.get(col_real_inicio)
            real_fin = item.get(col_real_fin)
            proj_inicio = item.get(col_proj_inicio)
            proj_fin = item.get(col_proj_fin)

            if (
                pd.isna(real_inicio)
                and pd.isna(real_fin)
                and pd.isna(proj_inicio)
                and pd.isna(proj_fin)
            ):
                continue

            rows.append(
                {
                    "kind": "task",
                    "label": tarea,
                    "tarea": tarea,
                    "solicitante": solicitante,
                    "destinatario": destinatario,
                    "real_inicio": real_inicio,
                    "real_fin": real_fin,
                    "proj_inicio": proj_inicio,
                    "proj_fin": proj_fin,
                }
            )

    if not rows:
        st.info("No hay fechas suficientes para mostrar el Gantt de este proyecto.")
        st.stop()

    n = len(rows)
    for i, row in enumerate(rows):
        row["y"] = n - 1 - i

    phase_palette = [
        "#2563EB",
        "#0F766E",
        "#CA8A04",
        "#9333EA",
        "#DC2626",
        "#EA580C",
        "#0891B2",
        "#4F46E5",
        "#BE185D",
        "#15803D",
    ]
    phase_colors: dict[str, str] = {}
    palette_idx = 0
    current_phase = None
    for row in rows:
        if row["kind"] == "phase":
            current_phase = row["label"]
            if current_phase not in phase_colors:
                phase_colors[current_phase] = phase_palette[palette_idx % len(phase_palette)]
                palette_idx += 1
        row["phase_name"] = current_phase or row["label"]

    date_values = []
    for row in rows:
        for key in ["real_inicio", "real_fin", "proj_inicio", "proj_fin"]:
            if pd.notna(row[key]):
                date_values.append(pd.Timestamp(row[key]))

    date_min = min(date_values)
    date_max = max(date_values)
    date_min_num = day_num(date_min)
    date_max_num = day_num(date_max)
    date_span = max(date_max_num - date_min_num, 1)
    total_start = int(date_min_num)
    total_end = int(date_max_num)
    total_days = max(total_end - total_start + 1, 1)

    default_window = 60
    if total_days <= 45:
        default_window = total_days
    elif total_days <= 60:
        default_window = 60
    elif total_days <= 90:
        default_window = 90
    else:
        default_window = 120

    window_options = [30, 45, 60, 90, 120, 180]
    if total_days not in window_options and total_days < 30:
        window_options = [total_days, *window_options]
    window_options = sorted(set(window_options))

    nav_key = f"gantt_start::{col_proyecto}::{proyecto_sel}"
    show_all_key = f"gantt_show_all::{col_proyecto}::{proyecto_sel}"
    window_key = f"gantt_window::{col_proyecto}::{proyecto_sel}"
    with subtab_inicial:
        visible_days = st.selectbox(
            "Ventana visible (dias)",
            options=window_options,
            index=window_options.index(default_window) if default_window in window_options else 0,
        )

    max_start = max(total_start, total_end - visible_days + 1)
    if nav_key not in st.session_state:
        st.session_state[nav_key] = total_start
    st.session_state[nav_key] = min(max(st.session_state[nav_key], total_start), max_start)

    previous_window = st.session_state.get(window_key)
    if previous_window != visible_days:
        st.session_state[show_all_key] = False
        st.session_state[window_key] = visible_days

    with subtab_inicial:
        nav_prev, nav_next, nav_reset = st.columns([1, 1, 1], gap="small")
        if nav_prev.button("Anterior", use_container_width=True):
            st.session_state[show_all_key] = False
            st.session_state[nav_key] = max(total_start, st.session_state[nav_key] - visible_days)
        if nav_next.button("Siguiente", use_container_width=True):
            st.session_state[show_all_key] = False
            st.session_state[nav_key] = min(max_start, st.session_state[nav_key] + visible_days)
        if nav_reset.button("Ver todo", use_container_width=True):
            st.session_state[show_all_key] = True
            st.session_state[nav_key] = total_start

    if show_all_key not in st.session_state:
        st.session_state[show_all_key] = total_days <= visible_days

    if st.session_state[show_all_key] or total_days <= visible_days:
        visible_start = total_start
        visible_end = total_end
    else:
        visible_start = st.session_state[nav_key]
        visible_end = min(total_end, visible_start + visible_days - 1)

    visible_span = max(visible_end - visible_start, 1)
    pad = max(visible_span * 0.05, 1)

    x_task = visible_start - visible_span * 0.62
    x_sol = visible_start - visible_span * 0.29
    x_dest = visible_start - visible_span * 0.15
    x_divider = visible_start - visible_span * 0.03
    x_left = visible_start - visible_span * 0.68
    x_right = visible_end + pad
    x_task_end = x_sol - visible_span * 0.05
    x_sol_end = x_dest - visible_span * 0.05
    x_dest_end = x_divider - visible_span * 0.03

    fig = go.Figure()
    paper_bg = "#FFFFFF"
    plot_bg = "#FFFFFF"
    grid_color = "#D6E3F0"
    font_color = "#1F2937"
    header_bg = "#F7FAFC"
    phase_text = "#111827"
    task_text = "#374151"
    alert_red = "#DC2626"

    header_top = n + 1.8
    month_header_bottom = n + 1.35
    week_header_bottom = n + 1.0
    table_header_bottom = n + 0.1
    table_header_y = n + 0.55

    fig.add_shape(
        type="rect",
        x0=x_left,
        x1=x_divider,
        y0=table_header_bottom,
        y1=week_header_bottom,
        fillcolor=header_bg,
        line=dict(color=grid_color, width=1),
        layer="below",
    )

    fig.add_shape(
        type="rect",
        x0=x_divider,
        x1=x_right,
        y0=table_header_bottom,
        y1=week_header_bottom,
        fillcolor="#FFFFFF",
        line=dict(color=grid_color, width=1),
        layer="below",
    )

    fig.add_shape(
        type="rect",
        x0=x_divider,
        x1=x_right,
        y0=week_header_bottom,
        y1=header_top,
        fillcolor="#FFFFFF",
        line=dict(color=grid_color, width=1),
        layer="below",
    )

    header_positions = [
        (x_task, "Tarea"),
        (x_sol, "Solicitante"),
        (x_dest, "Destiantario"),
    ]
    for x_pos, text in header_positions:
        fig.add_annotation(
            x=x_pos,
            y=table_header_y,
            text=f"<b>{text}</b>",
            showarrow=False,
            xanchor="left",
            yanchor="middle",
            font=dict(size=12, color=font_color),
        )

    for x_line in [x_sol - visible_span * 0.04, x_dest - visible_span * 0.04, x_divider]:
        fig.add_shape(
            type="line",
            x0=x_line,
            x1=x_line,
            y0=-0.8,
            y1=week_header_bottom,
            line=dict(color=grid_color, width=1),
            layer="below",
        )
    visible_start_ts = pd.Timestamp.fromordinal(int(visible_start))
    visible_end_ts = pd.Timestamp.fromordinal(int(visible_end))
    visible_calendar = calendar_df[
        (calendar_df["year"] >= visible_start_ts.year)
        & (calendar_df["year"] <= visible_end_ts.year)
    ].copy()
    month_tickvals = []
    month_order = {
        "enero": 1,
        "febrero": 2,
        "marzo": 3,
        "abril": 4,
        "mayo": 5,
        "junio": 6,
        "julio": 7,
        "agosto": 8,
        "septiembre": 9,
        "octubre": 10,
        "noviembre": 11,
        "diciembre": 12,
    }
    visible_calendar["month_num"] = visible_calendar["mes"].map(month_order)
    visible_calendar = visible_calendar.sort_values(["year", "month_num"])

    for _, cal_row in visible_calendar.iterrows():
        year = int(cal_row["year"])
        month_num = int(cal_row["month_num"])
        month_start = pd.Timestamp(year=year, month=month_num, day=1)
        next_month = (
            pd.Timestamp(year=year + 1, month=1, day=1)
            if month_num == 12
            else pd.Timestamp(year=year, month=month_num + 1, day=1)
        )
        month_end = next_month - pd.Timedelta(days=1)
        seg_start = max(day_num(month_start), visible_start)
        seg_end = min(day_num(month_end), visible_end)
        if seg_start > seg_end:
            continue

        month_tickvals.append(seg_start)
        fig.add_shape(
            type="line",
            x0=seg_start,
            x1=seg_start,
            y0=week_header_bottom,
            y1=header_top,
            line=dict(color=grid_color, width=1),
            layer="below",
        )
        fig.add_annotation(
            x=(seg_start + seg_end) / 2,
            y=(week_header_bottom + header_top) / 2,
            text=f"<b>{str(cal_row['mes']).capitalize()}</b>",
            showarrow=False,
            xanchor="center",
            yanchor="middle",
            font=dict(size=12, color=font_color),
        )

        week_count = int(cal_row["cantidad-semanas"])
        for week_idx in range(1, week_count + 1):
            week_start_day = cal_row.get(f"semana{week_idx}-inicio")
            week_end_day = cal_row.get(f"semana{week_idx}-fin")
            if pd.isna(week_start_day) or pd.isna(week_end_day):
                continue

            week_start = pd.Timestamp(year=year, month=month_num, day=int(week_start_day))
            week_end = pd.Timestamp(year=year, month=month_num, day=int(week_end_day))
            week_seg_start = max(day_num(week_start), visible_start)
            week_seg_end = min(day_num(week_end), visible_end)
            if week_seg_start > week_seg_end:
                continue

            fig.add_shape(
                type="line",
                x0=week_seg_start,
                x1=week_seg_start,
                y0=table_header_bottom,
                y1=week_header_bottom,
                line=dict(color=grid_color, width=1),
                layer="below",
            )
            fig.add_shape(
                type="line",
                x0=week_seg_start,
                x1=week_seg_start,
                y0=-0.8,
                y1=table_header_bottom,
                line=dict(color="#D9E6F2", width=1, dash="dot"),
                layer="below",
            )
            fig.add_annotation(
                x=(week_seg_start + week_seg_end) / 2,
                y=(table_header_bottom + week_header_bottom) / 2,
                text=f"{int(week_start_day)}-{int(week_end_day)}",
                showarrow=False,
                xanchor="center",
                yanchor="middle",
                font=dict(size=10, color=font_color),
            )

    fig.add_shape(
        type="line",
        x0=visible_end,
        x1=visible_end,
        y0=table_header_bottom,
        y1=header_top,
        line=dict(color=grid_color, width=1),
        layer="below",
    )
    month_tickvals.append(visible_end)

    for row in rows:
        row_bottom = row["y"] - 0.5
        text_color = phase_text if row["kind"] == "phase" else task_text
        text_weight = "<b>{}</b>" if row["kind"] == "phase" else "{}"
        tarea_full = row["tarea"]
        solicitante_full = row["solicitante"]
        destinatario_full = row["destinatario"]
        tarea_text = text_weight.format(truncate_text(tarea_full, 30))
        solicitante_text = (
            text_weight.format(truncate_text(solicitante_full, 11))
            if row["kind"] == "phase"
            else truncate_text(solicitante_full, 11)
        )
        destinatario_text = (
            text_weight.format(truncate_text(destinatario_full, 11))
            if row["kind"] == "phase"
            else truncate_text(destinatario_full, 11)
        )

        fig.add_shape(
            type="line",
            x0=x_left,
            x1=x_right,
            y0=row_bottom,
            y1=row_bottom,
            line=dict(color=grid_color, width=1),
            layer="below",
        )

        fig.add_annotation(
            x=x_task,
            y=row["y"],
            text=tarea_text,
            showarrow=False,
            xanchor="left",
            yanchor="middle",
            font=dict(size=12, color=text_color),
        )
        fig.add_trace(
            go.Scatter(
                x=[(x_task + x_task_end) / 2],
                y=[row["y"]],
                mode="markers",
                marker=dict(size=22, color="rgba(0,0,0,0)"),
                showlegend=False,
                hovertemplate=f"Tarea: {tarea_full}<extra></extra>",
            )
        )
        fig.add_annotation(
            x=x_sol,
            y=row["y"],
            text=solicitante_text,
            showarrow=False,
            xanchor="left",
            yanchor="middle",
            font=dict(size=11, color=text_color),
        )
        fig.add_trace(
            go.Scatter(
                x=[(x_sol + x_sol_end) / 2],
                y=[row["y"]],
                mode="markers",
                marker=dict(size=18, color="rgba(0,0,0,0)"),
                showlegend=False,
                hovertemplate=f"Solicitante: {solicitante_full}<extra></extra>",
            )
        )
        fig.add_annotation(
            x=x_dest,
            y=row["y"],
            text=destinatario_text,
            showarrow=False,
            xanchor="left",
            yanchor="middle",
            font=dict(size=11, color=text_color),
        )
        fig.add_trace(
            go.Scatter(
                x=[(x_dest + x_dest_end) / 2],
                y=[row["y"]],
                mode="markers",
                marker=dict(size=18, color="rgba(0,0,0,0)"),
                showlegend=False,
                hovertemplate=f"Destiantario: {destinatario_full}<extra></extra>",
            )
        )

        is_phase = row["kind"] == "phase"
        base_color = phase_colors.get(row["phase_name"], "#2563EB")
        real_color = base_color
        proj_color = lighten_color(base_color, 0.68)
        real_line = lighten_color(base_color, 0.35)
        proj_line = lighten_color(base_color, 0.82)

        if is_phase:
            real_y0, real_y1 = row["y"] + 0.06, row["y"] + 0.40
            proj_y0, proj_y1 = row["y"] - 0.40, row["y"] - 0.06
        else:
            real_y0, real_y1 = row["y"] + 0.08, row["y"] + 0.24
            proj_y0, proj_y1 = row["y"] - 0.24, row["y"] - 0.08

        add_period_trace(
            fig,
            row["label"],
            row["proj_inicio"],
            row["proj_fin"],
            proj_y0,
            proj_y1,
            proj_color,
            proj_line,
            "Proyectado",
            visible_start,
            visible_end,
        )
        add_period_trace(
            fig,
            row["label"],
            row["real_inicio"],
            row["real_fin"],
            real_y0,
            real_y1,
            real_color,
            real_line,
            "Real",
            visible_start,
            visible_end,
        )

        if is_phase and row["label"].strip().lower() == "info complementaria":
            highlight_start = row["real_inicio"]
            if pd.isna(highlight_start):
                highlight_start = row["proj_inicio"]
            add_highlight_business_window(
                fig,
                highlight_start,
                business_days=5,
                y0=row["y"] + 0.14,
                y1=row["y"] + 0.32,
                fill_color=alert_red,
                visible_start=visible_start,
                visible_end=visible_end,
                label=row["label"],
            )

    fig.add_shape(
        type="line",
        x0=x_left,
        x1=x_right,
        y0=table_header_bottom,
        y1=table_header_bottom,
        line=dict(color=grid_color, width=1),
        layer="below",
    )

    fig.add_trace(
        go.Bar(x=[None], y=[None], marker_color="#2563EB", name="Real", showlegend=True)
    )
    fig.add_trace(
        go.Bar(x=[None], y=[None], marker_color=lighten_color("#2563EB", 0.68), name="Proyectado", showlegend=True)
    )
    fig.add_trace(
        go.Bar(x=[None], y=[None], marker_color=alert_red, name="Plazo 5 dias habiles", showlegend=True)
    )

    fig.update_layout(
        height=max(620, 44 * n + 140),
        margin=dict(l=10, r=10, t=20, b=20),
        paper_bgcolor=paper_bg,
        plot_bgcolor=plot_bg,
        font=dict(color=font_color, family="Trebuchet MS"),
        legend=dict(orientation="h", y=1.04, x=1, xanchor="right", bgcolor="rgba(0,0,0,0)"),
        xaxis=dict(
            range=[x_left, x_right],
            tickmode="array",
            tickvals=month_tickvals,
            ticktext=["" for _ in month_tickvals],
            showticklabels=False,
            showgrid=True,
            gridcolor=grid_color,
            zeroline=False,
            tickfont=dict(color=font_color),
        ),
        yaxis=dict(
            showgrid=False,
            zeroline=False,
            showticklabels=False,
            range=[-0.8, header_top + 0.1],
        ),
    )

    with subtab_inicial:
        st.plotly_chart(fig, use_container_width=True)

    with subtab_actualizada:
        st.empty()

with tab_resumen:
    st.subheader("Resumen de proyectos")
    st.dataframe(df, use_container_width=True, hide_index=True)

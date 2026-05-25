from datetime import datetime
from time import time

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

SHEET_ID = "1s05TfnAHtRQpnjX0iwOcLsWVX1rCfz_v"


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


def truncate_text(value: str, max_chars: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


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
):
    if pd.isna(start) or pd.isna(end):
        return

    start_num = day_num(start)
    end_num = day_num(end)
    center_y = (y0 + y1) / 2

    if start_num == end_num:
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
        x0=start_num,
        x1=end_num,
        y0=y0,
        y1=y1,
        fillcolor=fill_color,
        line=dict(width=0),
        layer="above",
    )

    center_x = start_num + (end_num - start_num) / 2
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

tab_resumen, tab_estado = st.tabs(["Resumen de proyectos", "Estado por proyecto"])

with tab_resumen:
    st.subheader("Resumen de proyectos")
    st.dataframe(df, use_container_width=True, hide_index=True)

with tab_estado:
    st.subheader("Estado por proyecto")
    col_proyecto = elegir_columna_proyecto(df)
    valores = df[col_proyecto].dropna().astype(str).str.strip()
    valores = sorted([v for v in valores.unique().tolist() if v])

    if not valores:
        st.warning(f"No hay valores para mostrar en '{col_proyecto}'.")
        st.stop()

    proyecto_sel = st.selectbox("Proyecto", valores)
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
    pad = max(date_span * 0.05, 1)

    x_task = date_min_num - date_span * 0.86
    x_sol = date_min_num - date_span * 0.44
    x_dest = date_min_num - date_span * 0.20
    x_divider = date_min_num - date_span * 0.03
    x_left = date_min_num - date_span * 0.92
    x_right = date_max_num + pad
    x_task_end = x_sol - date_span * 0.05
    x_sol_end = x_dest - date_span * 0.05
    x_dest_end = x_divider - date_span * 0.03

    fig = go.Figure()
    paper_bg = "#FFFFFF"
    plot_bg = "#FFFFFF"
    grid_color = "#D6E3F0"
    font_color = "#1F2937"
    header_bg = "#F7FAFC"
    phase_text = "#111827"
    task_text = "#374151"
    real_phase = "#58C6FF"
    proj_phase = "#98A8B8"
    real_task = "#2D8CFF"
    proj_task = "#C8D1D8"

    header_top = n + 1.0
    header_bottom = n + 0.1
    table_header_y = n + 0.55

    fig.add_shape(
        type="rect",
        x0=x_left,
        x1=x_divider,
        y0=header_bottom,
        y1=header_top,
        fillcolor=header_bg,
        line=dict(color=grid_color, width=1),
        layer="below",
    )

    fig.add_shape(
        type="rect",
        x0=x_divider,
        x1=x_right,
        y0=header_bottom,
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

    for x_line in [x_sol - date_span * 0.04, x_dest - date_span * 0.04, x_divider]:
        fig.add_shape(
            type="line",
            x0=x_line,
            x1=x_line,
            y0=-0.8,
            y1=header_top,
            line=dict(color=grid_color, width=1),
            layer="below",
        )

    for row in rows:
        row_bottom = row["y"] - 0.5
        text_color = phase_text if row["kind"] == "phase" else task_text
        text_weight = "<b>{}</b>" if row["kind"] == "phase" else "{}"
        tarea_full = row["tarea"]
        solicitante_full = row["solicitante"]
        destinatario_full = row["destinatario"]
        tarea_text = text_weight.format(truncate_text(tarea_full, 38))
        solicitante_text = (
            text_weight.format(truncate_text(solicitante_full, 16))
            if row["kind"] == "phase"
            else truncate_text(solicitante_full, 16)
        )
        destinatario_text = (
            text_weight.format(truncate_text(destinatario_full, 16))
            if row["kind"] == "phase"
            else truncate_text(destinatario_full, 16)
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
        real_color = real_phase if is_phase else real_task
        proj_color = proj_phase if is_phase else proj_task
        real_line = "#A5F3FC" if is_phase else "#93C5FD"
        proj_line = "#E2E8F0" if is_phase else "#CBD5E1"

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
        )

    fig.add_shape(
        type="line",
        x0=x_left,
        x1=x_right,
        y0=header_bottom,
        y1=header_bottom,
        line=dict(color=grid_color, width=1),
        layer="below",
    )

    tickvals = list(range(int(date_min_num), int(date_max_num) + 1, 7))
    if int(date_max_num) not in tickvals:
        tickvals.append(int(date_max_num))
    ticktext = [pd.Timestamp.fromordinal(int(v)).strftime("%d/%m") for v in tickvals]

    fig.add_trace(
        go.Bar(x=[None], y=[None], marker_color=real_task, name="Real", showlegend=True)
    )
    fig.add_trace(
        go.Bar(x=[None], y=[None], marker_color=proj_task, name="Proyectado", showlegend=True)
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
            tickvals=tickvals,
            ticktext=ticktext,
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

    st.plotly_chart(fig, use_container_width=True)

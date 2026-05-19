from datetime import datetime
from time import time

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

SHEET_ID = "1s05TfnAHtRQpnjX0iwOcLsWVX1rCfz_v"


def _csv_url() -> str:
    # /export?format=csv lee los valores crudos (gviz/tq omite celdas con
    # formato/locale inconsistente). Sin `gid` se exporta la primera hoja
    # (Estado). `_t` cambia en cada carga para evitar cachés intermedios.
    return (
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
        f"/export?format=csv&_t={int(time() * 1000)}"
    )


def parse_fecha(valor):
    """Parsea fechas en formato día primero (DD/MM/YYYY o DD/M/YY)."""
    if pd.isna(valor):
        return pd.NaT
    s = str(valor).strip()
    if not s:
        return pd.NaT
    return pd.to_datetime(s, dayfirst=True, errors="coerce")


def find_col(df: pd.DataFrame, *candidatos: str) -> str:
    """Devuelve el nombre real de columna que coincide con alguno de los candidatos
    (case/espacio/acento-insensitive). Lanza KeyError si ninguno encaja."""
    import unicodedata

    def norm(s: str) -> str:
        s = unicodedata.normalize("NFKD", str(s))
        return "".join(c for c in s if not unicodedata.combining(c)).strip().lower()

    cols_norm = {norm(c): c for c in df.columns}
    for cand in candidatos:
        if norm(cand) in cols_norm:
            return cols_norm[norm(cand)]
        # Match parcial: cualquier columna cuyo nombre normalizado empiece con el candidato
        for nc, real in cols_norm.items():
            if nc.startswith(norm(cand)):
                return real
    raise KeyError(f"Ninguna de {candidatos} encontrada en {list(df.columns)}")


TIPOS_VALIDOS = {"inicio y fin", "solo inicio"}

COLOR_FASE = "#374151"
COLOR_TAREA = "#3B82F6"
COLOR_HITO = "#DC2626"
COLOR_PROGRAMADO = "#9CA3AF"

st.set_page_config(page_title="Estado OXI", layout="wide")
st.title("Estado OXI")

if st.sidebar.button("🔄 Actualizar"):
    st.rerun()


def cargar_estado() -> pd.DataFrame:
    # En /export?format=csv los headers pueden venir partidos en dos filas físicas
    # (la 2da es la continuación: "si tarea tiene:", "dias calendario", etc.).
    # Saltamos la 2da fila para mantener un único header coherente.
    df = pd.read_csv(_csv_url(), skiprows=[1])
    df.columns = df.columns.str.strip()
    df = df.loc[:, ~df.columns.str.startswith("Unnamed")]
    df = df.loc[:, df.columns != ""]

    col_proyecto = find_col(df, "Proyecto nombre corto", "Proyecto")
    col_fase = find_col(df, "Nombre fase", "Fase nombre", "Fase")
    col_tarea = find_col(df, "Tarea")
    col_tipo = find_col(df, "Tipo tarea si tarea tiene:", "Tipo tarea Tiene:", "Tipo tarea")
    col_inicio = find_col(df, "Fecha solicitud")
    col_fin = find_col(df, "Fecha recepción", "Fecha recepcion")
    col_plazo = find_col(df, "Plazo referencial dias calendario", "Plazo referencial DC",
                         "Plazo referencial", "Plazo")

    # Salvaguarda: si todavía queda una fila de notas (Tipo tarea inválido), la quitamos.
    if not df.empty:
        primer_tipo = str(df.iloc[0].get(col_tipo, "")).strip().lower()
        if primer_tipo not in TIPOS_VALIDOS:
            df = df.iloc[1:].reset_index(drop=True)

    df[col_inicio] = df[col_inicio].apply(parse_fecha)
    df[col_fin] = df[col_fin].apply(parse_fecha)
    df[col_plazo] = pd.to_numeric(df[col_plazo], errors="coerce")
    df["_tipo"] = df[col_tipo].astype(str).str.strip().str.lower()

    # Adjuntamos el mapeo de nombres canónicos para que el resto del script lo use.
    df.attrs["cols"] = {
        "proyecto": col_proyecto,
        "fase": col_fase,
        "tarea": col_tarea,
        "tipo": col_tipo,
        "inicio": col_inicio,
        "fin": col_fin,
        "plazo": col_plazo,
    }
    return df


try:
    with st.spinner("Cargando datos desde Google Sheets..."):
        df = cargar_estado()
    st.caption(f"Última carga: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
except Exception as exc:
    st.error(f"No se pudo cargar el Google Sheet: {exc}")
    st.stop()

cols = df.attrs["cols"]

COL_PROYECTO = cols["proyecto"]
COL_FASE = cols["fase"]
COL_TAREA = cols["tarea"]
COL_TIPO = cols["tipo"]
COL_INICIO = cols["inicio"]
COL_FIN = cols["fin"]
COL_PLAZO = cols["plazo"]

proyectos = sorted([p for p in df[COL_PROYECTO].dropna().unique() if str(p).strip()])
if not proyectos:
    st.warning("No hay proyectos en la hoja Estado.")
    st.stop()
proyecto_sel = st.sidebar.selectbox("Proyecto", proyectos)

df_p = df[df[COL_PROYECTO] == proyecto_sel].copy()

fases_orden = df_p[COL_FASE].dropna().drop_duplicates().tolist()

# Cálculo de fechas programadas (días hábiles, lun-vie) por fase y tarea.
# Ancla: primera "Fecha solicitud" real de la primera tarea "Inicio y fin" de la fase.
# Cada tarea "Inicio y fin" siguiente arranca donde terminó la programación de la anterior.
# Las "Solo inicio" no tienen plazo y no se programan.
sched_phase: dict = {}
sched_task: dict = {}
for fase in fases_orden:
    sub = df_p[df_p[COL_FASE] == fase]
    anchor = None
    for _, rr in sub.iterrows():
        if rr["_tipo"] == "inicio y fin" and pd.notna(rr[COL_INICIO]):
            anchor = pd.Timestamp(rr[COL_INICIO])
            break
    if anchor is None:
        continue
    cursor = anchor
    fin_fase = anchor
    for _, rr in sub.iterrows():
        if rr["_tipo"] != "inicio y fin":
            continue
        plazo = rr.get(COL_PLAZO)
        if pd.isna(plazo):
            continue
        sched_end = cursor + pd.tseries.offsets.BDay(int(plazo))
        sched_task[(fase, str(rr[COL_TAREA]).strip())] = {"start": cursor, "end": sched_end}
        cursor = sched_end
        if sched_end > fin_fase:
            fin_fase = sched_end
    sched_phase[fase] = {"start": anchor, "end": fin_fase}

rows = []
for fase in fases_orden:
    sub = df_p[df_p[COL_FASE] == fase]
    fase_inicio = sub[COL_INICIO].min()
    fase_fin = sub[COL_FIN].max()
    if pd.isna(fase_fin):
        fase_fin = sub[COL_INICIO].max()
    if pd.notna(fase_inicio) and pd.notna(fase_fin):
        rows.append({
            "label": f"▣  {fase}",
            "fase": fase,
            "kind": "phase",
            "start": fase_inicio,
            "end": fase_fin,
            "sched": sched_phase.get(fase),
        })
    for _, r in sub.iterrows():
        tarea = str(r[COL_TAREA]).strip()
        label = f"      {tarea}"
        if "solo inicio" in r["_tipo"]:
            if pd.notna(r[COL_INICIO]):
                rows.append({
                    "label": label, "fase": fase, "tarea": tarea, "kind": "milestone",
                    "start": r[COL_INICIO], "end": r[COL_INICIO],
                    "sched": None,
                })
        else:
            if pd.notna(r[COL_INICIO]) and pd.notna(r[COL_FIN]):
                rows.append({
                    "label": label, "fase": fase, "tarea": tarea, "kind": "task",
                    "start": r[COL_INICIO], "end": r[COL_FIN],
                    "sched": sched_task.get((fase, tarea)),
                })

if not rows:
    st.info("Sin tareas con fechas suficientes para mostrar en este proyecto.")
    st.stop()

n = len(rows)
for i, r in enumerate(rows):
    r["y"] = n - 1 - i  # primer item de la lista queda arriba

# Rango del eje X a partir de todas las fechas presentes (reales y programadas)
all_dates = []
for r in rows:
    all_dates.append(r["start"])
    all_dates.append(r["end"])
    if r.get("sched"):
        all_dates.append(r["sched"]["start"])
        all_dates.append(r["sched"]["end"])
date_min = min(all_dates)
date_max = max(all_dates)
pad = max((date_max - date_min) * 0.05, pd.Timedelta(days=1))

fig = go.Figure()

# Rectángulos como shapes. Real arriba, Programado abajo dentro de cada fila.
# Fase real: y+0.02..y+0.20  | Fase programada: y-0.20..y-0.02
# Tarea real: y+0.02..y+0.34 | Tarea programada: y-0.34..y-0.02
for r in rows:
    if r["kind"] == "phase":
        fig.add_shape(
            type="rect",
            x0=r["start"], x1=r["end"],
            y0=r["y"] + 0.02, y1=r["y"] + 0.20,
            fillcolor=COLOR_FASE, line=dict(width=0), layer="above",
        )
        if r.get("sched"):
            fig.add_shape(
                type="rect",
                x0=r["sched"]["start"], x1=r["sched"]["end"],
                y0=r["y"] - 0.20, y1=r["y"] - 0.02,
                fillcolor=COLOR_PROGRAMADO, line=dict(width=0), layer="above",
            )
    elif r["kind"] == "task":
        fig.add_shape(
            type="rect",
            x0=r["start"], x1=r["end"],
            y0=r["y"] + 0.02, y1=r["y"] + 0.34,
            fillcolor=COLOR_TAREA, line=dict(width=0), layer="above",
        )
        if r.get("sched"):
            fig.add_shape(
                type="rect",
                x0=r["sched"]["start"], x1=r["sched"]["end"],
                y0=r["y"] - 0.34, y1=r["y"] - 0.02,
                fillcolor=COLOR_PROGRAMADO, line=dict(width=0), layer="above",
            )

# Capa transparente para hover (real arriba, programado abajo)
for r in rows:
    if r["kind"] == "phase":
        center_real = r["start"] + (r["end"] - r["start"]) / 2
        fig.add_trace(go.Scatter(
            x=[center_real], y=[r["y"] + 0.11],
            mode="markers",
            marker=dict(size=18, color="rgba(0,0,0,0)"),
            showlegend=False,
            hovertemplate=(f"<b>Fase:</b> {r['fase']} (real)<br>"
                           f"{r['start'].strftime('%d/%m/%Y')} → "
                           f"{r['end'].strftime('%d/%m/%Y')}<extra></extra>"),
        ))
        if r.get("sched"):
            s = r["sched"]
            center_s = s["start"] + (s["end"] - s["start"]) / 2
            fig.add_trace(go.Scatter(
                x=[center_s], y=[r["y"] - 0.11],
                mode="markers",
                marker=dict(size=18, color="rgba(0,0,0,0)"),
                showlegend=False,
                hovertemplate=(f"<b>Fase:</b> {r['fase']} (programado)<br>"
                               f"{s['start'].strftime('%d/%m/%Y')} → "
                               f"{s['end'].strftime('%d/%m/%Y')}<extra></extra>"),
            ))
    elif r["kind"] == "task":
        center_real = r["start"] + (r["end"] - r["start"]) / 2
        fig.add_trace(go.Scatter(
            x=[center_real], y=[r["y"] + 0.18],
            mode="markers",
            marker=dict(size=22, color="rgba(0,0,0,0)"),
            showlegend=False,
            hovertemplate=(f"<b>{r['tarea']}</b> (real)<br>"
                           f"{r['start'].strftime('%d/%m/%Y')} → "
                           f"{r['end'].strftime('%d/%m/%Y')}<extra></extra>"),
        ))
        if r.get("sched"):
            s = r["sched"]
            center_s = s["start"] + (s["end"] - s["start"]) / 2
            fig.add_trace(go.Scatter(
                x=[center_s], y=[r["y"] - 0.18],
                mode="markers",
                marker=dict(size=22, color="rgba(0,0,0,0)"),
                showlegend=False,
                hovertemplate=(f"<b>{r['tarea']}</b> (programado)<br>"
                               f"{s['start'].strftime('%d/%m/%Y')} → "
                               f"{s['end'].strftime('%d/%m/%Y')}<extra></extra>"),
            ))
    elif r["kind"] == "milestone":
        fig.add_trace(go.Scatter(
            y=[r["y"] + 0.18], x=[r["start"]],
            mode="markers",
            marker=dict(symbol="diamond", size=14, color=COLOR_HITO,
                        line=dict(color="#7F1D1D", width=1)),
            showlegend=False,
            hovertemplate=(f"<b>{r['tarea']}</b> (hito)<br>"
                           f"{r['start'].strftime('%d/%m/%Y')}<extra></extra>"),
        ))

# Leyenda manual
fig.add_trace(go.Bar(x=[None], y=[None], marker_color=COLOR_FASE,
                    name="Fase (real)", showlegend=True))
fig.add_trace(go.Bar(x=[None], y=[None], marker_color=COLOR_TAREA,
                    name="Tarea (real)", showlegend=True))
fig.add_trace(go.Bar(x=[None], y=[None], marker_color=COLOR_PROGRAMADO,
                    name="Programado", showlegend=True))
fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers",
                         marker=dict(symbol="diamond", size=12, color=COLOR_HITO),
                         name="Hito (solo inicio)", showlegend=True))

fig.update_layout(
    height=max(420, 42 * n + 120),
    margin=dict(l=10, r=10, t=40, b=10),
    xaxis=dict(
        type="date",
        range=[date_min - pad, date_max + pad],
        showgrid=True,
        gridcolor="#E5E7EB",
    ),
    yaxis=dict(
        tickmode="array",
        tickvals=[r["y"] for r in rows],
        ticktext=[r["label"] for r in rows],
        showgrid=False,
        automargin=True,
        range=[-0.6, n - 0.4],
    ),
    plot_bgcolor="white",
    legend=dict(orientation="h", y=1.08, x=1, xanchor="right"),
)

st.subheader(f"Gantt — {proyecto_sel}")
st.plotly_chart(fig, use_container_width=True)

total_tareas = len(df_p)
dibujadas = sum(1 for r in rows if r["kind"] in ("task", "milestone"))
omitidas = total_tareas - dibujadas
if omitidas > 0:
    st.caption(f"⚠️ {omitidas} tarea(s) no se dibujan: les falta fecha de inicio "
               f"y/o fin según su tipo.")

with st.expander("Datos crudos (hoja Estado)"):
    st.dataframe(df_p.drop(columns=["_tipo"]), use_container_width=True, hide_index=True)

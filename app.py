from __future__ import annotations

import base64
import hashlib
import hmac
import mimetypes
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


APP_TITLE = "BI Cadastro | Copel"
DATA_FILE = Path(__file__).with_name("base_consolidada_copel.csv")
ASSET_DIR = Path(__file__).with_name("assets")
LOGIN_USER = "Copel"
PASSWORD_SALT = b"copel-bi-cadastro-v1"
PASSWORD_HASH = bytes.fromhex(
    "09e79419c0d0ef10fb06c88f9a68195b02c4954873140d6b0974f22e3f9fae10"
)
COLORS = ["#F5821E", "#FDB422", "#E65D24", "#3F444B", "#69727D", "#8D3F8F"]
PROJECT_START_DATE = pd.Timestamp("2026-03-01")

st.set_page_config(page_title=APP_TITLE, page_icon="⚡", layout="wide")


def inject_css() -> None:
    st.markdown(
        """
        <style>
        :root { --copel-orange:#F5821E; --copel-gold:#FDB422; --ink:#151C21; }
        .stApp { background: linear-gradient(145deg, #f8f9fa 0%, #eef0f2 100%); }
        [data-testid="stSidebar"] { background: #151C21; border-right: 3px solid #F5821E; }
        [data-testid="stSidebar"] * { color: #f7f8f8; }
        [data-testid="stSidebar"] [data-testid="stMetric"] * {
            color: #151C21 !important;
        }
        [data-testid="stSidebar"] .stButton button,
        [data-testid="stSidebar"] .stButton button * {
            color: #151C21 !important;
        }
        [data-testid="stSidebar"] hr { border-color: rgba(255,255,255,.14); }
        [data-testid="stMetric"] {
            background: rgba(255,255,255,.96); border: 1px solid #e1e3e5;
            border-left: 5px solid var(--copel-orange); border-radius: 14px;
            padding: 14px 16px; box-shadow: 0 8px 24px rgba(21,28,33,.08);
        }
        [data-testid="stMetricValue"] { color: var(--ink); font-weight: 750; }
        [data-testid="stMetricDelta"] svg { display:none; }
        .page-kicker { color:#F5821E; font-size:.78rem; letter-spacing:.14em;
            text-transform:uppercase; font-weight:700; margin-bottom:.25rem; }
        .page-title { color:var(--ink); font-size:2rem; line-height:1.1;
            font-weight:800; margin:0 0 .3rem 0; }
        .page-subtitle { color:#69727D; margin-bottom:1.25rem; }
        .login-wrap { max-width:460px; margin:7vh auto 0 auto; padding:30px;
            background:white; border-radius:18px; box-shadow:0 14px 42px rgba(21,28,33,.12); }
        .brand-mark { font-size:2.2rem; font-weight:850; color:#151C21; }
        .brand-mark span { color:#F5821E; }
        .filter-caption { color:#C8CDD0 !important; font-size:.8rem; }
        div[data-testid="stPlotlyChart"] { background:#fff; border:1px solid #E1E3E5;
            border-radius:14px; padding:8px; box-shadow:0 8px 24px rgba(21,28,33,.06); }
        .brand-banner {
            display:flex; align-items:center; justify-content:space-between; gap:28px;
            padding:22px 28px; margin:0 0 26px 0; overflow:hidden;
            border-radius:18px; color:white;
            background:linear-gradient(112deg, #151C21 0%, #272F35 64%, #7A3C1B 100%);
            border-bottom:5px solid #F5821E;
            box-shadow:0 14px 34px rgba(21,28,33,.16);
        }
        .banner-kicker { color:#FDB422; font-size:.72rem; font-weight:800;
            letter-spacing:.16em; text-transform:uppercase; margin-bottom:4px; }
        .banner-title { font-size:1.7rem; font-weight:850; line-height:1.1; }
        .banner-copy { color:#DDE1E3; font-size:.88rem; margin-top:5px; }
        .brand-logos { display:flex; align-items:center; gap:20px; flex-shrink:0; }
        .copel-logo { width:210px; height:auto; display:block; }
        .brand-separator { height:54px; width:1px; background:rgba(255,255,255,.28); }
        .essenz-panel { display:flex; align-items:center; justify-content:center;
            width:176px; height:70px; }
        .essenz-logo { max-width:170px; max-height:66px; width:auto; height:auto; display:block; }
        @media (max-width: 760px) {
            .brand-banner { align-items:flex-start; flex-direction:column; padding:19px; }
            .brand-logos { width:100%; justify-content:space-between; gap:12px; }
            .copel-logo { width:170px; }
            .essenz-panel { width:145px; height:62px; }
            .essenz-logo { max-width:140px; max-height:58px; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def asset_data_uri(filename: str) -> str:
    path = ASSET_DIR / filename
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def render_brand_banner() -> None:
    copel_logo = asset_data_uri("logo-copel.png")
    essenz_logo = asset_data_uri("logo-essenz.svg")
    st.markdown(
        f"""
        <div class="brand-banner">
            <div>
                <div class="banner-kicker">Inteligência para energia</div>
                <div class="banner-title">BI Cadastro de UCs</div>
                <div class="banner-copy">Indicadores consolidados para decisões orientadas por dados</div>
            </div>
            <div class="brand-logos">
                <img class="copel-logo" src="{copel_logo}" alt="COPEL — Pura Energia">
                <div class="brand-separator"></div>
                <div class="essenz-panel">
                    <img class="essenz-logo" src="{essenz_logo}" alt="Essenz Soluções">
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def password_matches(candidate: str) -> bool:
    candidate_hash = hashlib.pbkdf2_hmac(
        "sha256", candidate.encode("utf-8"), PASSWORD_SALT, 390_000
    )
    return hmac.compare_digest(candidate_hash, PASSWORD_HASH)


def login_screen() -> None:
    left, center, right = st.columns([1, 1.15, 1])
    with center:
        st.markdown(
            '<div class="brand-mark">BI <span>Cadastro</span></div>'
            '<p style="color:#69727D">Painel consolidado de unidades consumidoras</p>',
            unsafe_allow_html=True,
        )
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Login", placeholder="Digite seu login")
            password = st.text_input(
                "Senha", type="password", placeholder="Digite sua senha"
            )
            submitted = st.form_submit_button("Entrar", width="stretch")
        if submitted:
            if hmac.compare_digest(username.strip(), LOGIN_USER) and password_matches(password):
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Login ou senha inválidos.")


@st.cache_data(show_spinner="Carregando base de UCs...")
def load_data(file_mtime: float) -> pd.DataFrame:
    del file_mtime  # Included only to invalidate the cache when the CSV changes.
    frame = pd.read_csv(DATA_FILE, encoding="utf-8-sig", low_memory=False)
    frame.columns = [
        str(column)
        .strip()
        .replace("IND_SOLICITA�AO", "IND_SOLICITACAO")
        .replace("IND_SOLICITAÇAO", "IND_SOLICITACAO")
        for column in frame.columns
    ]
    for column in [
        "DT_ATIVACAO",
        "DT_DISTRATO",
        "GD_BENE_INIC",
        "GD_BENE_FIM",
        "DATA_INICIO_GD",
        "DATA_FIM_GD",
    ]:
        if column in frame:
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
    for column in ["GRUPO", "ETAPA", "ANO_VEIC"]:
        if column in frame:
            frame[column] = frame[column].astype("Int64").astype("string")
    return frame


def clean_label(value: object) -> str:
    return "Não informado" if pd.isna(value) or str(value).strip() == "" else str(value)


def options_for(frame: pd.DataFrame, column: str) -> list[str]:
    return sorted(frame[column].dropna().astype(str).unique().tolist())


def sidebar_filters(frame: pd.DataFrame) -> tuple[pd.DataFrame, str, pd.Timestamp]:
    st.sidebar.markdown("## BI Cadastro")
    page = st.sidebar.radio(
        "Navegação",
        [
            "Resumo executivo",
            "UCs e localização",
            "Perfil dos veículos",
            "Infraestrutura de recarga",
            "Geração distribuída",
            "Qualidade dos dados",
        ],
        label_visibility="collapsed",
    )

    st.sidebar.divider()
    st.sidebar.markdown("### Filtros globais")
    st.sidebar.markdown(
        '<p class="filter-caption">Seleção vazia considera todos os valores.</p>',
        unsafe_allow_html=True,
    )
    gd_reference_date = pd.Timestamp(
        st.sidebar.date_input(
            "Data de referência",
            value=PROJECT_START_DATE.date(),
            help=(
                "Recalcula a GD inicial e a situação das UCs na data "
                "selecionada."
            ),
        )
    )

    filters = {
        "SITUACAO_ATUAL": st.sidebar.multiselect(
            "Situação atual", options_for(frame, "SITUACAO_ATUAL")
        ),
        "LOCAL": st.sidebar.multiselect("Município", options_for(frame, "LOCAL")),
        "TIPO_FASE": st.sidebar.multiselect(
            "Tipo de fase", options_for(frame, "TIPO_FASE")
        ),
        "ETAPA": st.sidebar.multiselect("Etapa", options_for(frame, "ETAPA")),
        "FINALIDADE": st.sidebar.multiselect(
            "Finalidade", options_for(frame, "FINALIDADE")
        ),
        "FABRI_VEIC": st.sidebar.multiselect(
            "Fabricante do veículo", options_for(frame, "FABRI_VEIC")
        ),
    }

    filtered = frame.copy()
    for column, chosen in filters.items():
        if chosen:
            filtered = filtered[filtered[column].astype(str).isin(chosen)]

    st.sidebar.divider()
    st.sidebar.metric("UCs na seleção", f"{len(filtered):,}".replace(",", "."))
    if st.sidebar.button("Sair", width="stretch"):
        st.session_state.authenticated = False
        st.rerun()
    return filtered, page, gd_reference_date


def title(kicker: str, heading: str, subtitle: str) -> None:
    heading_html = f'<div class="page-title">{heading}</div>' if heading else ""
    st.markdown(
        f'<div class="page-kicker">{kicker}</div>'
        f'{heading_html}'
        f'<div class="page-subtitle">{subtitle}</div>',
        unsafe_allow_html=True,
    )


def empty_state() -> None:
    st.warning("Nenhuma UC corresponde aos filtros selecionados.")


def chart_style(fig: go.Figure, height: int = 390) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=20, r=20, t=55, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Arial", color="#33373D"),
        colorway=COLORS,
        legend_title_text="",
    )
    return fig


def count_table(frame: pd.DataFrame, column: str, name: str) -> pd.DataFrame:
    values = frame[column].map(clean_label).value_counts().rename_axis(name).reset_index(name="UCs")
    return values


def executive_page(frame: pd.DataFrame, gd_reference_date: pd.Timestamp) -> None:
    title(
        "Visão consolidada",
        "",
        "Indicadores principais das unidades consumidoras conforme os filtros ativos.",
    )
    active_initial = int(frame["SITUACAO_INICIAL"].eq("Ativo").sum())
    active = int(frame["SITUACAO_ATUAL"].eq("Ativo").sum())
    control_initial = int(frame["SITUACAO_INICIAL"].eq("Controle").sum())
    control = int(frame["SITUACAO_ATUAL"].eq("Controle").sum())
    reserve = int(frame["SITUACAO_ATUAL"].eq("Reserva").sum())
    with_vehicle = int(frame["FABRI_VEIC"].notna().sum())
    with_wallbox = int(frame["STATUS_WALLBOX"].eq("S").sum())
    gd_started_before_project = (
        frame["GD_BENE_INIC"].lt(PROJECT_START_DATE)
        | frame["DATA_INICIO_GD"].lt(PROJECT_START_DATE)
    )
    gd_started_before_reference = (
        frame["GD_BENE_INIC"].lt(gd_reference_date)
        | frame["DATA_INICIO_GD"].lt(gd_reference_date)
    )
    same_benefit_start_and_end = (
        frame["GD_BENE_INIC"].notna()
        & frame["GD_BENE_FIM"].notna()
        & frame["GD_BENE_INIC"].eq(frame["GD_BENE_FIM"])
    )
    valid_initial_gd = gd_started_before_project & ~same_benefit_start_and_end
    valid_filtered_gd = gd_started_before_reference & ~same_benefit_start_and_end
    active_initial_gd = int(
        (frame["SITUACAO_INICIAL"].eq("Ativo") & valid_initial_gd).sum()
    )
    control_initial_gd = int(
        (frame["SITUACAO_INICIAL"].eq("Controle") & valid_initial_gd).sum()
    )
    active_filtered_gd = int(
        (frame["SITUACAO_INICIAL"].eq("Ativo") & valid_filtered_gd).sum()
    )
    control_filtered_gd = int(
        (frame["SITUACAO_INICIAL"].eq("Controle") & valid_filtered_gd).sum()
    )
    active_initial_gd_percentage = (
        active_initial_gd / active_initial if active_initial else 0
    )
    control_initial_gd_percentage = (
        control_initial_gd / control_initial if control_initial else 0
    )
    active_filtered_gd_percentage = (
        active_filtered_gd / active_initial if active_initial else 0
    )
    control_filtered_gd_percentage = (
        control_filtered_gd / control_initial if control_initial else 0
    )
    cities = int(frame["LOCAL"].nunique())
    removed = int(frame["SITUACAO_ATUAL"].eq("Removido").sum())

    row1 = st.columns(5)
    row1[0].metric("UCs ativas inicial", f"{active_initial:,}".replace(",", "."))
    row1[1].metric("UCs ativas", f"{active:,}".replace(",", "."))
    row1[2].metric("UCs controle inicial", f"{control_initial:,}".replace(",", "."))
    row1[3].metric("UCs controle", f"{control:,}".replace(",", "."))
    row1[4].metric("UCs reserva", f"{reserve:,}".replace(",", "."))
    st.caption(
        f"GD inicial em {PROJECT_START_DATE:%d/%m/%Y} · "
        f"GD filtrada em {gd_reference_date:%d/%m/%Y}"
    )
    gd_row = st.columns(4)
    gd_row[0].metric(
        "GD Ativos — inicial",
        f"{active_initial_gd:,}".replace(",", "."),
        f"{active_initial_gd_percentage:.1%}".replace(".", ","),
        delta_color="normal",
    )
    gd_row[1].metric(
        "GD Controle — inicial",
        f"{control_initial_gd:,}".replace(",", "."),
        f"{control_initial_gd_percentage:.1%}".replace(".", ","),
        delta_color="normal",
    )
    gd_row[2].metric(
        "GD Ativos — filtrada",
        f"{active_filtered_gd:,}".replace(",", "."),
        f"{active_filtered_gd_percentage:.1%}".replace(".", ","),
        delta_color="normal",
    )
    gd_row[3].metric(
        "GD Controle — filtrada",
        f"{control_filtered_gd:,}".replace(",", "."),
        f"{control_filtered_gd_percentage:.1%}".replace(".", ","),
        delta_color="normal",
    )
    row2 = st.columns(4)
    row2[0].metric("Com veículo", f"{with_vehicle:,}".replace(",", "."))
    row2[1].metric("Com wallbox", f"{with_wallbox:,}".replace(",", "."))
    row2[2].metric("Municípios atendidos", f"{cities:,}".replace(",", "."))
    row2[3].metric("UCs removidas", f"{removed:,}".replace(",", "."))
    st.markdown("#### Comparativos consolidados")
    left, right = st.columns([1.35, 1])
    status_population = frame[
        frame["SITUACAO_INICIAL"].isin(["Ativo", "Controle"])
    ].copy()
    removed_by_reference_date = (
        status_population["DT_DISTRATO"].notna()
        & status_population["DT_DISTRATO"].le(gd_reference_date)
    )
    status_population["Situação na referência"] = status_population[
        "SITUACAO_INICIAL"
    ]
    status_population.loc[
        removed_by_reference_date, "Situação na referência"
    ] = (
        "Removido "
        + status_population.loc[removed_by_reference_date, "SITUACAO_INICIAL"]
    )
    status_order = ["Ativo", "Controle", "Removido Ativo", "Removido Controle"]
    status_counts = status_population["Situação na referência"].value_counts()
    status = pd.DataFrame(
        {
            "Situação": status_order,
            "UCs": [int(status_counts.get(label, 0)) for label in status_order],
        }
    )
    status_total = int(status["UCs"].sum())
    removed_total = int(
        status.loc[status["Situação"].str.startswith("Removido"), "UCs"].sum()
    )
    active_control_total = status_total - removed_total
    removed_midpoint = (
        360 * (active_control_total + removed_total / 2) / status_total
        if status_total
        else 0
    )
    donut_rotation = (180 - removed_midpoint) % 360
    with left:
        fig = px.pie(
            status,
            names="Situação",
            values="UCs",
            hole=.64,
            color="Situação",
            color_discrete_map={
                "Ativo": "#F5821E",
                "Controle": "#FDB422",
                "Removido Ativo": "#3F444B",
                "Removido Controle": "#69727D",
            },
            category_orders={"Situação": status_order},
        )
        fig.update_traces(
            textposition="outside",
            textinfo="none",
            texttemplate="%{label}<br><b>%{value}</b>",
            textfont_size=13,
            sort=False,
            direction="clockwise",
            rotation=donut_rotation,
        )
        fig = chart_style(fig, 520)
        fig.update_layout(
            title=f"Situação em {gd_reference_date:%d/%m/%Y}",
            showlegend=False,
            margin=dict(l=95, r=95, t=75, b=115),
        )
        fig.add_annotation(text=f"<b>{status_total}</b><br>UCs", showarrow=False, font_size=18)
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    with right:
        cities_df = count_table(frame, "LOCAL", "Município").head(10).sort_values("UCs")
        fig = px.bar(cities_df, x="UCs", y="Município", orientation="h", text="UCs", color="UCs", color_continuous_scale=["#FBE8D8", "#F5821E"])
        fig.update_layout(coloraxis_showscale=False, title="Top 10 municípios")
        fig.update_traces(textposition="outside")
        st.plotly_chart(chart_style(fig), width="stretch", config={"displayModeBar": False})


def uc_page(frame: pd.DataFrame) -> None:
    title("Distribuição operacional", "UCs e localização", "Compare a concentração territorial, as fases e as situações das UCs.")
    left, right = st.columns([1.15, 1])
    with left:
        city = count_table(frame, "LOCAL", "Município").head(15).sort_values("UCs")
        fig = px.bar(city, x="UCs", y="Município", orientation="h", color="UCs", text="UCs", color_continuous_scale=["#FFF1E6", "#F5821E"])
        fig.update_layout(title="15 municípios com mais UCs", coloraxis_showscale=False)
        st.plotly_chart(chart_style(fig, 470), width="stretch", config={"displayModeBar": False})
    with right:
        cross = pd.crosstab(frame["TIPO_FASE"].map(clean_label), frame["SITUACAO_ATUAL"].map(clean_label))
        fig = px.imshow(cross, text_auto=True, aspect="auto", color_continuous_scale=["#F7F7F7", "#F5821E"], labels=dict(x="Situação atual", y="Tipo de fase", color="UCs"))
        fig.update_layout(title="Situação por tipo de fase")
        st.plotly_chart(chart_style(fig, 470), width="stretch", config={"displayModeBar": False})


def vehicle_page(frame: pd.DataFrame) -> None:
    title("Mobilidade elétrica", "Perfil dos veículos", "Compare fabricantes, tecnologia do motor, finalidade e ano dos veículos cadastrados.")
    vehicles = frame[frame["FABRI_VEIC"].notna()].copy()
    if vehicles.empty:
        empty_state(); return
    left, right = st.columns([1.25, 1])
    with left:
        vehicles["Motor"] = vehicles["MOTOR_VEIC"].map(clean_label)
        fig = px.treemap(vehicles, path=["Motor", "FABRI_VEIC"], color="Motor", color_discrete_sequence=COLORS)
        fig.update_layout(title="Fabricantes por tipo de motor")
        st.plotly_chart(chart_style(fig, 440), width="stretch", config={"displayModeBar": False})
    with right:
        comparison = vehicles.groupby(["FINALIDADE", "MOTOR_VEIC"], dropna=False).size().reset_index(name="UCs")
        comparison["Finalidade"] = comparison["FINALIDADE"].map(clean_label)
        comparison["Motor"] = comparison["MOTOR_VEIC"].map(clean_label)
        fig = px.bar(comparison, x="Finalidade", y="UCs", color="Motor", barmode="group", text_auto=True, color_discrete_sequence=COLORS)
        fig.update_layout(title="Motor por finalidade")
        st.plotly_chart(chart_style(fig, 440), width="stretch", config={"displayModeBar": False})


def charging_page(frame: pd.DataFrame) -> None:
    title("Equipamentos", "Infraestrutura de recarga", "Compare a presença de wallbox e carregador portátil por perfil de veículo.")
    labels = {"S": "Sim", "N": "Não"}
    equipment = pd.DataFrame(
        {
            "Equipamento": ["Wallbox", "Wallbox", "Portátil", "Portátil"],
            "Disponibilidade": ["Sim", "Não", "Sim", "Não"],
            "UCs": [
                frame["STATUS_WALLBOX"].eq("S").sum(), frame["STATUS_WALLBOX"].eq("N").sum(),
                frame["STATUS_PORTATIL"].eq("S").sum(), frame["STATUS_PORTATIL"].eq("N").sum(),
            ],
        }
    )
    left, right = st.columns([1, 1.25])
    with left:
        fig = px.funnel(equipment, y="Equipamento", x="UCs", color="Disponibilidade", color_discrete_map={"Sim": "#F5821E", "Não": "#C8CDD0"})
        fig.update_layout(title="Disponibilidade dos equipamentos")
        st.plotly_chart(chart_style(fig, 430), width="stretch", config={"displayModeBar": False})
    with right:
        records = []
        for motor, group in frame.groupby(frame["MOTOR_VEIC"].map(clean_label)):
            for column, label in [("STATUS_WALLBOX", "Wallbox"), ("STATUS_PORTATIL", "Portátil")]:
                records.append({"Motor": motor, "Equipamento": label, "UCs com equipamento": int(group[column].eq("S").sum())})
        compare = pd.DataFrame(records)
        fig = px.bar(compare, x="Motor", y="UCs com equipamento", color="Equipamento", barmode="group", text_auto=True, color_discrete_sequence=["#F5821E", "#FDB422"])
        fig.update_layout(title="Equipamentos por tipo de motor")
        st.plotly_chart(chart_style(fig, 430), width="stretch", config={"displayModeBar": False})


def gd_page(frame: pd.DataFrame) -> None:
    title("Energia", "Geração distribuída", "Compare os tipos de GD e a evolução do início dos benefícios na base cadastrada.")
    gd = frame[frame["TIPO_GD_GERA"].notna()].copy()
    if gd.empty:
        empty_state(); return
    left, right = st.columns([1, 1.3])
    with left:
        types = count_table(gd, "TIPO_GD_GERA", "Tipo de GD")
        fig = px.pie(types, names="Tipo de GD", values="UCs", color_discrete_sequence=["#F5821E", "#FDB422"], hole=.42)
        fig.update_traces(textinfo="label+value+percent")
        fig.update_layout(title="Composição por tipo de GD")
        st.plotly_chart(chart_style(fig, 430), width="stretch", config={"displayModeBar": False})
    with right:
        dated = gd.dropna(subset=["DATA_INICIO_GD"]).copy()
        dated["Ano"] = dated["DATA_INICIO_GD"].dt.year
        evolution = dated.groupby(["Ano", "TIPO_GD_GERA"]).size().reset_index(name="Novas UCs")
        fig = px.area(evolution, x="Ano", y="Novas UCs", color="TIPO_GD_GERA", markers=True, color_discrete_sequence=["#F5821E", "#FDB422"])
        fig.update_layout(title="Evolução anual do início da GD", xaxis=dict(dtick=1))
        st.plotly_chart(chart_style(fig, 430), width="stretch", config={"displayModeBar": False})


def quality_page(frame: pd.DataFrame) -> None:
    title("Governança", "Qualidade dos dados", "Compare o preenchimento dos campos analíticos e consulte UCs sem expor dados pessoais.")
    key_columns = ["NUM_UC", "SITUACAO_ATUAL", "LOCAL", "TIPO_FASE", "ETAPA", "DT_ATIVACAO", "FINALIDADE", "FABRI_VEIC", "MOTOR_VEIC", "STATUS_WALLBOX", "STATUS_PORTATIL", "TIPO_GD_GERA"]
    quality = pd.DataFrame({
        "Campo": key_columns,
        "Preenchidos": [int(frame[c].notna().sum()) for c in key_columns],
        "Ausentes": [int(frame[c].isna().sum()) for c in key_columns],
    })
    quality["Completude"] = quality["Preenchidos"] / len(frame) if len(frame) else 0
    fig = go.Figure(go.Bar(
        x=quality["Completude"], y=quality["Campo"], orientation="h",
        text=(quality["Completude"] * 100).round(1).astype(str) + "%",
        marker=dict(color=quality["Completude"], colorscale=[[0, "#A83D2D"], [.5, "#FDB422"], [1, "#F5821E"]], cmin=0, cmax=1),
    ))
    fig.update_layout(title="Completude dos principais campos", xaxis=dict(tickformat=".0%", range=[0, 1.08]), yaxis=dict(autorange="reversed"))
    st.plotly_chart(chart_style(fig, 520), width="stretch", config={"displayModeBar": False})
    st.markdown("#### Consulta operacional (sem dados pessoais)")
    public_columns = ["NUM_UC", "NUM_UC_ANEEL", "SITUACAO_ATUAL", "SITUACAO_UC", "LOCAL", "CLASSE", "TIPO_FASE", "ETAPA", "DT_ATIVACAO", "FINALIDADE", "FABRI_VEIC", "MODELO_VEIC", "MOTOR_VEIC", "STATUS_WALLBOX", "STATUS_PORTATIL", "TIPO_GD_GERA"]
    view = frame[public_columns].copy()
    for column in ["NUM_UC", "NUM_UC_ANEEL"]:
        view[column] = view[column].apply(lambda value: "" if pd.isna(value) else str(int(value)))
    st.dataframe(view, width="stretch", hide_index=True, height=410)


inject_css()
render_brand_banner()
if not st.session_state.get("authenticated", False):
    login_screen()
    st.stop()

if not DATA_FILE.exists():
    st.error(f"Arquivo de dados não encontrado: {DATA_FILE.name}")
    st.stop()

data = load_data(DATA_FILE.stat().st_mtime)
filtered_data, selected_page, gd_reference_date = sidebar_filters(data)

if filtered_data.empty:
    title("Filtros", selected_page, "A combinação atual não retornou registros.")
    empty_state()
elif selected_page == "Resumo executivo":
    executive_page(filtered_data, gd_reference_date)
elif selected_page == "UCs e localização":
    uc_page(filtered_data)
elif selected_page == "Perfil dos veículos":
    vehicle_page(filtered_data)
elif selected_page == "Infraestrutura de recarga":
    charging_page(filtered_data)
elif selected_page == "Geração distribuída":
    gd_page(filtered_data)
else:
    quality_page(filtered_data)

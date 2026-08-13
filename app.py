from __future__ import annotations

import base64
import hashlib
import hmac
import json
import mimetypes
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


APP_TITLE = "BI Cadastro | Copel"
DATA_FILE = Path(__file__).with_name("base_consolidada_BI.csv")
ASSET_DIR = Path(__file__).with_name("assets")
MUNICIPALITY_COORDINATES_FILE = ASSET_DIR / "municipios_coordenadas.csv"
PARANA_BOUNDARY_FILE = ASSET_DIR / "parana_contorno.geojson"
UPDATE_ALERT_FILE = Path(__file__).with_name("data") / "ultima_atualizacao_alertas.csv"
UPDATE_HISTORY_FILE = Path(__file__).with_name("data") / "historico_alertas.csv"
UPDATE_SUMMARY_FILE = Path(__file__).with_name("data") / "ultima_atualizacao_resumo.json"
MEASUREMENT_DIR = Path(__file__).with_name("relatorio_medicao")
MEASUREMENT_ALERT_FILE = MEASUREMENT_DIR / "relatorio_alertas_por_uc.csv"
MEASUREMENT_GAPS_FILE = MEASUREMENT_DIR / "detalhe_gaps.csv"
LOGIN_USER = "Copel"
PASSWORD_SALT = b"copel-bi-cadastro-v1"
PASSWORD_HASH = bytes.fromhex(
    "09e79419c0d0ef10fb06c88f9a68195b02c4954873140d6b0974f22e3f9fae10"
)
COLORS = ["#F5821E", "#FDB422", "#E65D24", "#3F444B", "#69727D", "#8D3F8F"]
PROJECT_START_DATE = pd.Timestamp("2026-03-01")
PLOTLY_CONFIG = {
    "displayModeBar": True,
    "displaylogo": False,
    "modeBarButtonsToRemove": [
        "zoom2d",
        "pan2d",
        "select2d",
        "lasso2d",
        "zoomIn2d",
        "zoomOut2d",
        "autoScale2d",
        "resetScale2d",
    ],
    "toImageButtonOptions": {
        "format": "png",
        "filename": "bi_cadastro",
        "scale": 2,
    },
}

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
        [data-testid="stSidebar"] [data-testid="stDateInput"] input {
            color: #151C21 !important;
        }
        [data-testid="stSidebar"] [data-testid="stButtonGroup"] button,
        [data-testid="stSidebar"] [data-testid="stButtonGroup"] button * {
            color:#151C21 !important; font-weight:700 !important;
        }
        [data-testid="stSidebar"] [data-testid="stButtonGroup"] button {
            background:#F7F8F8 !important; border:1px solid #C8CDD0 !important;
            min-height:36px; padding:6px 13px !important; white-space:nowrap;
        }
        [data-testid="stSidebar"] [data-testid="stButtonGroup"] button[data-variant="pills"][data-selected],
        [data-testid="stSidebar"] [data-testid="stButtonGroup"] button[data-variant="pills"][data-selected] * {
            background:#F5821E !important; border-color:#F5821E !important;
            color:#FFFFFF !important;
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
        .data-disclaimer {
            margin:-10px 0 24px 0; padding:10px 14px;
            border-left:4px solid #FDB422; border-radius:8px;
            background:#FFF7E6; color:#4A3B20; font-size:.86rem;
        }
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
        .brand-logos { display:flex; align-items:center; gap:18px; flex-shrink:0; }
        .copel-logo { width:190px; height:auto; display:block; }
        .brand-separator { height:54px; width:1px; background:rgba(255,255,255,.28); }
        .essenz-panel, .daimon-panel { display:flex; align-items:center; justify-content:center;
            width:145px; height:70px; }
        .essenz-logo, .daimon-logo {
            max-width:140px; max-height:62px; width:auto; height:auto; display:block;
        }
        @media (max-width: 760px) {
            .brand-banner { align-items:flex-start; flex-direction:column; padding:19px; }
            .brand-logos { width:100%; justify-content:flex-start; gap:12px; flex-wrap:wrap; }
            .brand-separator { display:none; }
            .copel-logo { width:170px; }
            .essenz-panel, .daimon-panel { width:135px; height:62px; }
            .essenz-logo, .daimon-logo { max-width:130px; max-height:56px; }
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
    daimon_logo = asset_data_uri("logo-daimon.svg")
    st.markdown(
        f"""
        <div class="brand-banner">
            <div>
                <div class="banner-kicker">Tarifa Mobiflex</div>
                <div class="banner-title">BI Cadastral</div>
                <div class="banner-copy">Indicadores consolidados</div>
            </div>
            <div class="brand-logos">
                <img class="copel-logo" src="{copel_logo}" alt="COPEL — Pura Energia">
                <div class="brand-separator"></div>
                <div class="essenz-panel">
                    <img class="essenz-logo" src="{essenz_logo}" alt="Essenz Soluções">
                </div>
                <div class="brand-separator"></div>
                <div class="daimon-panel">
                    <img class="daimon-logo" src="{daimon_logo}" alt="Daimon Engenharia">
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def latest_report_date() -> pd.Timestamp | None:
    report_dates = []
    data_directory = Path(__file__).with_name("data")
    for path in data_directory.glob("mdm-sandbox_clientes_novo-*.csv"):
        date_text = path.stem.rsplit("-", maxsplit=1)[-1]
        parsed = pd.to_datetime(date_text, format="%Y%m%d", errors="coerce")
        if pd.notna(parsed):
            report_dates.append(parsed)
    if report_dates:
        return max(report_dates)
    if UPDATE_SUMMARY_FILE.exists():
        try:
            summary = json.loads(UPDATE_SUMMARY_FILE.read_text(encoding="utf-8"))
            parsed = pd.to_datetime(
                summary.get("periodo_fim"), format="%Y%m%d", errors="coerce"
            )
            if pd.notna(parsed):
                return parsed
        except (OSError, json.JSONDecodeError):
            pass
    return None


def render_data_disclaimer() -> None:
    report_date = latest_report_date()
    formatted_date = (
        f"{report_date:%d-%m-%Y}" if report_date is not None else "não identificada"
    )
    st.markdown(
        '<div class="data-disclaimer">'
        f"Dados atualizados à partir do relatório feito em {formatted_date}, "
        "e no arquivo Amostra Final - Tarifa Mobiflex - 14.07.2026"
        "</div>",
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
            '<div class="brand-mark">BI <span>Cadastral</span></div>',
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
        "DT_SITUACAO_UC",
        "DT_MUD_TIT",
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


@st.cache_data
def load_map_assets() -> tuple[pd.DataFrame, dict]:
    coordinates = pd.read_csv(MUNICIPALITY_COORDINATES_FILE, encoding="utf-8")
    boundary = json.loads(PARANA_BOUNDARY_FILE.read_text(encoding="utf-8"))
    return coordinates, boundary


@st.cache_data
def load_update_report(
    history_mtime: float, alerts_mtime: float, summary_mtime: float
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    del history_mtime, alerts_mtime, summary_mtime
    history = pd.read_csv(
        UPDATE_HISTORY_FILE,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )
    latest = pd.read_csv(
        UPDATE_ALERT_FILE,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )
    summary = json.loads(UPDATE_SUMMARY_FILE.read_text(encoding="utf-8"))
    return history, latest, summary


@st.cache_data(show_spinner="Carregando relatório de medição...")
def load_measurement_alerts(file_mtime: float) -> pd.DataFrame:
    del file_mtime
    frame = pd.read_csv(
        MEASUREMENT_ALERT_FILE,
        sep=";",
        dtype={"uc": "string", "medidor_arquivo_normalizado": "string"},
        encoding="utf-8-sig",
    )
    for column in ["primeira_leitura", "ultima_leitura", "fim_dados_origem"]:
        frame[column] = pd.to_datetime(frame[column], errors="coerce")
    numeric_columns = [
        "atraso_min",
        "intervalo_predominante_min",
        "registros",
        "gaps",
        "intervalos_ausentes",
    ]
    frame[numeric_columns] = frame[numeric_columns].apply(
        pd.to_numeric, errors="coerce"
    )
    frame["dias_sem_comunicacao"] = frame["atraso_min"].fillna(0) / 1_440
    return frame


@st.cache_data(show_spinner="Carregando lacunas de medição...")
def load_measurement_gaps(file_mtime: float) -> pd.DataFrame:
    del file_mtime
    frame = pd.read_csv(
        MEASUREMENT_GAPS_FILE,
        sep=";",
        dtype={"uc": "string", "medidor_normalizado": "string"},
        encoding="utf-8-sig",
    )
    frame["inicio_gap"] = pd.to_datetime(frame["inicio_gap"], errors="coerce")
    frame["fim_gap"] = pd.to_datetime(frame["fim_gap"], errors="coerce")
    frame["intervalos_ausentes"] = pd.to_numeric(
        frame["intervalos_ausentes"], errors="coerce"
    ).fillna(0)
    return frame


MONTH_NAMES = {
    1: "Janeiro",
    2: "Fevereiro",
    3: "Março",
    4: "Abril",
    5: "Maio",
    6: "Junho",
    7: "Julho",
    8: "Agosto",
    9: "Setembro",
    10: "Outubro",
    11: "Novembro",
    12: "Dezembro",
}
EXPERIMENT_START_DATE = pd.Timestamp("2026-03-01")
ALERT_FIELD_LABELS = {
    "SITUACAO_UC": "Situação da UC alterada",
    "CLASSE": "Classe da UC alterada",
    "GRUPO": "Grupo tarifário alterado",
    "GD_BENE_INIC": "Início como beneficiária de GD",
    "GD_BENE_FIM": "Fim do vínculo como beneficiária de GD",
    "TIPO_GD_BENE": "Tipo de GD beneficiária alterado",
    "DATA_INICIO_GD": "Início da geração distribuída",
    "DATA_FIM_GD": "Fim da geração distribuída",
    "TIPO_GD_GERA": "Tipo de GD geradora alterado",
    "TARIFA_SOCIAL": "Tarifa social ativada",
    "TARIFA_BRANCA": "Tarifa branca ativada",
    "MUD_TIT": "Mudança de titularidade",
    "PRESENCA_NO_RELATORIO": "UC ausente no último relatório",
}


def alert_period_label(value: object) -> str:
    date = pd.to_datetime(value, errors="coerce")
    if pd.isna(date):
        return "Sem data"
    if date.normalize() < EXPERIMENT_START_DATE:
        return "Inicial"
    month = MONTH_NAMES[date.month]
    return month if date.year == EXPERIMENT_START_DATE.year else f"{month}/{date.year}"


def clean_label(value: object) -> str:
    return "Não informado" if pd.isna(value) or str(value).strip() == "" else str(value)


def status_display_label(value: object) -> str:
    return {
        "Ativo": "Tratamento",
        "Ativos": "Tratamento",
        "Ativa": "Tratamento",
        "Ativas": "Tratamento",
        "Removido Ativo": "Removido Tratamento",
        "Removida Ativa": "Removida Tratamento",
    }.get(str(value), str(value))


def options_for(frame: pd.DataFrame, column: str) -> list[str]:
    return sorted(frame[column].dropna().astype(str).unique().tolist())


def apply_reference_period(period_dates: dict[str, pd.Timestamp]) -> None:
    selected = st.session_state.get("reference_period")
    if selected in period_dates:
        st.session_state["reference_date"] = period_dates[selected].date()


def clear_reference_period() -> None:
    st.session_state["reference_period"] = None


def sidebar_filters(frame: pd.DataFrame) -> tuple[pd.DataFrame, str, pd.Timestamp]:
    st.sidebar.markdown("## BI Cadastro")
    page = st.sidebar.radio(
        "Navegação",
        [
            "Geral",
            "UCs e localização",
            "Perfil dos veículos",
            "Infraestrutura de recarga",
            "Geração distribuída",
            "Atualizações e alertas",
            "Alertas de comunicação",
            "Disponibilidade de medição",
            "UCs removidas",
        ],
        label_visibility="collapsed",
    )

    st.sidebar.divider()
    st.sidebar.markdown("### Filtros globais")
    st.sidebar.markdown(
        '<p class="filter-caption">Seleção vazia considera todos os valores.</p>',
        unsafe_allow_html=True,
    )
    if "reference_date" not in st.session_state:
        st.session_state["reference_date"] = PROJECT_START_DATE.date()
    gd_reference_date = pd.Timestamp(
        st.sidebar.date_input(
            "Data de referência",
            key="reference_date",
            format="DD/MM/YYYY",
            on_change=clear_reference_period,
            help=(
                "Recalcula a GD inicial e a situação das UCs na data "
                "selecionada."
            ),
        )
    )

    latest_date = latest_report_date() or PROJECT_START_DATE
    period_dates = {"Inicial": PROJECT_START_DATE - pd.Timedelta(days=1)}
    for month_start in pd.date_range(
        PROJECT_START_DATE.replace(day=1),
        latest_date.replace(day=1),
        freq="MS",
    ):
        label = MONTH_NAMES[month_start.month]
        if month_start.year != PROJECT_START_DATE.year:
            label = f"{label}/{month_start.year}"
        month_end = month_start + pd.offsets.MonthEnd(0)
        period_dates[label] = min(month_end, latest_date)
    st.sidebar.pills(
        "Atalhos por período",
        list(period_dates),
        selection_mode="single",
        label_visibility="collapsed",
        key="reference_period",
        on_change=apply_reference_period,
        args=(period_dates,),
    )

    reference_frame = frame.copy()
    if page != "UCs removidas":
        reference_frame["SITUACAO_ATUAL"] = reference_frame[
            "SITUACAO_INICIAL"
        ].fillna(reference_frame["SITUACAO_ATUAL"])
        removed_by_reference_date = (
            reference_frame["DT_DISTRATO"].notna()
            & reference_frame["DT_DISTRATO"].le(gd_reference_date)
        )
        reference_frame.loc[removed_by_reference_date, "SITUACAO_ATUAL"] = "Removido"

    status_options = list(
        dict.fromkeys(
            status_display_label(value)
            for value in options_for(reference_frame, "SITUACAO_ATUAL")
        )
    )

    filters = {
        "SITUACAO_ATUAL": st.sidebar.multiselect(
            "Situação atual",
            status_options,
            help="Situação calculada conforme a data de referência e o DT_DISTRATO.",
        ),
        "LOCAL": st.sidebar.multiselect(
            "Município", options_for(reference_frame, "LOCAL")
        ),
        "FINALIDADE": st.sidebar.multiselect(
            "Finalidade", options_for(reference_frame, "FINALIDADE")
        ),
        "FABRI_VEIC": st.sidebar.multiselect(
            "Fabricante do veículo", options_for(reference_frame, "FABRI_VEIC")
        ),
    }

    filtered = reference_frame.copy()
    st.session_state["global_filters_active"] = any(filters.values())
    for column, chosen in filters.items():
        if chosen:
            source_values = chosen
            if column == "SITUACAO_ATUAL":
                source_values = [
                    "Ativo" if value == "Tratamento" else value
                    for value in chosen
                ]
            filtered = filtered[filtered[column].astype(str).isin(source_values)]

    st.sidebar.divider()
    if st.sidebar.button("Sair", width="stretch"):
        st.session_state.authenticated = False
        st.rerun()
    return filtered, page, gd_reference_date


def title(kicker: str, heading: str, subtitle: str) -> None:
    heading_html = f'<div class="page-title">{heading}</div>' if heading else ""
    subtitle_html = (
        f'<div class="page-subtitle">{subtitle}</div>' if subtitle else ""
    )
    st.markdown(
        f'<div class="page-kicker">{kicker}</div>'
        f'{heading_html}'
        f'{subtitle_html}',
        unsafe_allow_html=True,
    )


def empty_state() -> None:
    st.warning("Nenhuma UC corresponde aos filtros selecionados.")


def metric_calculation_help(
    label: str, reference_date: pd.Timestamp | None = None
) -> str:
    rules = {
        "UCs monitoradas": (
            "Quantidade de UCs distintas no relat\u00f3rio de medi\u00e7\u00e3o ap\u00f3s "
            "a aplica\u00e7\u00e3o dos filtros selecionados."
        ),
        "Sem comunica\u00e7\u00e3o": (
            "Quantidade de UCs filtradas cujo relat\u00f3rio marca "
            "alerta_sem_comunicacao como SIM."
        ),
        "\u00daltima data de medi\u00e7\u00e3o dispon\u00edvel": (
            "Data mais recente encontrada em ultima_leitura entre as UCs "
            "exibidas pelos filtros de comunica\u00e7\u00e3o."
        ),
        "Disponibilidade geral": (
            "Para a UC selecionada: 1 menos os intervalos ausentes divididos "
            "pelos intervalos esperados entre a primeira e a \u00faltima leitura."
        ),
        "Grupo": "Grupo experimental da UC selecionada na base cadastral.",
        "Registros recebidos": (
            "Quantidade total de registros de medi\u00e7\u00e3o recebidos para a UC selecionada."
        ),
        "Intervalos ausentes": (
            "Quantidade de intervalos esperados sem leitura para a UC selecionada."
        ),
        "Intervalo esperado": (
            "Intervalo predominante, em minutos, entre as leituras da UC selecionada."
        ),
        "Dados dispon\u00edveis at\u00e9": (
            "Data de ultima_leitura mais recente no conjunto de UCs abrangido "
            "pelos filtros globais."
        ),
        "UCs — Tratamento": "UCs do grupo Tratamento de acordo com os filtros ativos.",
        "UCs — Controle": "UCs do grupo Controle de acordo com os filtros ativos.",
        "UCs — Reserva": "UCs do grupo Reserva de acordo com os filtros ativos.",
        "UCs removidas — Controle": "UCs removidas do grupo Controle de acordo com os filtros ativos.",
        "UCs removidas — Tratamento": "UCs removidas do grupo Tratamento de acordo com os filtros ativos.",
        "UCs com alertas": "Quantidade de UCs com pelo menos uma linha de alerta na seção e nos filtros selecionados.",
        "Sem atualização": "Quantidade distinta de UCs da base que não aparecem no relatório.",
        "Desligamentos": "Quantidade distinta de UCs cuja situação mudou para DS (Desligamento) ou CR (Corte).",
        "Mudanças de Titularidade": "Quantidade distinta de UCs com mudança de titularidade.",
        "Mudança de Classe": "Quantidade distinta de UCs com mudança de Classe e/ou Subgrupo.",
        "Tarifas Especiais Ativadas": "Quantidade distinta de UCs que passaram a ter tarifa social ou tarifa branca.",
        "Alterações GD": "Quantidade distinta de UCs que viraram beneficiárias ou geradoras de geração distribuída.",
    }
    if label in rules:
        return rules[label]
    if label.startswith("GD "):
        group = "Tratamento" if "Tratamento" in label else "Controle"
        if label.endswith("inicial"):
            period_description = (
                f"até a data inicial, {PROJECT_START_DATE:%d/%m/%Y}"
            )
        else:
            effective_reference = (
                reference_date
                if reference_date is not None
                else PROJECT_START_DATE
            )
            period_description = (
                f"até a data de referência, {effective_reference:%d/%m/%Y}"
            )
        return (
            f"Quantidade de UCs inicial do {group} {period_description}. "
            "Casos com início e fim da GD beneficiária no mesmo dia são excluídos; o percentual usa o total inicial do grupo."
        )
    if "Uso Pessoal" in label or "Trabalho" in label or "Não informada" in label:
        group = "Tratamento" if "Tratamento" in label else "Controle"
        category = label.split(" — ")[0]
        return (
            f"Quantidade de UCs do {group} com finalidade de {category} de acordo com os filtros; o percentual divide "
            f"essa contagem pelo total filtrado de UCs do {group}."
        )
    if "com veículo" in label:
        return "Quantidade de UCs do grupo indicado com informação do veículo preenchida; o percentual divide a contagem pelo total filtrado de UCs do grupo indicado."
    if "com wallbox" in label:
        return "Quantidade de UCs do grupo indicado que possuem wallbox; o percentual divide a contagem pelo total filtrado de UCs do grupo indicado."
    if "com portátil" in label:
        return "Quantidade de UCs do grupo indicado que possuem carreador portátil; o percentual divide a contagem pelo total filtrado de UCs do grupo indicado."
    return "Valor calculado sobre as UCs resultantes dos filtros ativos da barra lateral."


def show_metric(
    container,
    label: str,
    value: object,
    *args,
    reference_date: pd.Timestamp | None = None,
    **kwargs,
) -> None:
    kwargs.setdefault("help", metric_calculation_help(label, reference_date))
    container.metric(label, value, *args, **kwargs)


def chart_style(fig: go.Figure, height: int = 390) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=20, r=20, t=55, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Arial", color="#33373D"),
        colorway=COLORS,
        legend_title_text="",
        uniformtext=dict(minsize=12, mode="show"),
    )
    return fig


def count_table(frame: pd.DataFrame, column: str, name: str) -> pd.DataFrame:
    values = frame[column].map(clean_label).value_counts().rename_axis(name).reset_index(name="UCs")
    return values


def executive_page(frame: pd.DataFrame, gd_reference_date: pd.Timestamp) -> None:
    title(
        "Visão consolidada",
        "",
        "Indicadores principais das unidades consumidoras conforme os filtros selecionados.",
    )
    active_initial = int(frame["SITUACAO_INICIAL"].eq("Ativo").sum())
    active = int(frame["SITUACAO_ATUAL"].eq("Ativo").sum())
    control_initial = int(frame["SITUACAO_INICIAL"].eq("Controle").sum())
    control = int(frame["SITUACAO_ATUAL"].eq("Controle").sum())
    reserve = int(frame["SITUACAO_ATUAL"].eq("Reserva").sum())
    removed_mask = frame["SITUACAO_ATUAL"].eq("Removido")
    removed_control = int(
        (removed_mask & frame["SITUACAO_INICIAL"].eq("Controle")).sum()
    )
    removed_treatment = int(
        (removed_mask & frame["SITUACAO_INICIAL"].eq("Ativo")).sum()
    )
    active_mask = frame["SITUACAO_ATUAL"].eq("Ativo")
    control_mask = frame["SITUACAO_ATUAL"].eq("Controle")
    active_with_vehicle = int((active_mask & frame["FABRI_VEIC"].notna()).sum())
    control_with_vehicle = int((control_mask & frame["FABRI_VEIC"].notna()).sum())
    active_with_wallbox = int((active_mask & frame["STATUS_WALLBOX"].eq("S")).sum())
    control_with_wallbox = int((control_mask & frame["STATUS_WALLBOX"].eq("S")).sum())
    active_with_portable = int((active_mask & frame["STATUS_PORTATIL"].eq("S")).sum())
    control_with_portable = int((control_mask & frame["STATUS_PORTATIL"].eq("S")).sum())
    active_vehicle_percentage = active_with_vehicle / active if active else 0
    control_vehicle_percentage = control_with_vehicle / control if control else 0
    active_wallbox_percentage = active_with_wallbox / active if active else 0
    control_wallbox_percentage = control_with_wallbox / control if control else 0
    active_portable_percentage = active_with_portable / active if active else 0
    control_portable_percentage = control_with_portable / control if control else 0
    purpose = frame["FINALIDADE"].map(clean_label)
    active_personal = int((active_mask & purpose.eq("Pessoal")).sum())
    active_work = int((active_mask & purpose.eq("Trabalho")).sum())
    active_purpose_missing = int((active_mask & purpose.eq("Não informado")).sum())
    control_personal = int((control_mask & purpose.eq("Pessoal")).sum())
    control_work = int((control_mask & purpose.eq("Trabalho")).sum())
    control_purpose_missing = int(
        (control_mask & purpose.eq("Não informado")).sum()
    )
    active_personal_percentage = active_personal / active if active else 0
    active_work_percentage = active_work / active if active else 0
    active_purpose_missing_percentage = (
        active_purpose_missing / active if active else 0
    )
    control_personal_percentage = control_personal / control if control else 0
    control_work_percentage = control_work / control if control else 0
    control_purpose_missing_percentage = (
        control_purpose_missing / control if control else 0
    )
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
    row1 = st.columns(5)
    show_metric(row1[0], "UCs — Tratamento", f"{active:,}".replace(",", "."))
    show_metric(row1[1], "UCs — Controle", f"{control:,}".replace(",", "."))
    show_metric(row1[2], "UCs — Reserva", f"{reserve:,}".replace(",", "."))
    show_metric(
        row1[3],
        "UCs removidas — Tratamento",
        f"{removed_treatment:,}".replace(",", "."),
    )
    show_metric(
        row1[4],
        "UCs removidas — Controle",
        f"{removed_control:,}".replace(",", "."),
    )
    st.caption(
        f"GD inicial em {PROJECT_START_DATE:%d/%m/%Y} · "
        f"GD filtrada em {gd_reference_date:%d/%m/%Y}"
    )
    gd_row = st.columns(4)
    show_metric(
        gd_row[0],
        "GD Tratamento — inicial",
        f"{active_initial_gd:,}".replace(",", "."),
        f"{active_initial_gd_percentage:.1%}".replace(".", ","),
        delta_color="normal",
    )
    show_metric(
        gd_row[1],
        "GD Controle — inicial",
        f"{control_initial_gd:,}".replace(",", "."),
        f"{control_initial_gd_percentage:.1%}".replace(".", ","),
        delta_color="normal",
    )
    show_metric(
        gd_row[2],
        "GD Tratamento — filtrada",
        f"{active_filtered_gd:,}".replace(",", "."),
        f"{active_filtered_gd_percentage:.1%}".replace(".", ","),
        reference_date=gd_reference_date,
        delta_color="normal",
    )
    show_metric(
        gd_row[3],
        "GD Controle — filtrada",
        f"{control_filtered_gd:,}".replace(",", "."),
        f"{control_filtered_gd_percentage:.1%}".replace(".", ","),
        reference_date=gd_reference_date,
        delta_color="normal",
    )
    st.caption("Finalidade por situação atual")
    active_purpose_row = st.columns(3)
    show_metric(
        active_purpose_row[0],
        "Uso Pessoal — Tratamento",
        f"{active_personal:,}".replace(",", "."),
        f"{active_personal_percentage:.1%}".replace(".", ","),
        delta_color="normal",
    )
    show_metric(
        active_purpose_row[1],
        "Trabalho — Tratamento",
        f"{active_work:,}".replace(",", "."),
        f"{active_work_percentage:.1%}".replace(".", ","),
        delta_color="normal",
    )
    show_metric(
        active_purpose_row[2],
        "Não informada — Tratamento",
        f"{active_purpose_missing:,}".replace(",", "."),
        f"{active_purpose_missing_percentage:.1%}".replace(".", ","),
        delta_color="normal",
    )
    control_purpose_row = st.columns(3)
    show_metric(
        control_purpose_row[0],
        "Uso Pessoal — Controle",
        f"{control_personal:,}".replace(",", "."),
        f"{control_personal_percentage:.1%}".replace(".", ","),
        delta_color="normal",
    )
    show_metric(
        control_purpose_row[1],
        "Trabalho — Controle",
        f"{control_work:,}".replace(",", "."),
        f"{control_work_percentage:.1%}".replace(".", ","),
        delta_color="normal",
    )
    show_metric(
        control_purpose_row[2],
        "Não informada — Controle",
        f"{control_purpose_missing:,}".replace(",", "."),
        f"{control_purpose_missing_percentage:.1%}".replace(".", ","),
        delta_color="normal",
    )
    st.caption("Dados de Veículos e Carregadores com filtros selecionados")
    active_equipment_row = st.columns(3)
    show_metric(
        active_equipment_row[0],
        "UCs com veículo — Tratamento",
        f"{active_with_vehicle:,}".replace(",", "."),
        f"{active_vehicle_percentage:.1%}".replace(".", ","),
        delta_color="normal",
    )
    show_metric(
        active_equipment_row[1],
        "UCs com wallbox — Tratamento",
        f"{active_with_wallbox:,}".replace(",", "."),
        f"{active_wallbox_percentage:.1%}".replace(".", ","),
        delta_color="normal",
    )
    show_metric(
        active_equipment_row[2],
        "UCs com portátil — Tratamento",
        f"{active_with_portable:,}".replace(",", "."),
        f"{active_portable_percentage:.1%}".replace(".", ","),
        delta_color="normal",
    )
    control_equipment_row = st.columns(3)
    show_metric(
        control_equipment_row[0],
        "UCs com veículo — Controle",
        f"{control_with_vehicle:,}".replace(",", "."),
        f"{control_vehicle_percentage:.1%}".replace(".", ","),
        delta_color="normal",
    )
    show_metric(
        control_equipment_row[1],
        "UCs com wallbox — Controle",
        f"{control_with_wallbox:,}".replace(",", "."),
        f"{control_wallbox_percentage:.1%}".replace(".", ","),
        delta_color="normal",
    )
    show_metric(
        control_equipment_row[2],
        "UCs com portátil — Controle",
        f"{control_with_portable:,}".replace(",", "."),
        f"{control_portable_percentage:.1%}".replace(".", ","),
        delta_color="normal",
    )
    st.markdown("#### Comparativos consolidados")
    donut_column, manufacturer_column = st.columns([1.35, 1])
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
    status_pairs = [
        ("Ativo", "Tratamento"),
        ("Controle", "Controle"),
        ("Removido Ativo", "Removido Tratamento"),
        ("Removido Controle", "Removido Controle"),
    ]
    status_order = [display for _, display in status_pairs]
    status_counts = status_population["Situação na referência"].value_counts()
    status = pd.DataFrame(
        {
            "Situação": status_order,
            "UCs": [
                int(status_counts.get(source, 0)) for source, _ in status_pairs
            ],
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
    with donut_column:
        fig = px.pie(
            status,
            names="Situação",
            values="UCs",
            hole=.64,
            color="Situação",
            color_discrete_map={
                "Tratamento": "#F5821E",
                "Controle": "#FDB422",
                "Removido Tratamento": "#3F444B",
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
        fig.update_layout(
            title=f"Situação em {gd_reference_date:%d/%m/%Y}",
            showlegend=False,
        )
        fig = chart_style(fig, 520)
        fig.update_layout(
            margin=dict(l=95, r=95, t=75, b=115),
        )
        fig.add_annotation(text=f"<b>{status_total}</b><br>UCs", showarrow=False, font_size=18)
        st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)
    with manufacturer_column:
        vehicle_population = frame[
            (active_mask | control_mask) & frame["FABRI_VEIC"].notna()
        ]
        if vehicle_population.empty:
            st.info("Nenhum fabricante encontrado para os filtros selecionados.")
        else:
            manufacturers = count_table(
                vehicle_population, "FABRI_VEIC", "Fabricante"
            ).sort_values("UCs")
            fig = px.bar(
                manufacturers,
                x="UCs",
                y="Fabricante",
                orientation="h",
                text="UCs",
                color="UCs",
                color_continuous_scale=["#FBE8D8", "#F5821E"],
            )
            fig.update_layout(
                title="Fabricantes — UCs em tratamento e controle",
                coloraxis_showscale=False,
                yaxis_title="",
            )
            fig.update_traces(textposition="outside")
            st.plotly_chart(
                chart_style(fig, 520),
                width="stretch",
                config=PLOTLY_CONFIG,
            )

    st.markdown("#### Distribuição municipal de UCs em tratamento e controle")
    map_population = frame[
        (active_mask | control_mask) & frame["LOCAL"].notna()
    ].copy()
    map_population["Situação"] = map_population["SITUACAO_ATUAL"].replace(
        {"Ativo": "Tratamento"}
    )
    map_data = (
        map_population.groupby(["LOCAL", "Situação"])
        .size()
        .reset_index(name="UCs")
    )
    municipality_coordinates, parana_boundary = load_map_assets()
    map_data = map_data.merge(municipality_coordinates, on="LOCAL", how="inner")

    if map_data.empty:
        st.info("Nenhum município com UCs em tratamento ou controle para exibir no mapa.")
    else:
        # Slightly separate both statuses around the municipal centroid so that
        # overlapping bubbles remain visible and selectable.
        longitude_offset = {"Tratamento": -0.025, "Controle": 0.025}
        map_data["map_longitude"] = (
            map_data["longitude"] + map_data["Situação"].map(longitude_offset)
        )
        fig = px.scatter_map(
            map_data,
            lat="latitude",
            lon="map_longitude",
            size="UCs",
            color="Situação",
            hover_name="LOCAL",
            hover_data={
                "UCs": True,
                "latitude": False,
                "map_longitude": False,
            },
            color_discrete_map={
                "Tratamento": "#F5821E",
                "Controle": "#69727D",
            },
            category_orders={"Situação": ["Controle", "Tratamento"]},
            size_max=42,
            zoom=5.7,
            center={"lat": -25.35, "lon": -52.15},
            map_style="carto-positron",
        )
        fig.update_traces(marker_opacity=0.76)
        fig.update_layout(
            map_layers=[
                dict(
                    sourcetype="geojson",
                    source=parana_boundary,
                    type="line",
                    color="#8D979C",
                    opacity=0.72,
                    line=dict(width=2),
                )
            ]
        )
        fig = chart_style(fig, 620)
        fig.update_layout(
            margin=dict(l=10, r=10, t=15, b=10),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.01,
                xanchor="left",
                x=0,
            ),
        )
        st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)
        st.caption(
            "O tamanho das bolhas representa a quantidade de UCs. Os pontos "
            "são levemente separados ao redor do centro municipal para manter "
            "Tratamento e Controle visíveis."
        )


def uc_page(frame: pd.DataFrame) -> None:
    title(
        "Distribuição operacional",
        "UCs e localização",
        "Compare a distribuição municipal das UCs em tratamento, controle e reserva.",
    )
    status_labels = {
        "Ativo": "Tratamento",
        "Controle": "Controle",
        "Reserva": "Reserva",
    }
    status_colors = {
        "Tratamento": "#F5821E",
        "Controle": "#69727D",
        "Reserva": "#6EBAE8",
    }
    location_population = frame[
        frame["SITUACAO_ATUAL"].isin(status_labels)
        & frame["LOCAL"].notna()
        & frame["LOCAL"].astype(str).str.strip().ne("")
    ].copy()
    location_population["Situação"] = location_population[
        "SITUACAO_ATUAL"
    ].replace(status_labels)
    city_status = (
        location_population.groupby(["LOCAL", "Situação"])
        .size()
        .reset_index(name="UCs")
        .rename(columns={"LOCAL": "Município"})
    )

    if city_status.empty:
        empty_state()
        return

    city_totals = city_status.groupby("Município")["UCs"].sum()
    chart_height = max(620, 115 + 30 * len(city_totals))
    fig = px.bar(
        city_status,
        x="UCs",
        y="Município",
        color="Situação",
        orientation="h",
        barmode="stack",
        text="UCs",
        color_discrete_map=status_colors,
        category_orders={
            "Situação": ["Tratamento", "Controle", "Reserva"],
        },
    )
    fig.update_traces(textposition="inside", textangle=0)
    fig.update_layout(
        title="Municípios por situação",
        legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0),
        yaxis=dict(title="", categoryorder="total ascending"),
    )
    with st.container(height=600, border=False):
        st.plotly_chart(
            chart_style(fig, chart_height),
            width="stretch",
            config=PLOTLY_CONFIG,
        )

    st.markdown("#### Mapas por situação")
    municipality_coordinates, parana_boundary = load_map_assets()
    mapped_status = city_status.merge(
        municipality_coordinates,
        left_on="Município",
        right_on="LOCAL",
        how="inner",
    )
    maximum_city_count = int(mapped_status["UCs"].max()) if not mapped_status.empty else 1
    common_size_reference = 2 * maximum_city_count / (38 ** 2)
    first_map_row = st.columns(2)
    second_map_row = st.columns([1, 2, 1])
    map_columns = [first_map_row[0], first_map_row[1], second_map_row[1]]

    for column, situation in zip(
        map_columns, ["Tratamento", "Controle", "Reserva"]
    ):
        situation_map = mapped_status[mapped_status["Situação"].eq(situation)]
        with column:
            if situation_map.empty:
                st.info(f"Nenhuma UC em {situation.lower()} para exibir.")
                continue
            fig = px.scatter_map(
                situation_map,
                lat="latitude",
                lon="longitude",
                size="UCs",
                hover_name="Município",
                hover_data={"UCs": True, "latitude": False, "longitude": False},
                color_discrete_sequence=[status_colors[situation]],
                size_max=38,
                zoom=4.7,
                center={"lat": -24.75, "lon": -51.75},
                map_style="carto-positron",
            )
            fig.update_traces(
                marker_opacity=0.78,
                marker_sizeref=common_size_reference,
                marker_sizemin=4,
            )
            fig.update_layout(
                title=situation,
                map_layers=[
                    dict(
                        sourcetype="geojson",
                        source=parana_boundary,
                        type="line",
                        color="#8D979C",
                        opacity=0.72,
                        line=dict(width=2),
                    )
                ],
            )
            fig = chart_style(fig, 480)
            fig.update_layout(margin=dict(l=5, r=5, t=50, b=5))
            st.plotly_chart(
                fig,
                width="stretch",
                config=PLOTLY_CONFIG,
            )


def vehicle_page(frame: pd.DataFrame) -> None:
    title("Veículos Elétricos", "Perfil dos veículos", "Compare fabricantes, motorização e finalidade dos veículos cadastrados.")
    vehicles = frame[frame["FABRI_VEIC"].notna()].copy()
    if vehicles.empty:
        empty_state(); return
    with st.container():
        manufacturer_vehicles = vehicles[
            vehicles["SITUACAO_ATUAL"].isin(["Ativo", "Controle"])
        ]
        if manufacturer_vehicles.empty:
            st.info("Nenhum fabricante em tratamento ou controle para exibir.")
        else:
            manufacturers = (
                manufacturer_vehicles.groupby(["FABRI_VEIC", "SITUACAO_ATUAL"])
                .size()
                .reset_index(name="UCs")
                .rename(columns={"FABRI_VEIC": "Fabricante"})
            )
            manufacturers["Situação"] = manufacturers["SITUACAO_ATUAL"].replace(
                {"Ativo": "Tratamento", "Controle": "Controle"}
            )
            fig = px.bar(
                manufacturers,
                x="UCs",
                y="Fabricante",
                color="Situação",
                orientation="h",
                barmode="stack",
                text="UCs",
                color_discrete_map={
                    "Tratamento": "#F5821E",
                    "Controle": "#69727D",
                },
                category_orders={"Situação": ["Tratamento", "Controle"]},
            )
            fig.update_traces(textposition="inside", textangle=0)
            fig.update_layout(
                title="Fabricantes — UCs do Tratamento e Controle",
                yaxis=dict(title="", categoryorder="total ascending"),
                legend=dict(
                    orientation="v",
                    yanchor="top",
                    y=1,
                    xanchor="left",
                    x=1.02,
                ),
            )
            fig = chart_style(fig, 440)
            fig.update_layout(margin=dict(l=20, r=150, t=55, b=20))
            st.plotly_chart(
                fig,
                width="stretch",
                config=PLOTLY_CONFIG,
            )
    with st.container():
        motor_vehicles = vehicles[
            vehicles["SITUACAO_ATUAL"].isin(["Ativo", "Controle"])
        ].copy()
        if motor_vehicles.empty:
            st.info("Nenhuma motorização do Tratamento ou Controle para exibir.")
        else:
            comparison = (
                motor_vehicles.groupby(
                    ["FINALIDADE", "MOTOR_VEIC", "SITUACAO_ATUAL"],
                    dropna=False,
                )
                .size()
                .reset_index(name="UCs")
            )
            comparison["Finalidade"] = comparison["FINALIDADE"].map(clean_label)
            comparison["Motor"] = comparison["MOTOR_VEIC"].map(clean_label)
            comparison["Situação"] = comparison["SITUACAO_ATUAL"].replace(
                {"Ativo": "Tratamento", "Controle": "Controle"}
            )
            fig = px.bar(
                comparison,
                x="Finalidade",
                y="UCs",
                color="Situação",
                pattern_shape="Motor",
                pattern_shape_sequence=["", "/", "x"],
                barmode="group",
                text="UCs",
                color_discrete_map={
                    "Tratamento": "#F5821E",
                    "Controle": "#69727D",
                },
                category_orders={"Situação": ["Tratamento", "Controle"]},
            )
            fig.update_traces(textangle=0, textfont_color="#151C21")
            fig.update_layout(
                title="Motorização por Finalidade",
                legend=dict(
                    orientation="v",
                    yanchor="top",
                    y=1,
                    xanchor="left",
                    x=1.02,
                ),
            )
            fig = chart_style(fig, 440)
            fig.update_layout(margin=dict(l=20, r=180, t=55, b=20))
            st.plotly_chart(
                fig,
                width="stretch",
                config=PLOTLY_CONFIG,
            )

    for motor_value, motor_label in [
        ("Eletrico", "elétricos"),
        ("Hibrido", "híbridos"),
    ]:
        with st.container():
            model_vehicles = vehicles[
                vehicles["SITUACAO_ATUAL"].isin(["Ativo", "Controle"])
                & vehicles["MOTOR_VEIC"].eq(motor_value)
                & vehicles["MODELO_VEIC"].notna()
                & vehicles["MODELO_VEIC"].astype(str).str.strip().ne("")
            ]
            if model_vehicles.empty:
                st.info(f"Nenhum modelo {motor_label} para exibir.")
                continue
            models = (
                model_vehicles.groupby(["MODELO_VEIC", "SITUACAO_ATUAL"])
                .size()
                .reset_index(name="UCs")
                .rename(columns={"MODELO_VEIC": "Modelo"})
            )
            models["Situação"] = models["SITUACAO_ATUAL"].replace(
                {"Ativo": "Tratamento", "Controle": "Controle"}
            )
            model_chart_height = max(480, 110 + 24 * models["Modelo"].nunique())
            fig = px.bar(
                models,
                x="UCs",
                y="Modelo",
                color="Situação",
                orientation="h",
                barmode="stack",
                text="UCs",
                color_discrete_map={
                    "Tratamento": "#F5821E",
                    "Controle": "#69727D",
                },
                category_orders={"Situação": ["Tratamento", "Controle"]},
            )
            fig.update_traces(textposition="inside", textangle=0)
            fig.update_layout(
                title=f"Modelos {motor_label} — UCs do Tratamento e Controle",
                yaxis=dict(title="", categoryorder="total ascending"),
                legend=dict(
                    orientation="v",
                    yanchor="top",
                    y=1,
                    xanchor="left",
                    x=1.02,
                ),
            )
            fig = chart_style(fig, model_chart_height)
            fig.update_layout(margin=dict(l=20, r=150, t=55, b=20))
            st.plotly_chart(
                fig,
                width="stretch",
                config=PLOTLY_CONFIG,
            )


def charging_page(frame: pd.DataFrame) -> None:
    title(
        "Equipamentos",
        "Infraestrutura de recarga",
        "Compare disponibilidade, motorização, marcas, potência e locais de recarga entre Tratamento e Controle.",
    )
    status_labels = {"Ativo": "Tratamento", "Controle": "Controle"}
    status_colors = {"Tratamento": "#F5821E", "Controle": "#69727D"}
    equipment_colors = {"Wallbox": "#F5821E", "Portátil": "#FDB422"}
    population = frame[frame["SITUACAO_ATUAL"].isin(status_labels)].copy()
    if population.empty:
        st.info("Nenhuma UC em tratamento ou controle para comparar.")
        return
    population["Situação"] = population["SITUACAO_ATUAL"].replace(status_labels)

    equipment_fields = [
        ("STATUS_WALLBOX", "Wallbox"),
        ("STATUS_PORTATIL", "Portátil"),
    ]
    status_order = ["Tratamento", "Controle"]

    st.markdown("#### Disponibilidade dos equipamentos")
    availability_columns = st.columns(2)
    availability_labels = {"S": "Sim", "N": "Não"}
    for chart_column, situation in zip(availability_columns, status_order):
        situation_frame = population[population["Situação"].eq(situation)]
        records = []
        for source_column, equipment_label in equipment_fields:
            availability = situation_frame[source_column].map(
                lambda value: availability_labels.get(
                    str(value), "Não informado"
                )
            )
            for label, count in availability.value_counts().items():
                records.append(
                    {
                        "Equipamento": equipment_label,
                        "Disponibilidade": label,
                        "UCs": int(count),
                    }
                )
        wallbox_status = (
            situation_frame["STATUS_WALLBOX"].fillna("").astype(str).str.strip()
        )
        portable_status = (
            situation_frame["STATUS_PORTATIL"].fillna("").astype(str).str.strip()
        )
        has_both = wallbox_status.eq("S") & portable_status.eq("S")
        has_neither = wallbox_status.eq("N") & portable_status.eq("N")
        both_not_informed = (
            ~wallbox_status.isin(["S", "N"])
            & ~portable_status.isin(["S", "N"])
        )
        both_counts = {
            "Sim": int(has_both.sum()),
            "Não": int(has_neither.sum()),
            "Não informado": int(both_not_informed.sum()),
        }
        for label, count in both_counts.items():
            if count == 0:
                continue
            records.append(
                {
                    "Equipamento": "Ambos",
                    "Disponibilidade": label,
                    "UCs": count,
                }
            )
        with chart_column:
            if not records:
                st.info(f"Nenhuma UC em {situation.lower()} para exibir.")
                continue
            availability_data = pd.DataFrame(records)
            fig = px.bar(
                availability_data,
                x="Equipamento",
                y="UCs",
                color="Disponibilidade",
                barmode="group",
                text="UCs",
                color_discrete_map={
                    "Sim": "#F5821E",
                    "Não": "#69727D",
                    "Não informado": "#C8CDD0",
                },
                category_orders={
                    "Disponibilidade": ["Sim", "Não", "Não informado"]
                },
            )
            fig.update_traces(textposition="outside")
            fig.update_layout(title=f"Disponibilidade — {situation}")
            st.plotly_chart(
                chart_style(fig, 420),
                width="stretch",
                config=PLOTLY_CONFIG,
            )

    st.markdown("#### Equipamentos por motorização")
    motor_columns = st.columns(2)
    for chart_column, situation in zip(motor_columns, status_order):
        situation_frame = population[population["Situação"].eq(situation)]
        motor_frame = situation_frame[
            situation_frame["MOTOR_VEIC"].notna()
            & situation_frame["MOTOR_VEIC"].astype(str).str.strip().ne("")
        ]
        records = []
        for motor, group in motor_frame.groupby(
            motor_frame["MOTOR_VEIC"].map(clean_label)
        ):
            for source_column, equipment_label in equipment_fields:
                records.append(
                    {
                        "Motorização": motor,
                        "Equipamento": equipment_label,
                        "UCs com equipamento": int(group[source_column].eq("S").sum()),
                    }
                )
        with chart_column:
            if not records:
                st.info(f"Nenhuma motorização em {situation.lower()} para exibir.")
                continue
            motor_data = pd.DataFrame(records)
            fig = px.bar(
                motor_data,
                x="Motorização",
                y="UCs com equipamento",
                color="Equipamento",
                barmode="group",
                text="UCs com equipamento",
                color_discrete_map=equipment_colors,
            )
            fig.update_traces(textposition="outside")
            fig.update_layout(title=f"Equipamentos por motorização — {situation}")
            st.plotly_chart(
                chart_style(fig, 420),
                width="stretch",
                config=PLOTLY_CONFIG,
            )

    st.markdown("#### Modelos dos Equipamentos")
    brand_columns = st.columns(2)
    brand_fields = [
        ("MARCA_WALLB", "Wallbox"),
        ("MARCA_PORTATIL", "Portátil"),
    ]
    for chart_column, (source_column, equipment_label) in zip(
        brand_columns, brand_fields
    ):
        brand_population = population[
            population[source_column].notna()
            & population[source_column].astype(str).str.strip().ne("")
        ].copy()
        brand_population["Marca"] = (
            brand_population[source_column].astype(str).str.strip().str.upper()
        )
        brands = (
            brand_population.groupby(["Marca", "Situação"])
            .size()
            .reset_index(name="UCs")
        )
        top_brands = (
            brands.groupby("Marca")["UCs"].sum().nlargest(10).index.tolist()
        )
        brands = brands[brands["Marca"].isin(top_brands)]
        with chart_column:
            if brands.empty:
                st.info(f"Nenhum modelo de {equipment_label.lower()} informado.")
                continue
            fig = px.bar(
                brands,
                x="UCs",
                y="Marca",
                color="Situação",
                orientation="h",
                barmode="group",
                text="UCs",
                color_discrete_map=status_colors,
                # Plotly positions the first horizontal grouped trace below the
                # second one, so Controle comes first to keep Tratamento on top.
                category_orders={"Situação": ["Controle", "Tratamento"]},
            )
            fig.update_traces(textposition="outside")
            fig.update_layout(
                title=f"Principais modelos — {equipment_label}",
                yaxis=dict(title="", categoryorder="total ascending"),
                legend=dict(traceorder="reversed"),
            )
            st.plotly_chart(
                chart_style(fig, 500),
                width="stretch",
                config=PLOTLY_CONFIG,
            )
    st.caption("Os gráficos de modelos exibem as dez mais frequentes em cada equipamento.")

    st.markdown("#### Potência declarada dos equipamentos")
    power_order = [
        "menor que 4 kW",
        "entre 4 e 8 kW",
        "entre 8 e 12 kW",
        "entre 12 e 16 kW",
        "maior que 16 kW",
        "Não sei",
    ]
    power_records = []
    for source_column, equipment_label in [
        ("POT_WALLB", "Wallbox"),
        ("POT_PORTATIL", "Portátil"),
    ]:
        available = population[
            population[source_column].notna()
            & population[source_column].astype(str).str.strip().ne("")
        ]
        for (power, situation), group in available.groupby(
            [source_column, "Situação"]
        ):
            power_records.append(
                {
                    "Equipamento": equipment_label,
                    "Potência": str(power).strip(),
                    "Situação": situation,
                    "UCs": int(len(group)),
                }
            )
    if power_records:
        power_data = pd.DataFrame(power_records)
        fig = px.bar(
            power_data,
            x="Potência",
            y="UCs",
            color="Situação",
            facet_col="Equipamento",
            barmode="group",
            text="UCs",
            color_discrete_map=status_colors,
            category_orders={
                "Potência": power_order,
                "Situação": status_order,
                "Equipamento": ["Wallbox", "Portátil"],
            },
        )
        fig.update_traces(textposition="outside")
        fig.for_each_annotation(
            lambda annotation: annotation.update(
                text=annotation.text.replace("Equipamento=", "")
            )
        )
        fig.update_layout(title="Faixas de potência por equipamento")
        st.plotly_chart(
            chart_style(fig, 470),
            width="stretch",
            config=PLOTLY_CONFIG,
        )
    else:
        st.info("Nenhuma potência de equipamento informada.")

    st.markdown("#### Locais de recarga utilizados")
    location_records = []
    for _, row in population[["LOCAL_RECARGA", "Situação"]].dropna().iterrows():
        locations = {
            item.strip()
            for item in str(row["LOCAL_RECARGA"]).split(";")
            if item.strip()
        }
        for location in locations:
            location_records.append(
                {"Local de recarga": location, "Situação": row["Situação"]}
            )
    if location_records:
        locations = (
            pd.DataFrame(location_records)
            .groupby(["Local de recarga", "Situação"])
            .size()
            .reset_index(name="UCs")
        )
        fig = px.bar(
            locations,
            x="UCs",
            y="Local de recarga",
            color="Situação",
            orientation="h",
            barmode="group",
            text="UCs",
            color_discrete_map=status_colors,
            category_orders={"Situação": ["Controle", "Tratamento"]},
        )
        fig.update_traces(textposition="outside")
        fig.update_layout(
            title="Locais declarados por grupo",
            yaxis=dict(title="", categoryorder="total ascending"),
            legend=dict(traceorder="reversed"),
        )
        st.plotly_chart(
            chart_style(fig, 430),
            width="stretch",
            config=PLOTLY_CONFIG,
        )
    else:
        st.info("Nenhum local de recarga informado.")


def gd_page(frame: pd.DataFrame) -> None:
    title(
        "Energia",
        "Geração distribuída",
        "Compare a composição e os vínculos de GD entre Tratamento e Controle.",
    )
    status_labels = {"Ativo": "Tratamento", "Controle": "Controle"}
    population = frame[frame["SITUACAO_ATUAL"].isin(status_labels)].copy()
    if population.empty:
        st.info("Nenhuma UC em tratamento ou controle para comparar.")
        return
    population["Situação"] = population["SITUACAO_ATUAL"].replace(status_labels)
    status_order = ["Tratamento", "Controle"]

    st.markdown("#### Composição por tipo de GD")
    composition_columns = st.columns(2)
    for chart_column, situation in zip(composition_columns, status_order):
        situation_frame = population[population["Situação"].eq(situation)]
        typed_gd = situation_frame[
            situation_frame["TIPO_GD_GERA"].notna()
            & situation_frame["TIPO_GD_GERA"].astype(str).str.strip().ne("")
        ]
        types = count_table(typed_gd, "TIPO_GD_GERA", "Tipo de GD")
        with chart_column:
            if types.empty:
                st.info(f"Nenhum tipo de GD informado em {situation.lower()}.")
                continue
            fig = px.pie(
                types,
                names="Tipo de GD",
                values="UCs",
                hole=.45,
                color="Tipo de GD",
                color_discrete_map={"GDI": "#F5821E", "GDII": "#FDB422"},
                category_orders={"Tipo de GD": ["GDI", "GDII"]},
            )
            fig.update_traces(textinfo="label+value+percent")
            fig.update_layout(title=f"Composição de GD — {situation}")
            st.plotly_chart(
                chart_style(fig, 430),
                width="stretch",
                config=PLOTLY_CONFIG,
            )

    beneficiary = (
        population["GD_BENE_INIC"].notna()
        | population["GD_BENE_FIM"].notna()
        | population["TIPO_GD_BENE"].notna()
    )
    generator = (
        population["DATA_INICIO_GD"].notna()
        | population["DATA_FIM_GD"].notna()
        | population["TIPO_GD_GERA"].notna()
        | population["POSSUI_GD_CLIENTE"].eq("S")
    )
    population["Possui GD beneficiária"] = beneficiary
    population["Possui GD geradora"] = generator

    st.markdown("#### Relação da UC com a GD")
    profile_columns = st.columns(2)
    profile_order = [
        "Somente GD beneficiária",
        "Somente GD geradora",
        "Ambas",
    ]
    profile_colors = {
        "Somente GD beneficiária": "#F5821E",
        "Somente GD geradora": "#69727D",
        "Ambas": "#FDB422",
    }
    for chart_column, situation in zip(profile_columns, status_order):
        situation_frame = population[population["Situação"].eq(situation)]
        has_beneficiary = situation_frame["Possui GD beneficiária"]
        has_generator = situation_frame["Possui GD geradora"]
        profile_data = pd.DataFrame(
            {
                "Perfil": profile_order,
                "UCs": [
                    int((has_beneficiary & ~has_generator).sum()),
                    int((~has_beneficiary & has_generator).sum()),
                    int((has_beneficiary & has_generator).sum()),
                ],
            }
        )
        with chart_column:
            if situation_frame.empty:
                st.info(f"Nenhuma UC em {situation.lower()} para exibir.")
                continue
            fig = px.bar(
                profile_data,
                x="Perfil",
                y="UCs",
                color="Perfil",
                text="UCs",
                color_discrete_map=profile_colors,
                category_orders={"Perfil": profile_order},
            )
            fig.update_traces(textposition="outside", showlegend=False)
            fig.update_layout(title=f"Vínculo com GD — {situation}")
            st.plotly_chart(
                chart_style(fig, 430),
                width="stretch",
                config=PLOTLY_CONFIG,
            )
    st.caption(
        "GD beneficiária considera GD_BENE_INIC, GD_BENE_FIM ou TIPO_GD_BENE. "
        "GD geradora considera DATA_INICIO_GD, DATA_FIM_GD, TIPO_GD_GERA ou "
        "POSSUI_GD_CLIENTE = S."
    )


def update_report_page(frame: pd.DataFrame) -> None:
    title(
        "Monitoramento cadastral",
        "Atualizações e alertas",
        "Última atualização e histórico de alterações para UCs da base consolidada.",
    )
    if (
        not UPDATE_HISTORY_FILE.exists()
        or not UPDATE_ALERT_FILE.exists()
        or not UPDATE_SUMMARY_FILE.exists()
    ):
        st.info(
            "Nenhum histórico foi gerado. Execute `py update_base.py --force` uma "
            "vez para construir o histórico inicial."
        )
        return

    history, latest, summary = load_update_report(
        UPDATE_HISTORY_FILE.stat().st_mtime,
        UPDATE_ALERT_FILE.stat().st_mtime,
        UPDATE_SUMMARY_FILE.stat().st_mtime,
    )

    def normalized_uc(value: object) -> str:
        if pd.isna(value) or str(value).strip() == "":
            return ""
        try:
            return str(int(float(str(value))))
        except ValueError:
            return str(value).strip()

    allowed_ucs = {normalized_uc(value) for value in frame["NUM_UC"]}

    def prepare_alerts(source: pd.DataFrame) -> pd.DataFrame:
        prepared = source.copy()
        prepared["TIPO_ALERTA"] = prepared["TIPO_ALERTA"].replace(
            {
                "Desconexão": "Desligamento",
                "Corte": "Desligamento",
                "Fora do padrão": "Mudança de Classe",
                "Tarifa ativada": "Tarifa Especial Ativada",
            }
        )
        prepared = prepared[
            prepared["NUM_UC"].map(normalized_uc).isin(allowed_ucs)
        ].copy()
        prepared["DATA_ALERTA"] = pd.to_datetime(
            prepared["DATA_ALERTA"], errors="coerce"
        )
        prepared = prepared[prepared["DATA_ALERTA"].notna()].copy()
        prepared["PERIODO"] = prepared["DATA_ALERTA"].map(alert_period_label)
        return prepared

    history = prepare_alerts(history)
    latest = prepare_alerts(latest)

    start = pd.to_datetime(summary.get("periodo_inicio"), format="%Y%m%d", errors="coerce")
    end = pd.to_datetime(summary.get("periodo_fim"), format="%Y%m%d", errors="coerce")
    if pd.notna(start) and pd.notna(end):
        period = (
            f"{start:%d/%m/%Y}"
            if start == end
            else f"{start:%d/%m/%Y} a {end:%d/%m/%Y}"
        )
    else:
        period = "não informado"
    st.caption(
        f"Último relatório: {summary.get('arquivo_origem', 'não informado')} · "
        f"Período do relatório: {period}"
    )

    def render_metrics(alerts: pd.DataFrame) -> None:
        def unique_ucs(alert_type: str) -> int:
            return int(
                alerts.loc[alerts["TIPO_ALERTA"].eq(alert_type), "NUM_UC"].nunique()
            )

        alert_ucs = int(alerts["NUM_UC"].nunique()) if not alerts.empty else 0
        first_metrics = st.columns(4)
        show_metric(
            first_metrics[0],
            "UCs com alertas", f"{alert_ucs:,}".replace(",", ".")
        )
        show_metric(
            first_metrics[1],
            "Sem atualização",
            f"{unique_ucs('Sem atualização'):,}".replace(",", "."),
        )
        show_metric(
            first_metrics[2],
            "Desligamentos", f"{unique_ucs('Desligamento'):,}".replace(",", ".")
        )
        show_metric(
            first_metrics[3],
            "Mudanças de Titularidade",
            f"{unique_ucs('Mudança de Titularidade'):,}".replace(",", "."),
        )
        second_metrics = st.columns(3)
        show_metric(
            second_metrics[0],
            "Mudança de Classe",
            f"{unique_ucs('Mudança de Classe'):,}".replace(",", "."),
        )
        show_metric(
            second_metrics[1],
            "Tarifas Especiais Ativadas",
            f"{unique_ucs('Tarifa Especial Ativada'):,}".replace(",", "."),
        )
        show_metric(
            second_metrics[2],
            "Alterações GD", f"{unique_ucs('Alteração GD'):,}".replace(",", ".")
        )

    def render_alert_content(
        alerts: pd.DataFrame, section_key: str, table_title: str
    ) -> None:
        if alerts.empty:
            st.success("Nenhum alerta foi encontrado para esta seção.")
            return

        alert_types = sorted(alerts["TIPO_ALERTA"].unique().tolist())
        selected_types = st.multiselect(
            "Tipos de alerta",
            alert_types,
            placeholder="Todos os tipos",
            key=f"alert_types_{section_key}",
        )
        view = (
            alerts[alerts["TIPO_ALERTA"].isin(selected_types)].copy()
            if selected_types
            else alerts.copy()
        )

        left, right = st.columns([0.8, 1.4])
        by_group = (
            view.groupby(["GRUPO_UC", "TIPO_ALERTA"])
            .size()
            .reset_index(name="Alertas")
        )
        with left:
            fig = px.bar(
                by_group,
                x="GRUPO_UC",
                y="Alertas",
                color="TIPO_ALERTA",
                barmode="group",
                text="Alertas",
                labels={"GRUPO_UC": "Grupo da UC", "TIPO_ALERTA": "Tipo"},
                category_orders={
                    "GRUPO_UC": ["Tratamento", "Controle", "Reserva"]
                },
                color_discrete_sequence=COLORS,
            )
            fig.update_traces(textposition="outside")
            fig.update_xaxes(title_text=None)
            fig.update_layout(
                title="Alertas por grupo da UC",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.22,
                    xanchor="left",
                    x=0,
                ),
                legend_title_text="Tipo de alerta",
                margin=dict(b=105),
            )
            styled_group_fig = chart_style(fig, 430)
            styled_group_fig.update_layout(
                margin=dict(l=20, r=20, t=55, b=105),
                legend_title_text="Tipo de alerta",
            )
            st.plotly_chart(
                styled_group_fig,
                width="stretch",
                config=PLOTLY_CONFIG,
                key=f"alerts_group_{section_key}",
            )
        with right:
            by_field = view.groupby("CAMPO").size().reset_index(name="Alertas")
            by_field["Alteração"] = by_field["CAMPO"].map(
                lambda field: ALERT_FIELD_LABELS.get(
                    field, str(field).replace("_", " ").capitalize()
                )
            )
            fig = px.pie(
                by_field,
                names="Alteração",
                values="Alertas",
                hole=.42,
                color_discrete_sequence=COLORS,
            )
            fig.update_traces(textinfo="value", textposition="inside")
            fig.update_layout(
                title="Distribuição por campo alterado",
                legend_title_text="Tipo de alteração",
            )
            styled_field_fig = chart_style(fig, 430)
            styled_field_fig.update_layout(legend_title_text="Tipo de alteração")
            st.plotly_chart(
                styled_field_fig,
                width="stretch",
                config=PLOTLY_CONFIG,
                key=f"alerts_field_{section_key}",
            )

        st.markdown(f"#### {table_title}")
        with st.expander("Filtros da tabela", expanded=False):
            filter_row = st.columns(3)
            selected_periods_table = filter_row[0].multiselect(
                "Período",
                sorted(view["PERIODO"].dropna().unique().tolist()),
                placeholder="Todos os períodos",
                key=f"table_periods_{section_key}",
            )
            selected_ucs = filter_row[1].multiselect(
                "UC",
                sorted(view["NUM_UC"].dropna().unique().tolist(), key=normalized_uc),
                placeholder="Todas as UCs",
                key=f"table_ucs_{section_key}",
            )
            selected_groups = filter_row[2].multiselect(
                "Grupo da UC",
                sorted(view["GRUPO_UC"].dropna().unique().tolist()),
                placeholder="Todos os grupos",
                key=f"table_groups_{section_key}",
            )

            category_filter_row = st.columns(2)
            selected_table_types = category_filter_row[0].multiselect(
                "Tipo de alerta",
                sorted(view["TIPO_ALERTA"].dropna().unique().tolist()),
                placeholder="Todos os tipos",
                key=f"table_types_{section_key}",
            )
            selected_fields = category_filter_row[1].multiselect(
                "Campo alterado",
                sorted(view["CAMPO"].dropna().unique().tolist()),
                placeholder="Todos os campos",
                key=f"table_fields_{section_key}",
            )

            minimum_date = view["DATA_ALERTA"].min().date()
            maximum_date = view["DATA_ALERTA"].max().date()
            selected_date_range = st.date_input(
                "Data do alerta",
                value=(minimum_date, maximum_date),
                min_value=minimum_date,
                max_value=maximum_date,
                format="DD/MM/YYYY",
                key=f"table_dates_{section_key}",
            )

        detail_view = view.copy()
        if selected_periods_table:
            detail_view = detail_view[
                detail_view["PERIODO"].isin(selected_periods_table)
            ]
        if selected_ucs:
            detail_view = detail_view[detail_view["NUM_UC"].isin(selected_ucs)]
        if selected_groups:
            detail_view = detail_view[
                detail_view["GRUPO_UC"].isin(selected_groups)
            ]
        if selected_table_types:
            detail_view = detail_view[
                detail_view["TIPO_ALERTA"].isin(selected_table_types)
            ]
        if selected_fields:
            detail_view = detail_view[detail_view["CAMPO"].isin(selected_fields)]
        if len(selected_date_range) == 2:
            start_date, end_date = map(pd.Timestamp, selected_date_range)
            detail_view = detail_view[
                detail_view["DATA_ALERTA"].between(start_date, end_date)
            ]

        detail = detail_view.sort_values(
            ["DATA_ALERTA", "TIPO_ALERTA", "NUM_UC", "CAMPO"],
            ascending=[False, True, True, True],
        )[
            [
                "DATA_ALERTA",
                "PERIODO",
                "NUM_UC",
                "GRUPO_UC",
                "TIPO_ALERTA",
                "CAMPO",
                "VALOR_ANTERIOR",
                "VALOR_NOVO",
                "DETALHE",
            ]
        ].rename(
            columns={
                "DATA_ALERTA": "Data do alerta",
                "PERIODO": "Período",
                "GRUPO_UC": "Grupo da UC",
                "TIPO_ALERTA": "Tipo de alerta",
                "CAMPO": "Campo",
                "VALOR_ANTERIOR": "Valor anterior",
                "VALOR_NOVO": "Valor novo",
                "DETALHE": "Detalhe",
            }
        )
        detail["Data do alerta"] = detail["Data do alerta"].dt.strftime("%d/%m/%Y")
        st.caption(
            f"{len(detail):,} registro(s) exibido(s).".replace(",", ".")
        )
        st.dataframe(detail, width="stretch", hide_index=True, height=420)

    st.markdown("### Última atualização")
    st.caption("Indicadores e alertas gerados exclusivamente pelo relatório mais recente.")
    render_metrics(latest)
    render_alert_content(latest, "latest", "Detalhamento da última atualização")

    st.divider()
    st.markdown("### Histórico acumulado")
    st.caption("Totais e eventos registrados desde 01/03/2026.")
    history_end_candidates = [EXPERIMENT_START_DATE]
    if pd.notna(end):
        history_end_candidates.append(end)
    if not history.empty:
        history_end_candidates.append(history["DATA_ALERTA"].max())
    history_end = max(history_end_candidates)
    month_starts = pd.date_range(
        EXPERIMENT_START_DATE.replace(day=1),
        history_end.replace(day=1),
        freq="MS",
    )
    period_options = ["Inicial"]
    for month_start in month_starts:
        label = alert_period_label(month_start + pd.Timedelta(days=1))
        if label not in period_options:
            period_options.append(label)
    selected_periods = st.pills(
        "Períodos do histórico",
        period_options,
        selection_mode="multi",
        help=(
            "Inicial considera registros até 28/02/2026. Março considera de 01/03 "
            "a 31/03. Os demais meses são completos; seleções múltiplas são combinadas."
        ),
    )
    if selected_periods:
        history = history[history["PERIODO"].isin(selected_periods)].copy()

    render_metrics(history)
    render_alert_content(history, "history", "Histórico detalhado de alertas")


def removed_ucs_page(frame: pd.DataFrame) -> None:
    title(
        "Acompanhamento cadastral",
        "UCs removidas",
        "Analise a origem, os motivos e a evolu\u00e7\u00e3o das remo\u00e7\u00f5es e exporte o recorte filtrado.",
    )

    removed = frame[
        frame["SITUACAO_ATUAL"].eq("Removido") & frame["DT_DISTRATO"].notna()
    ].copy()
    if removed.empty:
        st.warning("Nenhuma UC removida corresponde aos filtros globais selecionados.")
        return

    removed["Grupo de origem"] = (
        removed["SITUACAO_INICIAL"].map(status_display_label).map(clean_label)
    )
    removed["Motivo da remo\u00e7\u00e3o"] = removed["MOTIV_DIST"].map(clean_label)
    removed["Munic\u00edpio"] = removed["LOCAL"].map(clean_label)

    st.markdown("#### Filtros do relat\u00f3rio")
    filter_columns = st.columns(3)
    selected_groups = filter_columns[0].multiselect(
        "Grupo de origem",
        sorted(removed["Grupo de origem"].unique()),
        key="removed_groups",
    )
    selected_reasons = filter_columns[1].multiselect(
        "Motivo da remo\u00e7\u00e3o",
        sorted(removed["Motivo da remo\u00e7\u00e3o"].unique()),
        key="removed_reasons",
    )
    selected_municipalities = filter_columns[2].multiselect(
        "Munic\u00edpio",
        sorted(removed["Munic\u00edpio"].unique()),
        key="removed_municipalities",
    )

    minimum_date = removed["DT_DISTRATO"].min().date()
    maximum_date = removed["DT_DISTRATO"].max().date()
    selected_period = st.date_input(
        "Per\u00edodo da remo\u00e7\u00e3o",
        value=(minimum_date, maximum_date),
        min_value=minimum_date,
        max_value=maximum_date,
        format="DD/MM/YYYY",
        key="removed_period",
    )

    report = removed.copy()
    if selected_groups:
        report = report[report["Grupo de origem"].isin(selected_groups)]
    if selected_reasons:
        report = report[report["Motivo da remo\u00e7\u00e3o"].isin(selected_reasons)]
    if selected_municipalities:
        report = report[report["Munic\u00edpio"].isin(selected_municipalities)]
    if isinstance(selected_period, (tuple, list)) and len(selected_period) == 2:
        start_date, end_date = map(pd.Timestamp, selected_period)
        report = report[report["DT_DISTRATO"].between(start_date, end_date)]

    if report.empty:
        st.warning("Nenhuma remo\u00e7\u00e3o corresponde aos filtros do relat\u00f3rio.")
        return

    total = len(report)
    treatment = int(report["Grupo de origem"].eq("Tratamento").sum())
    control = int(report["Grupo de origem"].eq("Controle").sum())
    other_groups = total - treatment - control
    latest_removal = report["DT_DISTRATO"].max()
    metric_columns = st.columns(4)
    metric_columns[0].metric("UCs removidas", f"{total:,}".replace(",", "."))
    metric_columns[1].metric("Origem: Tratamento", treatment)
    metric_columns[2].metric("Origem: Controle", control)
    metric_columns[3].metric("\u00daltima remo\u00e7\u00e3o", latest_removal.strftime("%d/%m/%Y"))
    if other_groups:
        st.caption(f"{other_groups} UC(s) removida(s) vieram de outros grupos de origem.")

    def render_donut(column: str, title_text: str, color_map: dict[str, str] | None = None) -> None:
        summary = count_table(report, column, column)
        figure = px.pie(
            summary,
            names=column,
            values="UCs",
            hole=0.62,
            color=column,
            color_discrete_map=color_map,
        )
        figure.update_traces(
            textposition="outside",
            texttemplate="%{label}<br><b>%{value}</b> (%{percent})",
            sort=False,
        )
        figure.update_layout(title=title_text, showlegend=False)
        figure.add_annotation(
            text=f"<b>{int(summary['UCs'].sum())}</b><br>UCs",
            showarrow=False,
            font_size=17,
        )
        st.plotly_chart(
            chart_style(figure, 450), width="stretch", config=PLOTLY_CONFIG
        )

    chart_columns = st.columns(2)
    with chart_columns[0]:
        render_donut(
            "Grupo de origem",
            "Remo\u00e7\u00f5es por grupo de origem",
            {
                "Tratamento": "#F5821E",
                "Controle": "#FDB422",
                "Reserva": "#69727D",
            },
        )
    with chart_columns[1]:
        render_donut("Motivo da remo\u00e7\u00e3o", "Remo\u00e7\u00f5es por motivo")

    monthly = (
        report.assign(MONTH=report["DT_DISTRATO"].dt.to_period("M").dt.to_timestamp())
        .groupby("MONTH")
        .size()
        .reset_index(name="UCs")
        .sort_values("MONTH")
    )
    monthly["Per\u00edodo"] = monthly["MONTH"].dt.strftime("%m/%Y")
    monthly_chart = px.bar(
        monthly,
        x="Per\u00edodo",
        y="UCs",
        text="UCs",
        title="Evolu\u00e7\u00e3o mensal das remo\u00e7\u00f5es",
    )
    monthly_chart.update_traces(marker_color="#F5821E", textposition="outside")
    monthly_chart.update_layout(xaxis_title="", yaxis_title="UCs")
    st.plotly_chart(
        chart_style(monthly_chart, 380), width="stretch", config=PLOTLY_CONFIG
    )

    st.markdown("#### Detalhamento para exporta\u00e7\u00e3o")
    # Keep the same schema and column order as base_consolidada_BI.csv.
    detail_columns = [column for column in frame.columns if column in report.columns]
    detail = report[detail_columns].copy().sort_values(
        "DT_DISTRATO", ascending=False
    )
    for column in ["NUM_UC", "NUM_UC_ANEEL"]:
        if column in detail:
            detail[column] = pd.to_numeric(detail[column], errors="coerce").astype(
                "Int64"
            ).astype("string").fillna("")
    for column in detail.select_dtypes(include=["datetime", "datetimetz"]).columns:
        detail[column] = detail[column].dt.strftime("%Y-%m-%d").fillna("")
    detail = detail.rename(
        columns={"IND_SOLICITACAO": "IND_SOLICITA\u00c7AO"}
    )
    st.caption(f"{len(detail)} UC(s) no recorte filtrado.")
    st.dataframe(detail, width="stretch", hide_index=True, height=430)
    st.download_button(
        "Baixar relat\u00f3rio em CSV",
        data=detail.to_csv(index=False, sep=";", encoding="utf-8-sig").encode(
            "utf-8-sig"
        ),
        file_name="relatorio_ucs_removidas.csv",
        mime="text/csv",
        width="stretch",
    )


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
    st.plotly_chart(
        chart_style(fig, 520),
        width="stretch",
        config=PLOTLY_CONFIG,
    )
    st.markdown("#### Consulta operacional (sem dados pessoais)")
    public_columns = [
        "NUM_UC",
        "NUM_UC_ANEEL",
        "SITUACAO_INICIAL",
        "SITUACAO_ATUAL",
        "SITUACAO_UC",
        "LOCAL",
        "CLASSE",
        "GRUPO",
        "TIPO_FASE",
        "ETAPA",
        "DT_ATIVACAO",
        "DT_SITUACAO_UC",
        "DT_MUD_TIT",
        "MUD_TIT",
        "DT_DISTRATO",
        "MOTIV_DIST",
        "IND_SOLICITACAO",
        "FINALIDADE",
        "FABRI_VEIC",
        "MODELO_VEIC",
        "ANO_VEIC",
        "TIPO_VEIC",
        "MOTOR_VEIC",
        "STATUS_VEIC",
        "CAPACIDADE_VEIC",
        "QTE_VEIC",
        "PERCURSO_SEMANAL",
        "FREQ_CARGA_RESIDENCIA",
        "FREQ_CARGA_SEMANAL",
        "FREQ_CARGA_MADRUGADA",
        "LOCAL_RECARGA",
        "ELETROPOSTO_COPEL",
        "STATUS_WALLBOX",
        "MARCA_WALLB",
        "POT_WALLB",
        "STATUS_PORTATIL",
        "MARCA_PORTATIL",
        "POT_PORTATIL",
        "TARIFA_SOCIAL",
        "TARIFA_BRANCA",
        "GD_BENE_INIC",
        "GD_BENE_FIM",
        "TIPO_GD_BENE",
        "DATA_INICIO_GD",
        "DATA_FIM_GD",
        "TIPO_GD_GERA",
        "POSSUI_GD_CLIENTE",
    ]
    view = frame[public_columns].copy()
    view["SITUACAO_INICIAL"] = view["SITUACAO_INICIAL"].map(status_display_label)
    view["SITUACAO_ATUAL"] = view["SITUACAO_ATUAL"].map(status_display_label)
    for column in ["NUM_UC", "NUM_UC_ANEEL"]:
        view[column] = view[column].apply(lambda value: "" if pd.isna(value) else str(int(value)))
    st.dataframe(view, width="stretch", hide_index=True, height=410)


def measurement_scope(frame: pd.DataFrame, measurement: pd.DataFrame) -> pd.DataFrame:
    """Apply the dashboard's UC filters and attach each UC's experiment group."""
    uc_groups = frame[["NUM_UC", "SITUACAO_INICIAL"]].copy()
    uc_groups["uc"] = (
        uc_groups["NUM_UC"]
        .dropna()
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)
    )
    uc_groups["grupo_uc"] = (
        uc_groups["SITUACAO_INICIAL"].map(status_display_label).map(clean_label)
    )
    uc_groups = uc_groups[["uc", "grupo_uc"]].drop_duplicates("uc")

    scoped = measurement.copy()
    scoped["uc"] = scoped["uc"].astype(str)
    if st.session_state.get("global_filters_active", False):
        scoped = scoped[scoped["uc"].isin(set(uc_groups["uc"]))].copy()
    scoped = scoped.merge(uc_groups, on="uc", how="left")
    scoped["grupo_uc"] = scoped["grupo_uc"].replace(
        {"Não informado": "Reserva Extra"}
    ).fillna("Reserva Extra")
    return scoped


def latest_measurement_date_label(report: pd.DataFrame) -> str:
    latest_data_date = report["ultima_leitura"].max()
    if pd.notna(latest_data_date) and latest_data_date == latest_data_date.normalize():
        latest_data_date -= pd.Timedelta(days=1)
    return (
        latest_data_date.strftime("%d/%m/%Y")
        if pd.notna(latest_data_date)
        else "Não disponível"
    )


def communication_delay_label(row: pd.Series) -> str:
    if pd.isna(row["ultima_leitura"]):
        return "Sem medição"
    days = row["dias_sem_comunicacao"]
    if pd.isna(days) or days < 1:
        return "Menos de 1 dia"
    complete_days = int(days)
    return f"{complete_days} dia" if complete_days == 1 else f"{complete_days} dias"


def communication_alerts_page(frame: pd.DataFrame) -> None:
    title(
        "Continuidade dos dados",
        "Alertas de comunicação",
        "",
    )
    if not MEASUREMENT_ALERT_FILE.exists():
        st.error("O arquivo relatorio_alertas_por_uc.csv não foi encontrado.")
        return

    report = measurement_scope(
        frame, load_measurement_alerts(MEASUREMENT_ALERT_FILE.stat().st_mtime)
    )
    alerts = report[report["alerta_sem_comunicacao"].eq("SIM")].copy()
    alerts = alerts.sort_values("atraso_min", ascending=False)

    filter_cols = st.columns(4)
    source_options = sorted(report["origem"].dropna().unique().tolist())
    selected_sources = filter_cols[0].multiselect(
        "Origem", source_options, default=source_options, key="communication_sources"
    )
    timeline = report.copy()
    if selected_sources:
        timeline = timeline[timeline["origem"].isin(selected_sources)]
        alerts = alerts[alerts["origem"].isin(selected_sources)]

    group_order = ["Tratamento", "Controle", "Reserva", "Reserva Extra"]
    group_options = sorted(
        timeline["grupo_uc"].dropna().unique().tolist(),
        key=lambda value: (
            group_order.index(value) if value in group_order else len(group_order),
            value,
        ),
    )
    selected_groups = filter_cols[1].multiselect(
        "Grupo",
        group_options,
        default=[
            group for group in ["Tratamento", "Controle"]
            if group in group_options
        ],
        key="communication_groups",
    )
    if selected_groups:
        timeline = timeline[timeline["grupo_uc"].isin(selected_groups)]
        alerts = alerts[alerts["grupo_uc"].isin(selected_groups)]

    communication_labels = {
        "SIM": "Sem comunicação",
        "NAO": "Com comunicação",
    }
    timeline = timeline.copy()
    alerts = alerts.copy()
    timeline["situacao_comunicacao"] = timeline[
        "alerta_sem_comunicacao"
    ].map(communication_labels).fillna("Não informado")
    alerts["situacao_comunicacao"] = alerts[
        "alerta_sem_comunicacao"
    ].map(communication_labels).fillna("Não informado")
    communication_options = [
        label
        for label in ["Sem comunicação", "Com comunicação", "Não informado"]
        if label in set(timeline["situacao_comunicacao"])
    ]
    selected_communication = filter_cols[2].multiselect(
        "Situação da comunicação",
        communication_options,
        default=[
            status for status in ["Sem comunicação"]
            if status in communication_options
        ],
        key="communication_status",
    )
    if selected_communication:
        timeline = timeline[
            timeline["situacao_comunicacao"].isin(selected_communication)
        ].copy()
        alerts = alerts[
            alerts["situacao_comunicacao"].isin(selected_communication)
        ].copy()

    timeline["faixa_sem_comunicacao"] = timeline.apply(
        communication_delay_label, axis=1
    )
    alerts["faixa_sem_comunicacao"] = alerts.apply(
        communication_delay_label, axis=1
    )

    measured_delays = timeline.loc[
        timeline["ultima_leitura"].notna(), "dias_sem_comunicacao"
    ].dropna()
    max_complete_days = (
        int(measured_delays.max()) if not measured_delays.empty else 0
    )
    delay_options = ["Menos de 1 dia"]
    delay_options.extend(
        f"{days} dia" if days == 1 else f"{days} dias"
        for days in range(1, max_complete_days + 1)
    )
    if timeline["ultima_leitura"].isna().any():
        delay_options.append("Sem medição")
    delay_choices = ["Todos", *delay_options]
    if st.session_state.get("communication_delay_days") not in delay_choices:
        st.session_state["communication_delay_days"] = "Todos"
    selected_delay = filter_cols[3].selectbox(
        "Dias sem comunicação",
        delay_choices,
        index=0,
        key="communication_delay_days",
    )
    if selected_delay == "Menos de 1 dia":
        timeline = timeline[
            timeline["ultima_leitura"].notna()
            & timeline["dias_sem_comunicacao"].lt(1)
        ].copy()
        alerts = alerts[
            alerts["ultima_leitura"].notna()
            & alerts["dias_sem_comunicacao"].lt(1)
        ].copy()
    elif selected_delay == "Sem medição":
        timeline = timeline[timeline["ultima_leitura"].isna()].copy()
        alerts = alerts[alerts["ultima_leitura"].isna()].copy()
    elif selected_delay != "Todos":
        maximum_days = int(selected_delay.split()[0])
        timeline = timeline[
            timeline["ultima_leitura"].notna()
            & timeline["dias_sem_comunicacao"].lt(maximum_days + 1)
        ].copy()
        alerts = alerts[
            alerts["ultima_leitura"].notna()
            & alerts["dias_sem_comunicacao"].lt(maximum_days + 1)
        ].copy()

    filtered_alerts = timeline[
        timeline["alerta_sem_comunicacao"].eq("SIM")
    ]
    cols = st.columns(3)
    show_metric(
        cols[0],
        "UCs monitoradas",
        f"{timeline['uc'].nunique():,}".replace(",", "."),
    )
    show_metric(
        cols[1],
        "Sem comunicação",
        f"{filtered_alerts['uc'].nunique():,}".replace(",", "."),
    )
    show_metric(
        cols[2],
        "\u00daltima data de medi\u00e7\u00e3o dispon\u00edvel",
        latest_measurement_date_label(timeline),
    )
    if filtered_alerts.empty:
        st.success("Nenhuma UC nos filtros selecionados está sem comunicação.")

    timeline["ordem_grupo"] = timeline["grupo_uc"].map(
        {group: index for index, group in enumerate(group_order)}
    ).fillna(len(group_order))
    timeline = timeline.sort_values(
        ["ordem_grupo", "primeira_leitura", "ultima_leitura", "uc"],
        ascending=[True, False, True, True],
        na_position="first",
    ).copy()
    timeline["UC"] = timeline["uc"].map(lambda value: f"UC {value}")
    timeline["Grupo"] = timeline["grupo_uc"]
    timeline["Origem"] = timeline["origem"]
    timeline["Faixa de dias sem comunicação"] = timeline[
        "faixa_sem_comunicacao"
    ]
    st.caption(
        f"{timeline['uc'].nunique():,} UCs exibidas — use a barra de rolagem da "
        "janela para consultar toda a linha do tempo.".replace(",", ".")
    )
    fig = px.timeline(
        timeline,
        x_start="primeira_leitura",
        x_end="ultima_leitura",
        y="UC",
        color="Grupo",
        color_discrete_map={
            "Tratamento": "#F5821E",
            "Controle": "#69727D",
            "Reserva": "#6EBAE8",
            "Reserva Extra": "#A8ADB4",
        },
        category_orders={"Grupo": group_order},
        labels={
            "primeira_leitura": "Primeira leitura",
            "ultima_leitura": "Última leitura",
        },
        custom_data=["uc"],
        title="Período com dados por UC, agrupado pelo grupo experimental",
        hover_data={
            "Origem": True,
            "Faixa de dias sem comunicação": True,
            "primeira_leitura": True,
            "ultima_leitura": True,
            "dias_sem_comunicacao": ":.2f",
            "gaps": ":.0f",
        },
    )
    fig.update_yaxes(
        categoryorder="array",
        categoryarray=timeline["UC"].tolist()[::-1],
    )
    timeline_start = timeline["primeira_leitura"].min()
    timeline_end = timeline["ultima_leitura"].max()
    month_starts = pd.DatetimeIndex([])
    if pd.notna(timeline_start) and pd.notna(timeline_end):
        month_starts = pd.date_range(
            timeline_start.to_period("M").to_timestamp(),
            timeline_end.to_period("M").to_timestamp(),
            freq="MS",
        )
        for month_start in month_starts:
            fig.add_vline(
                x=month_start,
                line_width=2 if month_start.month == 3 else 1,
                line_dash="dash",
                line_color=(
                    "#D62728"
                    if month_start.month == 3
                    else "rgba(63, 68, 75, 0.35)"
                ),
            )
    month_labels = [
        f"{MONTH_NAMES[month.month][:3]}/{month.year}" for month in month_starts
    ]
    fig.update_xaxes(
        tickmode="array",
        tickvals=month_starts,
        ticktext=month_labels,
    )
    fig.update_layout(
        xaxis2=dict(
            anchor="y",
            overlaying="x",
            matches="x",
            side="top",
            tickmode="array",
            tickvals=month_starts,
            ticktext=month_labels,
            showgrid=False,
            title_text=None,
        )
    )
    with st.container(height=720, border=True):
        timeline_selection = st.plotly_chart(
            chart_style(fig, max(600, len(timeline) * 30)),
            width="stretch",
            config=PLOTLY_CONFIG,
            key="communication_timeline",
            on_select="rerun",
            selection_mode="points",
        )
    selected_points = timeline_selection.selection.get("points", [])
    if selected_points:
        selected_uc = str(selected_points[0]["customdata"][0])
        st.markdown("**UC selecionada — clique no ícone para copiar:**")
        st.code(selected_uc, language=None)
    else:
        st.caption(
            "Clique na barra de uma UC para exibir o número em um campo copiável."
        )

    st.markdown("#### Detalhes dos alertas de comunicação")
    view = alerts[
        ["uc", "grupo_uc", "origem", "situacao_comunicacao",
         "faixa_sem_comunicacao", "ultima_leitura", "fim_dados_origem",
         "dias_sem_comunicacao",
         "intervalo_predominante_min", "gaps", "intervalos_ausentes"]
    ].rename(columns={
        "uc": "UC", "grupo_uc": "Grupo", "origem": "Origem",
        "situacao_comunicacao": "Situação da comunicação",
        "faixa_sem_comunicacao": "Faixa de dias sem comunicação",
        "ultima_leitura": "Última leitura",
        "fim_dados_origem": "Fim dos dados da origem",
        "dias_sem_comunicacao": "Dias sem comunicação",
        "intervalo_predominante_min": "Intervalo esperado (min)",
        "gaps": "Lacunas", "intervalos_ausentes": "Intervalos ausentes",
    })
    view["Dias sem comunicação"] = view["Dias sem comunicação"].round(2)
    st.dataframe(view, width="stretch", hide_index=True, height=430)


def measurement_availability_page(frame: pd.DataFrame) -> None:
    title(
        "Continuidade dos dados",
        "Disponibilidade de medição",
        "Disponibilidade mensal e lacunas de dados para cada unidade consumidora.",
    )
    if not MEASUREMENT_ALERT_FILE.exists() or not MEASUREMENT_GAPS_FILE.exists():
        st.error("Os arquivos de alertas e detalhe de gaps não foram encontrados.")
        return

    report = measurement_scope(
        frame, load_measurement_alerts(MEASUREMENT_ALERT_FILE.stat().st_mtime)
    )
    if report.empty:
        empty_state()
        return

    report["availability_overall"] = (
        1
        - report["intervalos_ausentes"]
        / (
            (report["ultima_leitura"] - report["primeira_leitura"]).dt.total_seconds()
            / 60
            / report["intervalo_predominante_min"]
            + 1
        )
    ).clip(0, 1)
    st.markdown("#### Comparativo por UC")
    metric_options = {
        "Disponibilidade geral": ("availability_overall", "Disponibilidade"),
        "Registros recebidos": ("registros", "Registros recebidos"),
        "Intervalos ausentes": ("intervalos_ausentes", "Intervalos ausentes"),
        "Dias/horas sem comunica\u00e7\u00e3o": ("atraso_min", "Horas sem comunica\u00e7\u00e3o"),
    }
    comparison_groups = ["Tratamento", "Controle", "Reserva"]
    comparison_controls = st.columns([1, 1, 2])
    selected_metric_label = comparison_controls[0].selectbox(
        "Indicador do gr\u00e1fico",
        list(metric_options),
        key="availability_comparison_metric",
    )
    selected_source_label = comparison_controls[1].pills(
        "Origem",
        ["Nansen", "Hexing"],
        default=["Nansen", "Hexing"],
        selection_mode="multi",
        key="measurement_availability_source_filter",
    )
    selected_comparison_groups = comparison_controls[2].pills(
        "Grupos exibidos",
        comparison_groups,
        default=["Tratamento", "Controle"],
        selection_mode="multi",
        key="availability_comparison_groups",
    )
    selected_sources = {
        source.upper()
        for source in (selected_source_label or ["Nansen", "Hexing"])
    }
    report = report[
        report["origem"].astype(str).str.upper().isin(selected_sources)
    ].copy()
    if report.empty:
        empty_state()
        return
    metric_column, axis_label = metric_options[selected_metric_label]
    selected_comparison_groups = selected_comparison_groups or comparison_groups
    comparison = report[
        report["grupo_uc"].isin(selected_comparison_groups)
    ].copy()
    comparison["UC"] = comparison["uc"].map(lambda value: f"UC {value}")
    comparison["Grupo"] = comparison["grupo_uc"]
    comparison["Valor"] = pd.to_numeric(
        comparison[metric_column], errors="coerce"
    ).fillna(0)
    if metric_column == "atraso_min":
        comparison["Valor"] = comparison["Valor"] / 60
        comparison["R\u00f3tulo"] = comparison["atraso_min"].map(
            lambda value: (
                "Sem medi\u00e7\u00e3o"
                if pd.isna(value)
                else (
                    f"{value / 1_440:.1f} d"
                    if value >= 1_440
                    else f"{value / 60:.1f} h"
                )
            )
        )
    elif metric_column == "availability_overall":
        comparison["R\u00f3tulo"] = comparison["Valor"].map(
            lambda value: f"{value:.1%}"
        )
    else:
        comparison["R\u00f3tulo"] = comparison["Valor"].round().astype(int).map(
            lambda value: f"{value:,}".replace(",", ".")
        )
    ascending_metric = metric_column in {"availability_overall", "registros"}
    comparison = comparison.sort_values(
        ["Valor", "uc"], ascending=[ascending_metric, True]
    )
    comparison_chart = px.bar(
        comparison,
        x="Valor",
        y="UC",
        orientation="h",
        color="Grupo",
        text="R\u00f3tulo",
        color_discrete_map={
            "Tratamento": "#F5821E",
            "Controle": "#69727D",
            "Reserva": "#6EBAE8",
        },
        category_orders={
            "Grupo": comparison_groups
        },
        labels={"Valor": axis_label},
        hover_data={
            "uc": True,
            "origem": True,
            "R\u00f3tulo": True,
            "Valor": False,
        },
        title=f"{selected_metric_label} por UC",
    )
    comparison_chart.update_yaxes(
        categoryorder="array",
        # Plotly defines category arrays bottom-to-top; reverse it so the
        # dataframe's first (lowest/highest, depending on the metric) is on top.
        categoryarray=comparison["UC"].tolist()[::-1],
        title="",
    )
    comparison_chart.update_traces(textposition="outside", cliponaxis=False)
    if metric_column == "availability_overall":
        comparison_chart.update_xaxes(tickformat=".0%", range=[0, 1.08])
    st.caption(
        f"{comparison['uc'].nunique():,} UCs exibidas; role a janela para consultar todas."
        .replace(",", ".")
    )
    with st.container(height=432, border=True):
        st.plotly_chart(
            chart_style(comparison_chart, max(620, len(comparison) * 29)),
            width="stretch",
            config=PLOTLY_CONFIG,
        )

    st.markdown("#### An\u00e1lise individual")
    uc_options = report.sort_values(
        ["grupo_uc", "availability_overall", "uc"]
    )["uc"].tolist()
    group_by_uc = report.set_index("uc")["grupo_uc"].to_dict()
    selected_uc = st.selectbox(
        "Selecione a UC",
        uc_options,
        format_func=lambda value: f"{group_by_uc[value]} — UC {value}",
    )
    uc_row = report[report["uc"].eq(selected_uc)].iloc[0]

    metrics = st.columns(6)
    show_metric(metrics[0], "Disponibilidade geral", f"{uc_row['availability_overall']:.2%}")
    show_metric(metrics[1], "Grupo", uc_row["grupo_uc"])
    show_metric(metrics[2], "Registros recebidos", f"{int(uc_row['registros']):,}".replace(",", "."))
    show_metric(metrics[3], "Intervalos ausentes", f"{int(uc_row['intervalos_ausentes']):,}".replace(",", "."))
    show_metric(metrics[4], "Intervalo esperado", f"{int(uc_row['intervalo_predominante_min'])} min")
    show_metric(
        metrics[5],
        "Dados disponíveis até", latest_measurement_date_label(report)
    )

    timeline_segments = []
    first_reading = uc_row["primeira_leitura"]
    last_reading = uc_row["ultima_leitura"]
    source_end = uc_row["fim_dados_origem"]
    if pd.notna(first_reading) and pd.notna(last_reading):
        timeline_segments.append(
            {
                "UC": f"UC {selected_uc}",
                "In\u00edcio": first_reading,
                "Fim": last_reading,
                "Situa\u00e7\u00e3o": "Dados recebidos",
            }
        )
        if pd.notna(source_end) and source_end > last_reading:
            timeline_segments.append(
                {
                    "UC": f"UC {selected_uc}",
                    "In\u00edcio": last_reading,
                    "Fim": source_end,
                    "Situa\u00e7\u00e3o": "Sem comunica\u00e7\u00e3o",
                }
            )
    if timeline_segments:
        selected_timeline = pd.DataFrame(timeline_segments)
        timeline_chart = px.timeline(
            selected_timeline,
            x_start="In\u00edcio",
            x_end="Fim",
            y="UC",
            color="Situa\u00e7\u00e3o",
            color_discrete_map={
                "Dados recebidos": "#F5821E",
                "Sem comunica\u00e7\u00e3o": "#A83D2D",
            },
            title=f"Linha do tempo de comunica\u00e7\u00e3o da UC {selected_uc}",
        )
        timeline_chart.update_yaxes(title="")
        timeline_end = selected_timeline["Fim"].max()
        january_start = pd.Timestamp(year=first_reading.year, month=1, day=1)
        month_starts = pd.date_range(
            january_start,
            timeline_end.to_period("M").to_timestamp(),
            freq="MS",
        )
        for month_start in month_starts:
            timeline_chart.add_vline(
                x=month_start,
                line_width=2 if month_start.month == 3 else 1,
                line_dash="dash",
                line_color=(
                    "#D62728"
                    if month_start.month == 3
                    else "rgba(63, 68, 75, 0.35)"
                ),
            )
        month_labels = [
            f"{MONTH_NAMES[month.month][:3]}/{month.year}"
            for month in month_starts
        ]
        timeline_chart.update_xaxes(
            title="",
            tickmode="array",
            tickvals=month_starts,
            ticktext=month_labels,
        )
        timeline_chart.update_layout(
            xaxis2=dict(
                anchor="y",
                overlaying="x",
                matches="x",
                side="top",
                tickmode="array",
                tickvals=month_starts,
                ticktext=month_labels,
                showgrid=False,
                title_text=None,
            )
        )
        st.plotly_chart(
            chart_style(timeline_chart, 280),
            width="stretch",
            config=PLOTLY_CONFIG,
        )
    else:
        st.info(
            f"A UC {selected_uc} n\u00e3o possui medi\u00e7\u00f5es para exibir na linha do tempo."
        )

    gaps = load_measurement_gaps(MEASUREMENT_GAPS_FILE.stat().st_mtime)
    gaps = gaps[
        gaps["origem"].astype(str).str.upper().isin(selected_sources)
        & gaps["uc"].eq(selected_uc)
    ].copy()
    gaps["mes"] = gaps["inicio_gap"].dt.to_period("M").dt.to_timestamp()
    missing = gaps.groupby("mes", as_index=False)["intervalos_ausentes"].sum()

    start = uc_row["primeira_leitura"].to_period("M").to_timestamp()
    end = uc_row["ultima_leitura"].to_period("M").to_timestamp()
    monthly = pd.DataFrame({"mes": pd.date_range(start, end, freq="MS")})
    monthly = monthly.merge(missing, on="mes", how="left").fillna({"intervalos_ausentes": 0})
    month_end = monthly["mes"] + pd.offsets.MonthEnd(1) + pd.Timedelta(days=1)
    observed_start = monthly["mes"].clip(lower=uc_row["primeira_leitura"])
    observed_end = month_end.clip(upper=uc_row["ultima_leitura"] + pd.Timedelta(minutes=float(uc_row["intervalo_predominante_min"])))
    monthly["intervalos_esperados"] = (
        (observed_end - observed_start).dt.total_seconds()
        / 60
        / float(uc_row["intervalo_predominante_min"])
    ).clip(lower=1)
    monthly["disponibilidade"] = (
        1 - monthly["intervalos_ausentes"] / monthly["intervalos_esperados"]
    ).clip(0, 1)

    fig = px.bar(
        monthly,
        x="mes",
        y="disponibilidade",
        text=monthly["disponibilidade"].map(lambda value: f"{value:.1%}"),
        labels={"mes": "Mês", "disponibilidade": "Disponibilidade"},
        title=f"Disponibilidade mensal — UC {selected_uc}",
    )
    fig.update_yaxes(tickformat=".0%", range=[0, 1.08])
    fig.update_traces(marker_color="#F5821E", textposition="outside")
    st.plotly_chart(chart_style(fig, 430), width="stretch", config=PLOTLY_CONFIG)

    st.markdown("#### Maiores lacunas")
    gap_view = gaps.nlargest(100, "intervalos_ausentes")[
        ["inicio_gap", "fim_gap", "duracao_min", "intervalos_ausentes"]
    ].rename(columns={
        "inicio_gap": "Início", "fim_gap": "Fim", "duracao_min": "Duração (min)",
        "intervalos_ausentes": "Intervalos ausentes",
    })
    st.dataframe(gap_view, width="stretch", hide_index=True, height=360)


inject_css()
render_brand_banner()
if not st.session_state.get("authenticated", False):
    login_screen()
    st.stop()

render_data_disclaimer()

if not DATA_FILE.exists():
    st.error(f"Arquivo de dados não encontrado: {DATA_FILE.name}")
    st.stop()

data = load_data(DATA_FILE.stat().st_mtime)
filtered_data, selected_page, gd_reference_date = sidebar_filters(data)

if filtered_data.empty:
    title("Filtros", selected_page, "A combinação atual não retornou registros.")
    empty_state()
elif selected_page == "Geral":
    executive_page(filtered_data, gd_reference_date)
elif selected_page == "UCs removidas":
    removed_ucs_page(filtered_data)
elif selected_page == "UCs e localização":
    uc_page(filtered_data)
elif selected_page == "Perfil dos veículos":
    vehicle_page(filtered_data)
elif selected_page == "Infraestrutura de recarga":
    charging_page(filtered_data)
elif selected_page == "Geração distribuída":
    gd_page(filtered_data)
elif selected_page == "Atualizações e alertas":
    update_report_page(filtered_data)
elif selected_page == "Alertas de comunicação":
    communication_alerts_page(filtered_data)
elif selected_page == "Disponibilidade de medição":
    measurement_availability_page(filtered_data)

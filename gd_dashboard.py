"""Streamlit views for the generated, privacy-filtered Cadastro/GD datasets."""
from pathlib import Path
import json

import pandas as pd
import plotly.express as px
import streamlit as st

DATA = Path(__file__).with_name("data")


@st.cache_data
def load_gd(mtimes):
    del mtimes
    files = ("gd_atual", "gd_snapshots", "gd_vinculos", "gd_historico_2026", "gd_qualidade", "gd_auditoria_baseline")
    frames = {name: pd.read_csv(DATA / f"{name}.csv", dtype=str, keep_default_na=False, encoding="utf-8-sig") for name in files}
    manifest = json.loads((DATA / "gd_manifesto.json").read_text(encoding="utf-8"))
    return frames, manifest


def download(frame, name, key):
    st.download_button("Baixar CSV", frame.to_csv(index=False, sep=";").encode("utf-8-sig"),
                       name, "text/csv", key=key)


def history_view(history, key="gd"):
    if history.empty:
        st.info("Nenhum evento de GD no recorte selecionado.")
        return
    view = history.copy()
    controls = st.columns(3)
    period = controls[0].selectbox("Período", ["Todo o ano de 2026", "Experimento: desde 01/03/2026"], key=f"{key}_period")
    if period.startswith("Experimento"):
        view = view[view["DATA_ALERTA"].ge("2026-03-01")]
    field = controls[1].multiselect("Alteração", sorted(history["CAMPO"].unique()), key=f"{key}_field")
    basis = controls[2].multiselect("Base da data", sorted(history["BASE_DATA"].unique()), key=f"{key}_basis")
    if field:
        view = view[view["CAMPO"].isin(field)]
    if basis:
        view = view[view["BASE_DATA"].isin(basis)]
    controls2 = st.columns(3)
    nature = controls2[0].multiselect("Natureza do registro", sorted(history["NATUREZA"].unique()), key=f"{key}_nature")
    source_dates = controls2[1].multiselect("Data de observação", sorted(history["OBSERVACAO_ATUAL"].unique()), key=f"{key}_source_dates")
    review = controls2[2].checkbox("Somente registros para revisão", key=f"{key}_review")
    if nature:
        view = view[view["NATUREZA"].isin(nature)]
    if source_dates:
        view = view[view["OBSERVACAO_ATUAL"].isin(source_dates)]
    if review:
        view = view[~view["STATUS_QUALIDADE"].isin(["", "OK"])]
    st.caption("Data cadastrada segue os campos definidos para GD. Primeira observação indica o limite da detecção; consulte a observação anterior. Reconstruções anteriores ao primeiro export estão identificadas.")
    columns = ["DATA_ALERTA", "NUM_UC", "CAMPO", "VALOR_ANTERIOR", "VALOR_NOVO", "BASE_DATA", "DATA_EFETIVA", "OBSERVACAO_ANTERIOR", "OBSERVACAO_ATUAL", "NATUREZA", "STATUS_QUALIDADE", "UC_RELACIONADA", "DETALHE", "ARQUIVO_ANTERIOR", "ARQUIVO_ORIGEM"]
    view = view.sort_values(["DATA_ALERTA", "NUM_UC"], ascending=[False, True])
    st.dataframe(view[columns], width="stretch", hide_index=True)
    download(view, "gd_historico_2026.csv", f"{key}_download")


def render(frame, reference_date, chart_style, plotly_config):
    if not (DATA / "gd_manifesto.json").exists():
        return False
    names = ("gd_atual.csv", "gd_snapshots.csv", "gd_vinculos.csv", "gd_historico_2026.csv", "gd_qualidade.csv", "gd_auditoria_baseline.csv", "gd_manifesto.json")
    frames, manifest = load_gd(tuple((DATA / name).stat().st_mtime_ns for name in names))
    scope = set(frame["NUM_UC"].astype(str))
    st.caption(f"GD/BEN/UC: {manifest['data_gd']} · MDM: {manifest['periodo_fim']} · Potência em kW · População: UCs da base BI")
    if manifest.get("lote_gd_incompleto"):
        st.warning(f"O lote de {manifest['data_ultimo_arquivo_gd']} está incompleto. A posição atual usa o último lote completo, de {manifest['data_gd']}.")
    mode = st.radio("Posição de GD", ["Último export completo", "Data de referência da barra lateral"], horizontal=True)
    current = frames["gd_atual"]
    if mode.startswith("Data"):
        snapshots = frames["gd_snapshots"]
        eligible = snapshots[snapshots["DATA_REFERENCIA"].le(pd.Timestamp(reference_date).strftime("%Y-%m-%d"))]
        if eligible.empty:
            st.info("A referência é anterior à baseline de 31/12/2025.")
            return True
        snapshot_date = eligible["DATA_REFERENCIA"].max()
        current = eligible[eligible["DATA_REFERENCIA"].eq(snapshot_date)]
        st.caption(f"Última posição disponível até a referência: {snapshot_date}. {manifest['baseline_limite']}")
    current = current[current["NUM_UC"].isin(scope)].copy()
    history = frames["gd_historico_2026"]
    history = history[history["NUM_UC"].isin(scope)]
    cards = st.columns(4)
    cards[0].metric("UCs geradoras", int(current["GD_GERADORA"].eq("S").sum()))
    cards[1].metric("UCs beneficiárias", int(current["GD_BENEFICIARIA"].eq("S").sum()))
    installed = pd.to_numeric(current["POTENCIA_INSTALADA_KW"], errors="coerce").sum()
    cards[2].metric("Potência própria (kW)", f"{installed:,.2f}", help="Uma potência por UC geradora; conflitos usam o maior valor e recebem flag de revisão. Valores desconhecidos não entram no total.")
    cards[3].metric("UCs para revisão", int(current["REVISAO_MANUAL"].eq("S").sum()))
    entries = history[history["CAMPO"].isin(["GD_GERADORA", "GD_BENEFICIARIA"]) & history["VALOR_NOVO"].eq("S")]
    dated = entries[entries["BASE_DATA"].isin(["Data cadastrada", "Reconstrução por data cadastrada"])]
    extra = st.columns(3)
    extra[0].metric("UCs com entrada GD datada em 2026", dated["NUM_UC"].nunique(), help="Data de solicitação para geradoras; data de inclusão para beneficiárias, conforme regra acordada. Não certifica comissionamento.")
    extra[1].metric("UCs com entrada GD por observação", entries[~entries.index.isin(dated.index)]["NUM_UC"].nunique())
    extra[2].metric("Mudanças de potência em 2026", int(history["CAMPO"].eq("POTENCIA_INSTALADA_KW").sum()))
    tabs = st.tabs(["Posição e potência", "Histórico 2026", "Consulta por UC", "Qualidade e baseline"])
    with tabs[0]:
        groups = frame[["NUM_UC", "SITUACAO_ATUAL"]].copy()
        groups["NUM_UC"] = groups["NUM_UC"].astype(str)
        display = current.merge(groups, on="NUM_UC", how="left")
        display["Grupo"] = display["SITUACAO_ATUAL"].replace({"Ativo": "Tratamento"})
        chart = display.groupby(["Grupo", "PERFIL_GD"]).size().reset_index(name="UCs")
        fig = px.bar(chart, x="Grupo", y="UCs", color="PERFIL_GD", barmode="group", text="UCs", labels={"PERFIL_GD": "Perfil GD"}, color_discrete_sequence=["#F5821E", "#FDB422", "#69727D", "#3F444B"])
        st.plotly_chart(chart_style(fig, 400), width="stretch", config=plotly_config)
        powers = pd.DataFrame({"Classificação": ["GDI", "GDII", "Outros", "Sem classificação"],
            "kW": [pd.to_numeric(current[c], errors="coerce").sum() for c in ["POTENCIA_GDI_KW", "POTENCIA_GDII_KW", "POTENCIA_OUTROS_KW", "POTENCIA_SEM_CLASSIFICACAO_KW"]]})
        fig = px.bar(powers, x="Classificação", y="kW", text_auto=".2f", color="Classificação", color_discrete_sequence=["#F5821E", "#FDB422", "#69727D", "#3F444B"])
        st.plotly_chart(chart_style(fig, 350), width="stretch", config=plotly_config)
        st.caption("GDI/GDII usa PCT_DIS_KCD. PCT_RAT_XBG representa rateio de créditos. Potência externa associada é contexto cadastral e não deve ser somada entre beneficiárias; não representa energia em kWh.")
        review_only = st.checkbox("Mostrar somente UCs para revisão", key="gd_current_review")
        table = display[display["REVISAO_MANUAL"].eq("S")] if review_only else display
        st.dataframe(table, width="stretch", hide_index=True)
        download(table, "gd_atual.csv", "gd_current_download")
    with tabs[1]:
        history_view(history)
    with tabs[2]:
        selected = st.selectbox("UC", sorted(scope), index=None, placeholder="Pesquisar UC")
        if selected:
            st.dataframe(current[current["NUM_UC"].eq(selected)], width="stretch", hide_index=True)
            relationships = frames["gd_vinculos"]
            relationships = relationships[relationships["UC_GERADORA"].eq(selected) | relationships["UC_BENEFICIARIA"].eq(selected)]
            st.caption("Vínculos presentes no último export completo, incluindo UCs relacionadas externas ao BI. Autorrelacionamentos são exibidos somente quando constam na fonte.")
            st.dataframe(relationships, width="stretch", hide_index=True)
            download(relationships, f"gd_vinculos_{selected}.csv", "gd_links_download")
            history_view(history[history["NUM_UC"].eq(selected)], "gd_uc")
    with tabs[3]:
        st.caption(f"Baseline: {manifest['arquivo_baseline']} · Referência: 31/12/2025. Correções de baseline não são novas entradas GD em 2026.")
        audit = frames["gd_auditoria_baseline"]
        audit = audit[audit["NUM_UC"].isin(scope)]
        st.dataframe(audit, width="stretch", hide_index=True)
        download(audit, "gd_auditoria_baseline.csv", "gd_audit_download")
        quality = frames["gd_qualidade"]
        quality = quality[quality["NUM_UC"].isin(scope | {""})]
        st.dataframe(quality, width="stretch", hide_index=True)
        download(quality, "gd_qualidade.csv", "gd_quality_download")
    return True

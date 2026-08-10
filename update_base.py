from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Callable

import pandas as pd


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
BASE_FILE = ROOT / "base_consolidada_BI.csv"
ALERT_FILE = DATA_DIR / "ultima_atualizacao_alertas.csv"
HISTORY_FILE = DATA_DIR / "historico_alertas.csv"
SUMMARY_FILE = DATA_DIR / "ultima_atualizacao_resumo.json"
REPORT_PATTERN = re.compile(
    r"^mdm-sandbox_clientes_novo-(\d{8})-(\d{8})\.csv$",
    re.IGNORECASE,
)
MOBIFLEX_REPORT_PATTERN = re.compile(
    r"^Relat.rio_Cadastral_Mobiflex_(\d{2})-(\d{2})-(\d{2})\.csv$",
    re.IGNORECASE,
)
MOBIFLEX_TARGET_COLUMNS = [
    "SITUACAO_ATUAL",
    "DT_DISTRATO",
    "MOTIV_DIST",
    "IND_SOLICITA\u00c7AO",
]
TITLE_CHANGE_START_DATE = pd.Timestamp("2026-03-01")
TRACKING_COLUMNS = ["DT_SITUACAO_UC", "DT_MUD_TIT", "MUD_TIT"]
PERSONAL_REPORT_COLUMNS = {"cliente", "nome", "celular", "email", "medidor"}

ALERT_COLUMNS = [
    "DATA_ALERTA",
    "NUM_UC",
    "GRUPO_UC",
    "TIPO_ALERTA",
    "CAMPO",
    "VALOR_ANTERIOR",
    "VALOR_NOVO",
    "DETALHE",
    "ARQUIVO_ORIGEM",
]
MONITORED_COLUMNS = [
    "SITUACAO_UC",
    "CLASSE",
    "GRUPO",
    "GD_BENE_INIC",
    "GD_BENE_FIM",
    "TIPO_GD_BENE",
    "DATA_INICIO_GD",
    "DATA_FIM_GD",
    "TIPO_GD_GERA",
    "TARIFA_SOCIAL",
    "TARIFA_BRANCA",
]


def text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    result = str(value).strip()
    return "" if result.lower() in {"nan", "none", "<na>"} else result


def upper(value: object) -> str:
    return text(value).upper()


def identifier(value: object) -> str:
    result = text(value)
    if not result:
        return ""
    if re.fullmatch(r"\d+(?:\.0+)?", result):
        return str(int(float(result)))
    return result


def integer(value: object) -> str:
    result = text(value)
    if not result:
        return ""
    try:
        return str(int(float(result.replace(",", "."))))
    except ValueError:
        return result


def iso_date(value: object) -> str:
    result = text(value)
    if not result:
        return ""
    parsed = pd.to_datetime(result, errors="coerce", dayfirst="/" in result)
    if pd.isna(parsed):
        raise ValueError(f"Data inválida no relatório: {result!r}")
    return parsed.strftime("%Y-%m-%d")


def yes_no(value: object) -> str:
    normalized = upper(value)
    if normalized in {"S", "SIM", "GERADORA", "TRUE", "1"}:
        return "S"
    if normalized in {"N", "NAO", "NÃO", "FALSE", "0", ""}:
        return "N"
    return normalized


def social_tariff(value: object) -> str:
    normalized = upper(value)
    return "N" if normalized in {"", "N", "NAO", "NÃO", "0"} else "S"


def group_label(value: object) -> str:
    normalized = upper(value)
    return {
        "ATIVO": "Tratamento",
        "ATIVOS": "Tratamento",
        "ATIVA": "Tratamento",
        "ATIVAS": "Tratamento",
        "CONTROLE": "Controle",
        "RESERVA": "Reserva",
    }.get(normalized, text(value) or "Não informado")


Normalizer = Callable[[object], str]

# Only fields with a direct, reliable correspondence are updated. Project fields
# such as ETAPA, DT_ATIVACAO and FINALIDADE remain under the consolidated base's
# existing governance.
FIELD_MAP: dict[str, tuple[str, Normalizer]] = {
    "uc_aneel": ("NUM_UC_ANEEL", identifier),
    "sub_grupo": ("CLASSE", upper),
    "classe_principal": ("GRUPO", integer),
    "situacao_uc": ("SITUACAO_UC", upper),
    "tipo_fase": ("TIPO_FASE", upper),
    "municipio": ("LOCAL", upper),
    "data_situacao": ("DT_SITUACAO_UC", iso_date),
    "max_data_tt": ("DT_MUD_TIT", iso_date),
    "inicio_beneficiaria": ("GD_BENE_INIC", iso_date),
    "fim_benificiaria": ("GD_BENE_FIM", iso_date),
    # TIPO_GD_BENE is not modalidade_geracao. This optional source column will
    # only be used once it is delivered explicitly in a future report.
    "tipo_gd_bene": ("TIPO_GD_BENE", upper),
    "data_inicio_gd": ("DATA_INICIO_GD", iso_date),
    "data_fim_gd": ("DATA_FIM_GD", iso_date),
    "tipo_gd": ("TIPO_GD_GERA", upper),
    "geracao_propria": ("POSSUI_GD_CLIENTE", yes_no),
    "tarifa_branca": ("TARIFA_BRANCA", yes_no),
    "baixa_renda": ("TARIFA_SOCIAL", social_tariff),
}
OPTIONAL_SOURCE_COLUMNS = {"tipo_gd_bene"}
TARGET_NORMALIZERS: dict[str, Normalizer] = {
    target: (
        upper
        if target in {"POSSUI_GD_CLIENTE", "TARIFA_SOCIAL", "TARIFA_BRANCA"}
        else normalizer
    )
    for target, normalizer in FIELD_MAP.values()
}
TARGET_NORMALIZERS["MUD_TIT"] = upper


def newest_report() -> Path:
    candidates: list[tuple[str, str, Path]] = []
    for path in DATA_DIR.glob("mdm-sandbox_clientes_novo-*.csv"):
        match = REPORT_PATTERN.fullmatch(path.name)
        if match:
            datetime.strptime(match.group(1), "%Y%m%d")
            datetime.strptime(match.group(2), "%Y%m%d")
            candidates.append((match.group(2), match.group(1), path))
    if not candidates:
        raise FileNotFoundError(
            "Nenhum relatório data/mdm-sandbox_clientes_novo-YYYYMMDD-YYYYMMDD.csv encontrado."
        )
    return max(candidates)[2]


def newest_mobiflex_report() -> Path:
    candidates: list[tuple[datetime, Path]] = []
    for path in DATA_DIR.glob("*Mobiflex*.csv"):
        match = MOBIFLEX_REPORT_PATTERN.fullmatch(path.name)
        if match:
            report_date = datetime.strptime("-".join(match.groups()), "%y-%m-%d")
            candidates.append((report_date, path))
    if not candidates:
        raise FileNotFoundError(
            "Nenhum relat\u00f3rio data/Relat\u00f3rio_Cadastral_Mobiflex_YY-MM-DD.csv "
            "encontrado."
        )
    return max(candidates, key=lambda item: item[0])[1]


def read_summary() -> dict:
    if not SUMMARY_FILE.exists():
        return {}
    return json.loads(SUMMARY_FILE.read_text(encoding="utf-8"))


def validate_columns(frame: pd.DataFrame, required: set[str], label: str) -> None:
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Colunas ausentes em {label}: {', '.join(missing)}")


def update_from_mobiflex(
    base: pd.DataFrame,
    base_index: dict[str, int],
    report: Path,
    changed_ucs: set[str],
) -> dict[str, int]:
    incoming = pd.read_csv(
        report,
        sep=";",
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )
    incoming.columns = [text(column) for column in incoming.columns]
    validate_columns(incoming, {"UC", "DATA", "Motivo"}, report.name)

    incoming["UC"] = incoming["UC"].map(identifier)
    if incoming["UC"].eq("").any():
        raise ValueError(f"Existem UCs sem identificador em {report.name}.")

    # If a UC has multiple removal events, its most recent dated row wins.
    incoming["_DT_DISTRATO"] = incoming["DATA"].map(iso_date)
    incoming = incoming.sort_values("_DT_DISTRATO", kind="stable").drop_duplicates(
        subset="UC", keep="last"
    )

    matched_ucs = 0
    extra_ucs = 0
    for _, source_row in incoming.iterrows():
        uc = source_row["UC"]
        if uc not in base_index:
            extra_ucs += 1
            continue

        matched_ucs += 1
        index = base_index[uc]
        updates = {
            "SITUACAO_ATUAL": "Removido",
            "DT_DISTRATO": source_row["_DT_DISTRATO"],
            "MOTIV_DIST": text(source_row["Motivo"]),
            # Only UCs explicitly present in Mobiflex receive this value.
            "IND_SOLICITA\u00c7AO": "N",
        }
        for column, new_value in updates.items():
            if text(base.at[index, column]) != new_value:
                base.at[index, column] = new_value
                changed_ucs.add(uc)

    return {
        "linhas": int(len(incoming)),
        "ucs_correspondentes": matched_ucs,
        "ucs_extras_ignoradas": extra_ucs,
    }


def atomic_csv(frame: pd.DataFrame, destination: Path, sep: str = ",") -> None:
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    frame.to_csv(
        temporary,
        index=False,
        sep=sep,
        encoding="utf-8-sig",
        lineterminator="\n",
    )
    temporary.replace(destination)


def atomic_json(payload: dict, destination: Path) -> None:
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)


def report_end_date(report: Path) -> str:
    match = REPORT_PATTERN.fullmatch(report.name)
    if not match:
        raise ValueError(f"Nome de relatório inválido: {report.name}")
    return datetime.strptime(match.group(2), "%Y%m%d").strftime("%Y-%m-%d")


def add_alert(
    alerts: list[dict[str, str]],
    uc: str,
    group: str,
    alert_type: str,
    field: str,
    previous: str,
    new: str,
    detail: str,
    source: str,
    alert_date: str = "",
) -> None:
    alerts.append(
        {
            "DATA_ALERTA": alert_date,
            "NUM_UC": uc,
            "GRUPO_UC": group,
            "TIPO_ALERTA": alert_type,
            "CAMPO": field,
            "VALOR_ANTERIOR": previous,
            "VALOR_NOVO": new,
            "DETALHE": detail,
            "ARQUIVO_ORIGEM": source,
        }
    )


def alert_date_for_change(
    field: str, new: str, converted: dict[str, str], fallback_date: str
) -> str:
    if field == "SITUACAO_UC":
        return converted.get("DT_SITUACAO_UC") or fallback_date
    if field in {"GD_BENE_INIC", "GD_BENE_FIM", "DATA_INICIO_GD", "DATA_FIM_GD"}:
        return new or fallback_date
    return fallback_date


def dated_history_from_base(base: pd.DataFrame, source: str) -> pd.DataFrame:
    events: list[dict[str, str]] = []
    for _, row in base.iterrows():
        uc = identifier(row["NUM_UC"])
        group = group_label(row["SITUACAO_INICIAL"])

        title_date = iso_date(row.get("DT_MUD_TIT", ""))
        if title_date and pd.Timestamp(title_date) >= TITLE_CHANGE_START_DATE:
            add_alert(
                events,
                uc,
                group,
                "Mudança de Titularidade",
                "MUD_TIT",
                "",
                title_date,
                "Mudança de titularidade registrada desde o início do experimento.",
                source,
                title_date,
            )

        situation_date = iso_date(row.get("DT_SITUACAO_UC", ""))
        situation = upper(row.get("SITUACAO_UC", ""))
        if (
            situation in {"DS", "CR"}
            and situation_date
            and pd.Timestamp(situation_date) >= TITLE_CHANGE_START_DATE
        ):
            detail = (
                "Desligamento registrado desde o início do experimento."
                if situation == "DS"
                else "Corte registrado desde o início do experimento."
            )
            add_alert(
                events,
                uc,
                group,
                "Desligamento",
                "SITUACAO_UC",
                "",
                situation,
                detail,
                source,
                situation_date,
            )

        for field in ("GD_BENE_INIC", "GD_BENE_FIM", "DATA_INICIO_GD", "DATA_FIM_GD"):
            event_date = iso_date(row.get(field, ""))
            if event_date and pd.Timestamp(event_date) >= TITLE_CHANGE_START_DATE:
                add_alert(
                    events,
                    uc,
                    group,
                    "Alteração GD",
                    field,
                    "",
                    event_date,
                    "Evento de GD datado desde o início do experimento.",
                    source,
                    event_date,
                )
    return pd.DataFrame(events, columns=ALERT_COLUMNS)


def update_alert_history(base: pd.DataFrame, latest: pd.DataFrame, report: Path) -> int:
    latest = latest.copy()
    latest["TIPO_ALERTA"] = latest["TIPO_ALERTA"].replace(
        {"Corte": "Desligamento"}
    )
    frames = [dated_history_from_base(base, report.name), latest]
    if HISTORY_FILE.exists():
        existing = pd.read_csv(
            HISTORY_FILE,
            dtype=str,
            keep_default_na=False,
            encoding="utf-8-sig",
        )
        for column in ALERT_COLUMNS:
            if column not in existing.columns:
                existing[column] = ""
        existing["TIPO_ALERTA"] = existing["TIPO_ALERTA"].replace(
            {"Corte": "Desligamento"}
        )
        frames.insert(0, existing[ALERT_COLUMNS])

    history = pd.concat(frames, ignore_index=True)
    history["DATA_ALERTA"] = history["DATA_ALERTA"].map(iso_date)
    history = history[
        history["DATA_ALERTA"].ne("")
        & pd.to_datetime(history["DATA_ALERTA"]).ge(TITLE_CHANGE_START_DATE)
    ].copy()
    history = history.drop_duplicates(
        subset=["NUM_UC", "TIPO_ALERTA", "CAMPO", "DATA_ALERTA", "VALOR_NOVO"],
        keep="last",
    ).sort_values(["DATA_ALERTA", "NUM_UC", "TIPO_ALERTA", "CAMPO"])
    atomic_csv(history[ALERT_COLUMNS], HISTORY_FILE)
    return int(len(history))


def change_detail(field: str, new: str) -> tuple[str, str]:
    if field == "SITUACAO_UC" and new == "DS":
        return "Desligamento", "A situação da UC mudou para desligada (DS)."
    if field == "SITUACAO_UC" and new == "CR":
        return "Desligamento", "A situação da UC mudou para corte (CR)."
    if field == "CLASSE":
        if new != "B1":
            return "Mudança de Classe", "A classe esperada é B1."
        return "Alteração cadastral", "A classe da UC foi alterada."
    if field == "GRUPO":
        if new != "1":
            return "Mudança de Classe", "O grupo esperado é 1."
        return "Alteração cadastral", "O grupo da UC foi alterado."
    if field in {"TARIFA_SOCIAL", "TARIFA_BRANCA"} and new == "S":
        return "Tarifa Especial Ativada", f"{field} passou a ser S."
    if field.startswith("GD_") or field in {
        "TIPO_GD_BENE",
        "DATA_INICIO_GD",
        "DATA_FIM_GD",
        "TIPO_GD_GERA",
    }:
        return "Alteração GD", "Informação de geração distribuída alterada."
    return "Alteração cadastral", "Valor cadastral alterado no último relatório."


def process_report(
    report: Path, force: bool = False, mobiflex_report: Path | None = None
) -> dict:
    if not BASE_FILE.exists():
        raise FileNotFoundError(f"Base consolidada não encontrada: {BASE_FILE}")

    base = pd.read_csv(BASE_FILE, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    incoming = pd.read_csv(
        report,
        sep=";",
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )
    base.columns = [text(column) for column in base.columns]
    incoming.columns = [text(column).lower() for column in incoming.columns]
    removed_personal_columns = sorted(
        PERSONAL_REPORT_COLUMNS.intersection(incoming.columns)
    )
    if removed_personal_columns:
        incoming = incoming.drop(columns=removed_personal_columns)
        atomic_csv(incoming, report, sep=";")

    mobiflex_report = mobiflex_report or newest_mobiflex_report()
    if not mobiflex_report.exists():
        raise FileNotFoundError(f"Relat\u00f3rio Mobiflex n\u00e3o encontrado: {mobiflex_report}")

    previous_summary = read_summary()
    if (
        previous_summary.get("arquivo_origem") == report.name
        and previous_summary.get("arquivo_mobiflex") == mobiflex_report.name
        and not force
    ):
        print(f"Relatório já processado e higienizado: {report.name}")
        return previous_summary

    for column in TRACKING_COLUMNS:
        if column not in base.columns:
            base[column] = ""
    validate_columns(
        base,
        {
            "NUM_UC",
            "SITUACAO_INICIAL",
            *TARGET_NORMALIZERS,
            *MOBIFLEX_TARGET_COLUMNS,
        },
        "base",
    )
    required_sources = set(FIELD_MAP).difference(OPTIONAL_SOURCE_COLUMNS)
    validate_columns(incoming, {"uc", *required_sources}, report.name)

    base["NUM_UC"] = base["NUM_UC"].map(identifier)
    incoming["uc"] = incoming["uc"].map(identifier)
    if base["NUM_UC"].eq("").any() or incoming["uc"].eq("").any():
        raise ValueError("Existem UCs sem identificador na base ou no relatório.")
    if base["NUM_UC"].duplicated().any():
        duplicates = base.loc[base["NUM_UC"].duplicated(False), "NUM_UC"].unique()
        raise ValueError(f"UCs duplicadas na base: {', '.join(duplicates[:10])}")
    if incoming["uc"].duplicated().any():
        duplicates = incoming.loc[incoming["uc"].duplicated(False), "uc"].unique()
        raise ValueError(f"UCs duplicadas no relatório: {', '.join(duplicates[:10])}")

    base_index = {uc: index for index, uc in base["NUM_UC"].items()}
    current_report_date = report_end_date(report)
    alerts: list[dict[str, str]] = []
    changed_ucs: set[str] = set()
    ignored_extra_ucs = 0
    matched_ucs = 0
    matched_uc_ids: set[str] = set()

    for _, source_row in incoming.iterrows():
        uc = source_row["uc"]
        if uc not in base_index:
            ignored_extra_ucs += 1
            continue

        converted = {
            target: normalizer(source_row[source])
            for source, (target, normalizer) in FIELD_MAP.items()
            if source in incoming.columns
        }
        title_change_date = converted.get("DT_MUD_TIT", "")
        converted["MUD_TIT"] = (
            "S"
            if title_change_date
            and pd.Timestamp(title_change_date) >= TITLE_CHANGE_START_DATE
            else ""
        )
        matched_ucs += 1
        matched_uc_ids.add(uc)
        index = base_index[uc]
        group = group_label(base.at[index, "SITUACAO_INICIAL"])
        previous_title_date = iso_date(base.at[index, "DT_MUD_TIT"])
        new_title_date = converted.get("DT_MUD_TIT", "")
        if (
            new_title_date
            and pd.Timestamp(new_title_date) >= TITLE_CHANGE_START_DATE
            and new_title_date != previous_title_date
        ):
            add_alert(
                alerts,
                uc,
                group,
                "Mudança de Titularidade",
                "MUD_TIT",
                previous_title_date,
                new_title_date,
                "Nova mudança de titularidade identificada no relatório.",
                report.name,
                new_title_date,
            )
            changed_ucs.add(uc)
        for field in MONITORED_COLUMNS:
            if field not in converted:
                continue
            normalizer = TARGET_NORMALIZERS[field]
            previous = normalizer(base.at[index, field])
            new = converted[field]
            if previous != new:
                if field in {"TARIFA_SOCIAL", "TARIFA_BRANCA"} and new != "S":
                    continue
                alert_type, detail = change_detail(field, new)
                add_alert(
                    alerts,
                    uc,
                    group,
                    alert_type,
                    field,
                    previous,
                    new,
                    detail,
                    report.name,
                    alert_date_for_change(
                        field, new, converted, current_report_date
                    ),
                )
                changed_ucs.add(uc)

        # Keep all mapped consolidated fields current, including non-alert fields.
        for field, new in converted.items():
            old = TARGET_NORMALIZERS[field](base.at[index, field])
            if old != new:
                base.at[index, field] = new

        # Class/group are persistent compliance rules, so an unchanged invalid
        # value remains visible in every report that contains the UC.
        for field, expected in (("CLASSE", "B1"), ("GRUPO", "1")):
            current = converted[field]
            already_alerted = any(
                alert["NUM_UC"] == uc and alert["CAMPO"] == field
                for alert in alerts
            )
            if current != expected and not already_alerted:
                add_alert(
                    alerts,
                    uc,
                    group,
                    "Mudança de Classe",
                    field,
                    current,
                    current,
                    f"Valor esperado: {expected}.",
                    report.name,
                    current_report_date,
                )

    mobiflex_counts = update_from_mobiflex(
        base, base_index, mobiflex_report, changed_ucs
    )

    missing_update_ucs = set(base_index).difference(matched_uc_ids)
    for uc in sorted(missing_update_ucs, key=lambda value: (len(value), value)):
        index = base_index[uc]
        add_alert(
            alerts,
            uc,
            group_label(base.at[index, "SITUACAO_INICIAL"]),
            "Sem atualização",
            "PRESENCA_NO_RELATORIO",
            "Presente na base",
            "Ausente no relatório",
            "A UC não recebeu dados no último relatório processado.",
            report.name,
            current_report_date,
        )

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    alerts_frame = pd.DataFrame(alerts, columns=ALERT_COLUMNS)
    atomic_csv(base, BASE_FILE)
    atomic_csv(alerts_frame, ALERT_FILE)
    history_count = update_alert_history(base, alerts_frame, report)

    filename_match = REPORT_PATTERN.fullmatch(report.name)
    summary = {
        "arquivo_origem": report.name,
        "arquivo_mobiflex": mobiflex_report.name,
        "periodo_inicio": filename_match.group(1) if filename_match else "",
        "periodo_fim": filename_match.group(2) if filename_match else "",
        "processado_em": datetime.now().astimezone().isoformat(timespec="seconds"),
        "ucs_no_relatorio": int(len(incoming)),
        "ucs_correspondentes": int(matched_ucs),
        "ucs_extras_ignoradas": int(ignored_extra_ucs),
        "ucs_sem_atualizacao": int(len(missing_update_ucs)),
        "ucs_alteradas": int(len(changed_ucs)),
        "alertas": int(len(alerts_frame)),
        "eventos_historicos": history_count,
        "total_base": int(len(base)),
        "colunas_pessoais_removidas_relatorio": removed_personal_columns,
        "mobiflex_ucs": mobiflex_counts["linhas"],
        "mobiflex_ucs_correspondentes": mobiflex_counts["ucs_correspondentes"],
        "mobiflex_ucs_extras_ignoradas": mobiflex_counts["ucs_extras_ignoradas"],
    }
    atomic_json(summary, SUMMARY_FILE)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Atualiza a base consolidada e gera alertas do relatório mais recente."
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="Relatório específico. Por padrão, usa o arquivo datado mais recente em data/.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reprocessa o relatório mesmo se ele já constar como a última atualização.",
    )
    parser.add_argument(
        "--mobiflex-input",
        type=Path,
        help=(
            "Relat\u00f3rio cadastral Mobiflex espec\u00edfico. Por padr\u00e3o, usa o "
            "arquivo Mobiflex datado mais recente em data/."
        ),
    )
    args = parser.parse_args()
    report = args.input.resolve() if args.input else newest_report()
    if not report.exists() or not REPORT_PATTERN.fullmatch(report.name):
        raise ValueError(
            "O relatório deve existir e seguir o nome "
            "mdm-sandbox_clientes_novo-YYYYMMDD-YYYYMMDD.csv."
        )
    mobiflex_report = (
        args.mobiflex_input.resolve() if args.mobiflex_input else newest_mobiflex_report()
    )
    summary = process_report(
        report, force=args.force, mobiflex_report=mobiflex_report
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

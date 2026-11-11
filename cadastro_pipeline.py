"""Local Cadastro -> full workbook + privacy-filtered BI, with auditable GD history.

Run ``python update_base.py --dry-run`` to validate/stage, then without --dry-run.
Original Cadastro exports and Amostra workbooks are never rewritten.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import unicodedata
from io import BytesIO
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

import update_base as legacy

ROOT = Path(__file__).resolve().parent
COPEL = ROOT.parent
BASELINE_DATE = "2025-12-31"
EXPORT_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2})-consulta_(GD|BEN|UC)\.csv$", re.I)
MDM_PATTERN = re.compile(r"-(\d{8})-(\d{8})(?:-ucs_sem_dados)?\.csv$")
ANNUAL = "mdm-sandbox_clientes_novo-20260101-20261231.csv"
CORRECTED = "mdm-sandbox_clientes_novo-20260611-202606011.csv"
ZERO = Decimal(0)
GD_COLUMNS = {
    "GD": {"COD_UN_CONS_UEE", "NUM_SEQ_KCG", "QTD_POT_GER_KCG", "DTA_SOL_ACES_KCG",
           "DTA_FIM_VIGN_KCG", "COD_TIPO_CSS_GER_KCD", "PCT_DIS_KCD"},
    "BEN": {"COD_UN_CONS_UEE", "COD_UN_CONS_BEN_XBG", "QTD_POT_GER_UTG",
            "DTA_INC_XBG", "PCT_RAT_XBG"},
    "UC": {"ISN_UC", "NUM_CLI_UC", "TIPO_SIT_UC"},
}
GD_FIELDS = ["GD_GERADORA", "GD_BENEFICIARIA", "POTENCIA_INSTALADA_KW", "TIPO_GD_GERA",
             "TIPO_GD_BENE", "POTENCIA_GDI_KW", "POTENCIA_GDII_KW", "MODALIDADE_GD",
             "GERADORES_EXTERNOS", "DATA_INICIO_GD", "DATA_FIM_GD", "GD_BENE_INIC"]
ALERT_EXTRA = ["ID_EVENTO", "NATUREZA", "BASE_DATA", "DATA_EFETIVA", "OBSERVACAO_ANTERIOR",
               "OBSERVACAO_ATUAL", "ARQUIVO_ANTERIOR", "STATUS_QUALIDADE", "UC_RELACIONADA"]
ALERT_COLUMNS = legacy.ALERT_COLUMNS + ALERT_EXTRA


def text(value):
    return "" if value is None else str(value).strip()


def identifier(value):
    value = text(value)
    # Preserve text identifiers and leading zeros; only remove an Excel .0 suffix.
    return re.sub(r"\.0+$", "", value) if re.fullmatch(r"\d+\.0+", value) else value


def folded(value):
    return " ".join(unicodedata.normalize("NFKD", text(value)).encode("ascii", "ignore").decode().upper().split())


def gd_types(value):
    return " | ".join(sorted(set(re.findall(r"GDII?\b", re.sub(r"GD\s+", "GD", folded(value))))))


def day(value):
    value = text(value)
    if not value:
        return ""
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M:%S.%f", "%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"Data inválida: {value!r}")


def number(value):
    value = text(value)
    result = Decimal(value.replace(",", ".")) if value else None
    if result is not None and (not result.is_finite() or result < ZERO):
        raise ValueError(f"Valor numérico inválido: {value}")
    return result


def numeric(value):
    return "" if value is None else format(value, "f")


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def source_workbook(path, **options):
    """Read cloud-backed files sequentially; report the actual unavailable path."""
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise OSError(f"Não foi possível ler {path}. Se estiver no OneDrive, use 'Sempre manter neste dispositivo' e aguarde o download.") from exc
    return load_workbook(BytesIO(content), **options)


def csv_rows(path, required=()):
    try:
        yield from _csv_rows(path, required)
    except OSError as exc:
        raise OSError(f"Não foi possível ler {path}. No OneDrive, use 'Sempre manter neste dispositivo' e aguarde o download.") from exc


def _csv_rows(path, required=()):
    # Restart before yielding if the file needs the Windows encoding.
    with path.open("rb") as stream:
        sample = stream.read(128 * 1024)
    try:
        sample.decode("utf-8-sig")
        encoding = "utf-8-sig"
    except UnicodeDecodeError:
        encoding = "cp1252"
    with path.open(encoding=encoding, newline="") as stream:
        reader = csv.DictReader(stream, delimiter=";")
        if "uc" in required:
            raw_headers = [text(column) for column in (reader.fieldnames or [])]
            reader.fieldnames = ["uc_join" if column == "UC" and "uc" in raw_headers else column.lower()
                                 for column in raw_headers]
            if len(reader.fieldnames) != len(set(reader.fieldnames)):
                raise ValueError(f"{path.name}: colunas MDM duplicadas após normalização")
        missing = set(required) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path.name}: colunas ausentes {sorted(missing)}")
        for line, row in enumerate(reader, 2):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"{path.name}:{line}: número de colunas incorreto")
            yield line, {key: text(value) for key, value in row.items()}


def write_rows(path, rows, columns=None):
    rows = list(rows)
    columns = columns or (list(rows[0]) if rows else [])
    if not columns:
        raise ValueError(f"Schema ausente: {path}")
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def event(uc, field, old, new, observed, previous="", source="", old_source="",
          effective="", kind="Alteração GD", nature="Mudança", quality="", related="", detail=""):
    effective = day(effective)
    # Effective dates outside the observed interval are context, not evidence
    # of when a changed value was introduced (e.g. a corrected old start date).
    supported = effective and effective <= observed and (not previous or effective > previous)
    basis = "Data cadastrada" if supported else "Primeira observação"
    payload = dict(DATA_ALERTA=effective if supported else observed, NUM_UC=uc, GRUPO_UC="",
                   TIPO_ALERTA=kind, CAMPO=field, VALOR_ANTERIOR=text(old), VALOR_NOVO=text(new),
                   DETALHE=detail, ARQUIVO_ORIGEM=source, NATUREZA=nature, BASE_DATA=basis,
                   DATA_EFETIVA=effective, OBSERVACAO_ANTERIOR=previous, OBSERVACAO_ATUAL=observed,
                   ARQUIVO_ANTERIOR=old_source, STATUS_QUALIDADE=quality, UC_RELACIONADA=related)
    payload["ID_EVENTO"] = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]
    return payload


def issue(uc, kind, detail, source="", observed=""):
    return dict(NUM_UC=uc, TIPO=kind, DETALHE=detail, ARQUIVO_ORIGEM=source, DATA_FONTE=observed)


def discover(directory):
    batches = defaultdict(dict)
    for path in sorted(directory.glob("*consulta*.csv")):
        match = EXPORT_PATTERN.fullmatch(path.name)
        if not match:
            raise ValueError(f"Nome GD/BEN/UC não reconhecido: {path.name}")
        dt, kind = match.groups()
        day(dt)
        if kind.upper() in batches[dt]:
            raise ValueError(f"Duas fontes {kind} em {dt}")
        batches[dt][kind.upper()] = path
    if not batches:
        raise FileNotFoundError(f"Sem exportações em {directory}")
    return dict(sorted(batches.items()))


def read_gd(path, scope, quality, observed):
    rows = defaultdict(list)
    for line, r in csv_rows(path, GD_COLUMNS["GD"]):
        uc = r["COD_UN_CONS_UEE"]
        if not uc:
            raise ValueError(f"{path.name}:{line}: UC vazia")
        if uc in scope:
            r["_line"] = str(line)
            rows[uc].append(r)
    return rows


def read_ben(path, scope, observed):
    pairs = defaultdict(list)
    for line, r in csv_rows(path, GD_COLUMNS["BEN"]):
        gen, ben = r["COD_UN_CONS_UEE"], r["COD_UN_CONS_BEN_XBG"]
        if not gen or not ben:
            raise ValueError(f"{path.name}:{line}: UC geradora/beneficiária vazia")
        if gen in scope or ben in scope:
            r["_line"] = str(line)
            pairs[gen, ben].append(r)
    return pairs


def generator_state(rows, reference, include_undated=True):
    active = [r for r in rows if (day(r["DTA_SOL_ACES_KCG"]) or include_undated)
              and (not day(r["DTA_SOL_ACES_KCG"]) or day(r["DTA_SOL_ACES_KCG"]) <= reference)
              and (not day(r["DTA_FIM_VIGN_KCG"]) or day(r["DTA_FIM_VIGN_KCG"]) > reference)]
    powers = {number(r["QTD_POT_GER_KCG"]) for r in active} - {None}
    power = max(powers) if powers else None
    flags = []
    if len(powers) > 1:
        flags.append("POTENCIAS_CONFLITANTES_MAIOR_ADOTADA")
    if len({r["NUM_SEQ_KCG"] for r in active}) > 1:
        flags.append("MULTIPLOS_REGISTROS_ATIVOS")
    if active and power is None:
        flags.append("POTENCIA_DESCONHECIDA")
    allocations = set()
    for sequence in {r["NUM_SEQ_KCG"] for r in active}:
        entries = {(r["COD_TIPO_CSS_GER_KCD"], r.get("COD_SUB_TIPO_CSS_GER_KCD", ""), number(r["PCT_DIS_KCD"]))
                   for r in active if r["NUM_SEQ_KCG"] == sequence and number(r["QTD_POT_GER_KCG"]) == power}
        if not entries:
            continue
        split = dict.fromkeys(("GDI", "GDII", "OUTROS"), ZERO)
        if any(pct is None or pct > 100 for typ, sub, pct in entries) or sum((pct for typ, sub, pct in entries), ZERO) != 100:
            flags.append("PERCENTUAL_CLASSIFICACAO_INVALIDO")
            continue
        for typ, sub, pct in entries:
            split[typ if typ in split else "OUTROS"] += pct
        allocations.add(tuple(split.values()))
    split = dict.fromkeys(("GDI", "GDII", "OUTROS", "SEM_CLASSIFICACAO"), ZERO)
    if power is not None:
        if len(allocations) == 1 and "PERCENTUAL_CLASSIFICACAO_INVALIDO" not in flags:
            for key, pct in zip(("GDI", "GDII", "OUTROS"), next(iter(allocations))):
                split[key] = power * pct / 100
        else:
            split["SEM_CLASSIFICACAO"] = power
            if active:
                flags.append("CLASSIFICACAO_AMBIGUA")
    starts = sorted({day(r["DTA_SOL_ACES_KCG"]) for r in active if day(r["DTA_SOL_ACES_KCG"])})
    if active and not starts:
        flags.append("DATA_INICIO_GERADORA_DESCONHECIDA")
    ends = sorted({day(r["DTA_FIM_VIGN_KCG"]) for r in rows if day(r["DTA_FIM_VIGN_KCG"]) and day(r["DTA_FIM_VIGN_KCG"]) <= reference})
    return dict(active=bool(active), power=power, split=split,
                types=" | ".join(sorted({r["COD_TIPO_CSS_GER_KCD"] for r in active if r["COD_TIPO_CSS_GER_KCD"]})),
                start=starts[0] if starts else "", end=ends[-1] if ends and not active else "",
                flags=sorted(set(flags)))


def link_states(pairs, reference, source, observed):
    result = {}
    for (gen, ben), rows in pairs.items():
        active = [r for r in rows if not day(r["DTA_INC_XBG"]) or day(r["DTA_INC_XBG"]) <= reference]
        if not active:
            continue
        powers = {number(r["QTD_POT_GER_UTG"]) for r in active} - {None}
        percentages = {number(r["PCT_RAT_XBG"]) for r in active} - {None}
        flags = []
        if len(powers) > 1:
            flags.append("POTENCIAS_BEN_CONFLITANTES_MAIOR_ADOTADA")
        if len(percentages) > 1:
            flags.append("RATEIO_CONFLITANTE")
        starts = sorted({day(r["DTA_INC_XBG"]) for r in active if day(r["DTA_INC_XBG"])})
        if not starts:
            flags.append("DATA_INCLUSAO_BENEFICIARIA_DESCONHECIDA")
        if any(value > 100 for value in percentages):
            flags.append("RATEIO_FORA_DE_0_A_100")
        result[gen, ben] = dict(UC_GERADORA=gen, UC_BENEFICIARIA=ben,
            POTENCIA_GERADOR_KW=numeric(max(powers) if powers else None),
            PERCENTUAL_RATEIO=numeric(next(iter(percentages))) if len(percentages) == 1 else "",
            PRIORIDADE=" | ".join(sorted({r.get("NUM_PRI_XBG", "") for r in active} - {""})),
            DATA_INICIO=starts[0] if starts else "",
            DATA_INICIO_VIGENCIA=" | ".join(sorted({day(r.get("DTA_INIC_VIGN_XBG")) for r in active} - {""})),
            MODALIDADE=" | ".join(sorted({r.get("COD_MODL_DIS_UTG", "") for r in active} - {""})),
            STATUS_QUALIDADE=";".join(flags), DATA_FONTE=observed, ARQUIVO_ORIGEM=source,
            STATUS_VINCULO="PRESENTE_NO_EXPORT", AUTO_RELACAO="S" if gen == ben else "N")
    return result


def enrich_links(links, gd, reference):
    for (gen, ben), row in links.items():
        generator = generator_state(gd.get(gen, []), reference, include_undated=reference >= row["DATA_FONTE"])
        flags = set(filter(None, row["STATUS_QUALIDADE"].split(";"))) | set(generator["flags"])
        power = generator["power"]
        row["TIPO_GD_GERADOR"] = generator["types"]
        if power is not None:
            if row["POTENCIA_GERADOR_KW"] and number(row["POTENCIA_GERADOR_KW"]) != power:
                flags.add("POTENCIA_DIVERGE_BEN")
            row["POTENCIA_GERADOR_KW"] = numeric(power)
        elif gd.get(gen):
            flags.add("GERADOR_SEM_REGISTRO_ATIVO")
        else:
            flags.add("POTENCIA_FALLBACK_BEN")
        row["STATUS_QUALIDADE"] = ";".join(sorted(flags))
    return links


def make_states(scope, gd, links, reference, observed, gd_source, ben_source, baseline=False):
    states = {}
    for uc in sorted(scope):
        g = generator_state(gd.get(uc, []), reference, include_undated=reference >= observed)
        if reference < observed and any(not day(r["DTA_SOL_ACES_KCG"]) for r in gd.get(uc, [])):
            g["flags"].append("INICIO_GD_DESCONHECIDO_NAO_RECONSTRUIDO")
        incoming = {gen: r for (gen, ben), r in links.items() if ben == uc}
        outgoing = [r for (gen, ben), r in links.items() if gen == uc]
        fallback = {number(r["POTENCIA_GERADOR_KW"]) for r in outgoing} - {None}
        # A link alone does not assert a generator was active after an explicit end.
        if not gd.get(uc) and outgoing:
            g["active"] = True
            g["power"] = max(fallback) if fallback else None
            g["split"]["SEM_CLASSIFICACAO"] = g["power"] or ZERO
            g["flags"].append("GERADORA_APENAS_BEN_FALLBACK")
        if g["power"] is not None and fallback and fallback != {g["power"]}:
            g["flags"].append("POTENCIA_DIVERGE_BEN")
        starts = sorted({r["DATA_INICIO"] for r in incoming.values()} - {""})
        flags = sorted(set(g["flags"] + [f for r in [*incoming.values(), *outgoing] for f in r["STATUS_QUALIDADE"].split(";") if f]))
        states[uc] = dict(NUM_UC=uc, DATA_REFERENCIA=reference, DATA_FONTE_GD=observed,
            DATA_FONTE_BEN=observed, GD_GERADORA="S" if g["active"] else "N",
            GD_BENEFICIARIA="S" if incoming else "N",
            PERFIL_GD=("Geradora e beneficiária" if incoming else "Geradora") if g["active"] else ("Beneficiária" if incoming else "Sem GD identificada"),
            POTENCIA_INSTALADA_KW=numeric(g["power"]),
            POTENCIA_GDI_KW=numeric(g["split"]["GDI"]) if g["power"] is not None else "",
            POTENCIA_GDII_KW=numeric(g["split"]["GDII"]) if g["power"] is not None else "",
            POTENCIA_OUTROS_KW=numeric(g["split"]["OUTROS"]) if g["power"] is not None else "",
            POTENCIA_SEM_CLASSIFICACAO_KW=numeric(g["split"]["SEM_CLASSIFICACAO"]) if g["power"] is not None else "",
            TIPO_GD_GERA=g["types"], DATA_INICIO_GD=g["start"], DATA_FIM_GD=g["end"],
            TIPO_GD_BENE=" | ".join(sorted({r.get("TIPO_GD_GERADOR", "") for r in incoming.values()} - {""})),
            GD_BENE_INIC=starts[0] if starts else "",
            GERADORES_EXTERNOS=" | ".join(sorted(set(incoming) - {uc})),
            QUANTIDADE_GERADORES_EXTERNOS=len(set(incoming) - {uc}),
            BENEFICIARIAS_EXTERNAS=len({r["UC_BENEFICIARIA"] for r in outgoing} - {uc}),
            POTENCIA_EXTERNA_ASSOCIADA_KW=(numeric(sum((number(r["POTENCIA_GERADOR_KW"]) for gen, r in incoming.items() if gen != uc), ZERO))
                if all(r["POTENCIA_GERADOR_KW"] for gen, r in incoming.items() if gen != uc) else ""),
            MODALIDADE_GD=" | ".join(sorted({r["MODALIDADE"] for r in [*incoming.values(), *outgoing]} - {""})),
            STATUS_QUALIDADE=";".join(flags) or "OK", REVISAO_MANUAL="S" if flags else "N",
            BASE_HISTORICA="RECONSTRUIDA_COM_DATAS_CADASTRADAS" if baseline else "EXPORT_DATADO",
            GD_SEM_VINCULO_CONFIRMADO="N",
            ARQUIVO_GD=gd_source, ARQUIVO_BEN=ben_source)
    return states


def read_baseline(path, scope):
    workbook = source_workbook(path, read_only=True, data_only=True)
    result = {}
    for sheet in workbook.worksheets:
        rows = sheet.iter_rows(values_only=True)
        headers = None
        for index, values in enumerate(rows, 1):
            labels = [text(v).upper() for v in values]
            if ("NUM_UC" in labels or "UC" in labels) and (
                any(field in labels for field in ("TIPO_GD_GERA", "GD_BENE_INIC", "DATA_INICIO_GD", "GD2"))
                or any(folded(field).startswith("QUAL GD") for field in labels)
            ):
                headers = labels
                break
            if index >= 20:
                break
        if headers is None:
            continue
        key = "NUM_UC" if "NUM_UC" in headers else "UC"
        for line, values in enumerate(rows, index + 1):
            row = dict(zip(headers, values))
            uc = identifier(row.get(key))
            if uc not in scope:
                continue
            candidate = {k: row.get(k) for k in ("TIPO_GD_GERA", "DATA_INICIO_GD", "DATA_FIM_GD", "GD_BENE_INIC", "GD_BENE_FIM", "TIPO_GD_BENE", "POSSUI_GD_CLIENTE")}
            if "GD2" in headers or any(folded(field).startswith("QUAL GD") for field in headers):
                type_field = "GD2" if "GD2" in headers else next(field for field in headers if folded(field).startswith("QUAL GD"))
                raw_type = text(row.get(type_field))
                types = gd_types(raw_type)
                mode_field = next((field for field in headers if folded(field) == "AUTOCONSUMO LOCAL OU REMOTO"), "")
                mode = folded(row.get(mode_field))
                declared = "S" if types else "N" if raw_type == "0" or mode == "SEM GD" else ""
                candidate.update(GD_DECLARADA=declared, TIPO_GD_DECLARADO=types,
                    ABA_AMOSTRA=sheet.title, LINHA_AMOSTRA=str(line), COLUNA_AMOSTRA=type_field,
                    VALOR_AMOSTRA_ORIGINAL=raw_type,
                    NOTA_AMOSTRA=("GD2 é declaração de GD, sem distinguir geradora/beneficiária." if type_field == "GD2"
                                  else "Presença interpretada por tipo e autoconsumo; 'Se tem ou Não GD' contém UCs e não foi usado como indicador."))
                # 'Se tem ou Não GD' in this workbook returns UC numbers. It is
                # not a boolean and must never be treated as one. GD2 and the
                # explicit type/mode columns are declarations, not UC roles.
            if uc in result and result[uc] != candidate:
                raise ValueError(f"Baseline com registros divergentes: UC {uc}")
            result[uc] = candidate
    workbook.close()
    if not result:
        raise ValueError(f"Cabeçalho NUM_UC/UC ou UCs BI não encontrados em {path.name}")
    return result


def baseline_audit(baseline, states, file, observed, gd_rows):
    audit = []
    for uc, current in states.items():
        old = baseline.get(uc)
        if old is None:
            audit.append(dict(NUM_UC=uc, CAMPO="PRESENCA", VALOR_AMOSTRA="", VALOR_RECONSTRUIDO="",
                              STATUS="AUSENTE_AMOSTRA", DATA_REFERENCIA=BASELINE_DATE,
                              DATA_FONTE_GD=observed, ARQUIVO_AMOSTRA=file.name,
                              LIMITACAO="Não foi localizado na amostra final."))
            continue
        survey = "GD_DECLARADA" in old
        fields = ("GD_DECLARADA", "TIPO_GD_DECLARADO") if survey else ("TIPO_GD_GERA", "TIPO_GD_BENE", "DATA_INICIO_GD", "GD_BENE_INIC")
        for field in fields:
            previous = day(old.get(field)) if "INIC" in field else text(old.get(field)).upper()
            if field == "GD_DECLARADA":
                reconstructed = "S" if current["GD_GERADORA"] == "S" or current["GD_BENEFICIARIA"] == "S" else "N"
            elif field == "TIPO_GD_DECLARADO":
                reconstructed = gd_types(current["TIPO_GD_GERA"] or current["TIPO_GD_BENE"])
            else:
                reconstructed = current[field]
            status = "CONFERE" if previous == reconstructed else "DIVERGENCIA_REVISAR"
            if survey and not previous:
                status = "COMPLEMENTADO_PELA_FONTE_GD" if reconstructed else "SEM_INFORMACAO_NA_AMOSTRA"
            if status != "CONFERE" and reconstructed:
                status = "CORRIGIDO_PELA_FONTE_GD" if previous else "COMPLEMENTADO_PELA_FONTE_GD"
            if status != "CONFERE" and current["REVISAO_MANUAL"] == "S":
                status = "REVISAR_FONTE_NAO_CONFIRMADA_OU_CONFLITANTE"
            audit.append(dict(NUM_UC=uc, CAMPO=field, VALOR_AMOSTRA=previous,
                VALOR_RECONSTRUIDO=reconstructed, STATUS=status, DATA_REFERENCIA=BASELINE_DATE,
                DATA_FONTE_GD=observed, ARQUIVO_AMOSTRA=file.name,
                LIMITACAO="Baseline retrospectiva: datas cadastradas; classificação sem vigência histórica própria.",
                ABA_AMOSTRA=old.get("ABA_AMOSTRA", ""), LINHA_AMOSTRA=old.get("LINHA_AMOSTRA", ""),
                COLUNA_AMOSTRA=old.get("COLUNA_AMOSTRA", field),
                VALOR_AMOSTRA_ORIGINAL=old.get("VALOR_AMOSTRA_ORIGINAL", previous),
                NOTA_AMOSTRA=old.get("NOTA_AMOSTRA", "")))
    return audit


def preserve_unconfirmed_baseline(initial, baseline, gd, pairs, reference=BASELINE_DATE):
    """Absence in October cannot disprove an Amostra GD position in 2025."""
    for uc, row in initial.items():
        old = baseline.get(uc, {})
        known_generator = bool(gd.get(uc)) or any(gen == uc for gen, ben in pairs)
        known_beneficiary = any(ben == uc for gen, ben in pairs)
        gstart, gend = day(old.get("DATA_INICIO_GD")), day(old.get("DATA_FIM_GD"))
        bstart, bend = day(old.get("GD_BENE_INIC")), day(old.get("GD_BENE_FIM"))
        retained = False
        if not known_generator and not known_beneficiary and old.get("GD_DECLARADA") == "S":
            row["GD_SEM_VINCULO_CONFIRMADO"] = "S"
            retained = True
        if not known_generator and ((gstart and gstart <= reference) or (not gstart and text(old.get("TIPO_GD_GERA")))) and (not gend or gend > reference):
            row.update(GD_GERADORA="S", DATA_INICIO_GD=gstart, TIPO_GD_GERA=text(old.get("TIPO_GD_GERA")))
            retained = True
        if not known_beneficiary and bstart and bstart <= reference and (not bend or bend > reference):
            row.update(GD_BENEFICIARIA="S", GD_BENE_INIC=bstart)
            retained = True
        if retained:
            row["STATUS_QUALIDADE"] = "AMOSTRA_SEM_CONFIRMACAO_NO_EXPORT_GD"
            row["REVISAO_MANUAL"] = "S"
            row["PERFIL_GD"] = ("Geradora e beneficiária" if row["GD_BENEFICIARIA"] == "S" else "Geradora") if row["GD_GERADORA"] == "S" else "Beneficiária"
            if row["GD_SEM_VINCULO_CONFIRMADO"] == "S":
                row["PERFIL_GD"] = "GD declarada, vínculo não confirmado"


def compare_gd(previous, current, source, old_source):
    events = []
    for uc, row in current.items():
        old = previous[uc]
        for field in GD_FIELDS:
            a, b = text(old[field]), text(row[field])
            if field.startswith("POTENCIA"):
                if number(a) == number(b):
                    continue
            elif a == b:
                continue
            if field == "GD_GERADORA" and b == "N" and not row["DATA_FIM_GD"]:
                nature = "Ausência no export"
                detail = "Geradora não identificada neste export; ausência não comprova cancelamento."
            elif field == "GD_BENEFICIARIA" and b == "N":
                nature = "Ausência no export"
                detail = "Vínculo não presente neste export; fonte sem data de fim."
            else:
                nature = "Mudança"
                detail = "Diferença entre observações cadastrais."
            effective = ""
            if field == "GD_GERADORA":
                effective = row["DATA_INICIO_GD"] if b == "S" else row["DATA_FIM_GD"]
            elif field == "GD_BENEFICIARIA" and b == "S":
                effective = row["GD_BENE_INIC"]
            if field == "POTENCIA_INSTALADA_KW" and a and b:
                detail += f" Variação: {numeric(number(b) - number(a))} kW."
            events.append(event(uc, field, a, b, row["DATA_REFERENCIA"], old["DATA_REFERENCIA"],
                source, old_source, effective, nature=nature,
                quality=row["STATUS_QUALIDADE"], detail=detail))
    return events


def compare_links(previous, current, scope, observed, old_observed, source, old_source):
    result = []
    for pair in sorted(previous.keys() | current.keys()):
        old, new = previous.get(pair), current.get(pair)
        affected = sorted(set(pair) & scope)
        if old is None:
            fields = [("VINCULO_GD", "Não observado", "Presente", "Mudança")]
        elif new is None:
            fields = [("VINCULO_GD", "Presente", "Não observado", "Ausência no export")]
        else:
            fields = [(f, old[f], new[f], "Mudança") for f in ("PERCENTUAL_RATEIO", "PRIORIDADE", "MODALIDADE")
                      if old[f] != new[f]]
        for uc in affected:
            for field, a, b, nature in fields:
                result.append(event(uc, field, a, b, observed, old_observed, source, old_source,
                    new["DATA_INICIO"] if old is None and new else "", nature=nature,
                    related=pair[0] if uc != pair[0] else pair[1],
                    quality=(new or old)["STATUS_QUALIDADE"],
                    detail=f"Geradora {pair[0]} → beneficiária {pair[1]}. Ausência não comprova encerramento."))
    return result


def mdm_date(path):
    if path.name == CORRECTED:
        return "2026-06-11"
    match = MDM_PATTERN.search(path.name)
    if not match:
        return None
    return datetime.strptime(match[2], "%Y%m%d").date().isoformat()


def mdm_history(paths, scope, quality):
    observations = defaultdict(lambda: defaultdict(list))
    dates = {}
    for position, path in enumerate(paths, 1):
        if position == 1 or position % 25 == 0:
            print(f"MDM: {position}/{len(paths)} arquivos", flush=True)
        if path.name == ANNUAL:
            continue
        observed = mdm_date(path)
        if not observed:
            continue
        dates[path] = observed
        if path.name.endswith("-ucs_sem_dados.csv"):
            continue
        for line, raw in csv_rows(path, {"uc"}):
            uc = raw["uc"]
            if uc not in scope:
                continue
            if raw.get("uc_join") and raw["uc_join"] != uc:
                quality.append(issue(uc, "MDM_UC_JOIN_DIVERGENTE", f"Linha {line}", path.name, observed))
                continue
            for field, (target, normalizer) in legacy.FIELD_MAP.items():
                if field in raw:
                    if target == "NUM_UC_ANEEL":
                        normalizer = identifier
                    observations[uc, target][observed].append((normalizer(raw[field]), path.name))
    current = defaultdict(dict)
    events = []
    for (uc, field), by_date in observations.items():
        previous = None
        for observed, values in sorted(by_date.items()):
            unique = {value for value, filename in values}
            source = " | ".join(sorted({filename for value, filename in values}))
            if len(unique) != 1:
                quality.append(issue(uc, "CONFLITO_MDM", f"{field}: {' | '.join(sorted(unique))}", source, observed))
                previous = None
                current[uc].pop(field, None)
                continue
            value = next(iter(unique))
            current[uc][field] = value
            # GD is reconstructed from its authoritative export series below.
            is_gd = field.startswith("GD_") or field in {"TIPO_GD_GERA", "DATA_INICIO_GD", "DATA_FIM_GD", "POSSUI_GD_CLIENTE"}
            if previous and value != previous[1] and not is_gd and field in {*legacy.MONITORED_COLUMNS, "DT_MUD_TIT"}:
                kind, detail = legacy.change_detail(field, value)
                if field == "DT_MUD_TIT":
                    kind = "Mudança de Titularidade"
                effective = value if field == "DT_MUD_TIT" else ""
                if field == "SITUACAO_UC":
                    companions = observations.get((uc, "DT_SITUACAO_UC"), {}).get(observed, [])
                    valid = {x for x, filename in companions}
                    effective = next(iter(valid)) if len(valid) == 1 else ""
                if field in {"TARIFA_SOCIAL", "TARIFA_BRANCA"} and value != "S":
                    kind, detail = "Tarifa Especial Desativada", "Tarifa especial desativada."
                if field == "SITUACAO_UC" and value not in {"DS", "CR"}:
                    kind = "Mudança de Situação"
                events.append(event(uc, field, previous[1], value, observed, previous[0], source,
                                    previous[2], effective, kind, detail=detail))
            elif previous is None and field == "DT_MUD_TIT" and value and value[:4] == "2026":
                events.append(event(uc, field, "", value, observed, source=source, effective=value,
                                    kind="Mudança de Titularidade", nature="Evento cadastrado",
                                    detail="Data registrada na primeira observação; titular anterior não conhecido."))
            previous = observed, value, source
    return current, events, dates


def build_gd(batches, scope, baseline, baseline_path, quality):
    states_by_date = {}
    events, sources, all_links = [], [], []
    previous_states = previous_links = None
    previous_observed = previous_source = ""
    audit = []
    complete = {dt: batch for dt, batch in batches.items() if set(batch) == {"GD", "BEN", "UC"}}
    if not complete:
        raise ValueError("Nenhum lote completo GD/BEN/UC; bases não serão atualizadas")
    for dt, batch in batches.items():
        for kind, path in batch.items():
            sources.append(dict(arquivo=path.name, data=dt, tipo=kind, sha256=digest(path),
                                status="COMPLETO" if dt in complete else "LOTE_INCOMPLETO"))
        if dt not in complete:
            quality.append(issue("", "LOTE_INCOMPLETO", "Faltam: " + ", ".join(sorted({"GD", "BEN", "UC"} - set(batch))), observed=dt))
            continue
        print(f"GD: {dt}", flush=True)
        pairs = read_ben(batch["BEN"], scope, dt)
        relevant = scope | {gen for gen, ben in pairs}
        gd = read_gd(batch["GD"], relevant, quality, dt)
        links = enrich_links(link_states(pairs, dt, batch["BEN"].name, dt), gd, dt)
        current = make_states(scope, gd, links, dt, dt, batch["GD"].name, batch["BEN"].name)
        source = batch["GD"].name + " | " + batch["BEN"].name
        if previous_states is None:
            initial_links = enrich_links(link_states(pairs, BASELINE_DATE, batch["BEN"].name, dt), gd, BASELINE_DATE)
            initial = make_states(scope, gd, initial_links, BASELINE_DATE, dt, batch["GD"].name, batch["BEN"].name, True)
            preserve_unconfirmed_baseline(initial, baseline, gd, pairs)
            audit = baseline_audit(baseline, initial, baseline_path, dt, gd)
            states_by_date[BASELINE_DATE] = initial
            previous_states, previous_links = initial, initial_links
            previous_observed, previous_source = BASELINE_DATE, source
            # Start/end dates allow reconstruction of transitions before the
            # first dated export. They do not reconstruct historical power changes.
            transitions = set()
            for rows in gd.values():
                for r in rows:
                    transitions.update(day(r[f]) for f in ("DTA_SOL_ACES_KCG", "DTA_FIM_VIGN_KCG") if day(r[f]))
            for rows in pairs.values():
                transitions.update(day(r["DTA_INC_XBG"]) for r in rows if day(r["DTA_INC_XBG"]))
            for transition in sorted(t for t in transitions if BASELINE_DATE < t < dt):
                tlinks = enrich_links(link_states(pairs, transition, batch["BEN"].name, dt), gd, transition)
                tstates = make_states(scope, gd, tlinks, transition, dt, batch["GD"].name, batch["BEN"].name)
                preserve_unconfirmed_baseline(tstates, baseline, gd, pairs, transition)
                generated = compare_gd(previous_states, tstates, source, previous_source)
                generated += compare_links(previous_links, tlinks, scope, transition, previous_observed, source, previous_source)
                for e in generated:
                    e["BASE_DATA"] = "Reconstrução por data cadastrada"
                    e["STATUS_QUALIDADE"] = (e["STATUS_QUALIDADE"] + ";HISTORICO_RECONSTRUIDO").strip(";")
                    e["OBSERVACAO_ATUAL"] = dt
                    e["OBSERVACAO_ANTERIOR"] = ""
                    e["DETALHE"] += " Reconstruído do primeiro export; potência/classificação anteriores não comprovadas."
                events += generated
                states_by_date[transition] = tstates
                previous_states, previous_links, previous_observed = tstates, tlinks, transition
        events += compare_gd(previous_states, current, source, previous_source)
        events += compare_links(previous_links, links, scope, dt, previous_observed, source, previous_source)
        states_by_date[dt] = current
        previous_states, previous_links = current, links
        previous_observed, previous_source = dt, source
        all_links = list(links.values())
        for row in current.values():
            if row["REVISAO_MANUAL"] == "S":
                quality.append(issue(row["NUM_UC"], "GD_REVISAO_MANUAL", row["STATUS_QUALIDADE"], source, dt))
    latest_date = max(complete)
    latest_batch = complete[latest_date]
    uc_data = defaultdict(set)
    for line, r in csv_rows(latest_batch["UC"], GD_COLUMNS["UC"]):
        if r["ISN_UC"] in scope:
            uc_data[r["ISN_UC"]].add(r["TIPO_SIT_UC"])
    for uc, row in states_by_date[latest_date].items():
        statuses = uc_data.get(uc, set())
        row["SITUACAO_UC_FONTE"] = next(iter(statuses)) if len(statuses) == 1 else ""
        row["DATA_FONTE_UC"] = latest_date
        row["ARQUIVO_UC"] = latest_batch["UC"].name
        if len(statuses) != 1:
            quality.append(issue(uc, "UC_REFERENCIA_AUSENTE_OU_CONFLITANTE", " | ".join(sorted(statuses)), latest_batch["UC"].name, latest_date))
    return states_by_date, events, all_links, audit, sources, latest_date


def stage_full_base(path, destination, bi, gd_columns):
    """Update BI-scope rows without dropping full-base rows or private columns."""
    workbook = source_workbook(path)
    worksheet = None
    header_row = None
    for sheet in workbook.worksheets:
        for row in sheet.iter_rows(max_row=20):
            if any(text(cell.value).upper() == "NUM_UC" for cell in row):
                worksheet, header_row = sheet, row[0].row
                break
        if worksheet is not None:
            break
    if worksheet is None:
        raise ValueError("NUM_UC não encontrado na base completa")
    headers = {text(cell.value).upper(): cell.column for cell in worksheet[header_row] if text(cell.value)}
    additions = [c for c in gd_columns if c not in headers]
    for column in additions:
        index = max(headers.values()) + 1
        worksheet.cell(header_row, index, column)
        headers[column] = index
    current = {text(row["NUM_UC"]): row for row in bi.to_dict("records")}
    matched = set()
    changed = 0
    for row_number in range(header_row + 1, worksheet.max_row + 1):
        uc = identifier(worksheet.cell(row_number, headers["NUM_UC"]).value)
        if uc not in current:
            continue
        if uc in matched:
            raise ValueError(f"UC duplicada na base completa: {uc}")
        matched.add(uc)
        allowed = set(legacy.TARGET_NORMALIZERS) | set(legacy.MOBIFLEX_TARGET_COLUMNS) | set(gd_columns)
        for field, value in current[uc].items():
            if field not in headers or field not in allowed or field == "NUM_UC":
                continue
            cell = worksheet.cell(row_number, headers[field])
            if field.startswith("POTENCIA_") and text(value):
                value = float(value)
            if isinstance(cell.value, (date, datetime)):
                old = cell.value.date() if isinstance(cell.value, datetime) else cell.value
                old = old.isoformat()
            else:
                old = text(cell.value)
            if field.startswith("POTENCIA_") and number(old) == number(value):
                continue
            if old != text(value):
                cell.value = value if text(value) else None
                changed += 1
    missing = set(current) - matched
    if missing:
        raise ValueError(f"UCs BI ausentes na base completa: {sorted(missing)}")
    if additions:
        from openpyxl.worksheet.table import TableColumn
        for table in worksheet.tables.values():
            if table.ref.startswith(f"A{header_row}:"):
                table.ref = f"A{header_row}:{get_column_letter(max(headers.values()))}{worksheet.max_row}"
                table.tableColumns = [TableColumn(id=i, name=text(worksheet.cell(header_row, i).value))
                                      for i in range(1, max(headers.values()) + 1)]
                if table.autoFilter:
                    table.autoFilter.ref = table.ref
    workbook.save(destination)
    workbook.close()
    return changed, len(matched)


def stage_report(stage, reference):
    import zipfile
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    workbook = Workbook()
    workbook.remove(workbook.active)
    tables = {"GD_Atual": "gd_atual.csv", "Vinculos": "gd_vinculos.csv", "Historico_2026": "gd_historico_2026.csv",
              "Auditoria_Baseline": "gd_auditoria_baseline.csv", "Qualidade": "gd_qualidade.csv"}
    for sheet_name, filename in tables.items():
        sheet = workbook.create_sheet(sheet_name)
        with (stage / filename).open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            headers = reader.fieldnames
            sheet.append(headers)
            for row in reader:
                sheet.append([float(row[key]) if row[key] and (key.startswith("POTENCIA_") or key in {"QUANTIDADE_GERADORES_EXTERNOS", "BENEFICIARIAS_EXTERNAS", "PERCENTUAL_RATEIO"}) else row[key] for key in headers])
                for cell in sheet[sheet.max_row]:
                    if isinstance(cell.value, str):
                        cell.data_type = "s"
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="F5821E")
        for column in sheet.columns:
            sheet.column_dimensions[column[0].column_letter].width = min(60, max(12, max(len(text(cell.value)) for cell in column[:100]) + 2))
    methodology = workbook.create_sheet("Metodologia")
    for row in [("Regra", "Descrição"), ("Referência", reference),
                ("Escopo", "População atual do BI; vínculos externos somente como contexto."),
                ("Início geradora", "DTA_SOL_ACES_KCG conforme regra aprovada; não certifica comissionamento."),
                ("Início beneficiária", "DTA_INC_XBG conforme regra aprovada."),
                ("Potência", "kW; maior valor conflitante com flag de revisão. Não somar potência associada entre beneficiárias."),
                ("Baseline", "Amostra final 21/07 auditada contra primeiro export; classificação/potência retrospectivas sem vigência histórica própria."),
                ("Ausências", "Não comprovam encerramento. Autorrelacionamento somente quando registrado."),
                ("Histórico", "Datas cadastradas, primeira observação e reconstruções identificadas separadamente."),
                ("Privacidade", "Sem nomes, documentos, telefone, email, medidor ou identificador de cliente.")]:
        methodology.append(row)
    report = stage / "Relatorio_GD_Atual.xlsx"
    workbook.save(report)
    with zipfile.ZipFile(report) as archive:
        contents = {name: archive.read(name) for name in archive.namelist()}
    core = contents["docProps/core.xml"].decode("utf-8")
    contents["docProps/core.xml"] = re.sub(r"(<dcterms:(?:created|modified)[^>]*>)[^<]+", lambda m: m[1] + reference + "T00:00:00Z", core).encode("utf-8")
    with zipfile.ZipFile(report, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in sorted(contents.items()):
            entry = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, value)
    return report


def run(copel=COPEL, bi_dir=ROOT, baseline_path=None, full_base=None, dry_run=False, report=None, mobiflex=None):
    copel, bi_dir = Path(copel), Path(bi_dir)
    cadastro = copel / "Cadastro"
    data_dir = bi_dir / "data"
    base_file = bi_dir / "base_consolidada_BI.csv"
    full_base = Path(full_base or copel / "base_consolidada_copel.xlsx")
    baseline_path = Path(baseline_path or copel / "Relatórios-Indicadores" / "Amostra Final - Tarifa Mobiflex - 21.07.2026.xlsx")
    base = pd.read_csv(base_file, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    scope = set(base["NUM_UC"].map(text))
    if "" in scope or len(scope) != len(base):
        raise ValueError("UCs vazias/duplicadas no BI")
    excluded_file = cadastro / "gd_report_exclusions.json"
    exclusions = set(json.loads(excluded_file.read_text(encoding="utf-8"))["excluded_ucs"]) if excluded_file.exists() else set()
    if scope & exclusions:
        raise ValueError(f"UCs excluídas presentes na população BI: {sorted(scope & exclusions)}")
    batches = discover(cadastro / "DADOS_GD_GERAL")
    baseline = read_baseline(baseline_path, scope)
    quality = []
    states, gd_events, links, audit, manifest, gd_date = build_gd(batches, scope, baseline, baseline_path, quality)
    # Cadastro is preferred; BI data/ files supplement dates not present there.
    paths = {p.name: p for p in sorted(data_dir.glob("mdm-sandbox_clientes*.csv"))}
    paths.update({p.name: p for p in sorted(cadastro.glob("mdm-sandbox_clientes*.csv"))})
    if report:
        paths[Path(report).name] = Path(report)
    mdm_current, mdm_events, mdm_dates = mdm_history(list(paths.values()), scope, quality)
    if not mdm_dates:
        raise ValueError("Nenhuma fonte MDM datada disponível")
    detailed_dates = {p: dt for p, dt in mdm_dates.items() if not p.name.endswith("-ucs_sem_dados.csv")}
    if not detailed_dates:
        raise ValueError("Nenhuma fonte MDM com detalhes disponível")
    mdm_date_latest = max(detailed_dates.values())
    latest_mdm = max(detailed_dates, key=lambda p: (detailed_dates[p], p.name))
    for index, row in base.iterrows():
        uc = row["NUM_UC"]
        for field, value in mdm_current.get(uc, {}).items():
            base.at[index, field] = value
        title = text(base.at[index, "DT_MUD_TIT"])
        base.at[index, "MUD_TIT"] = "S" if title and title >= "2026-03-01" else ""
    # Existing, explicitly corrected removal list has priority over old reports.
    if mobiflex:
        removal = Path(mobiflex)
    elif (data_dir / "relatorio_ucs_removidas.xlsx").exists():
        removal = data_dir / "relatorio_ucs_removidas.xlsx"
    else:
        removal = legacy.newest_mobiflex_report()
    # Legacy removal helper writes a review file; stage that too.
    stage = data_dir / "backups" / "pipeline-staging"
    stage.mkdir(parents=True, exist_ok=True)
    old_review = legacy.REMOVAL_REVIEW_FILE
    legacy.REMOVAL_REVIEW_FILE = stage / "remocoes_pendentes_confirmacao.csv"
    try:
        removal_counts = legacy.update_from_mobiflex(base, {uc: index for index, uc in base["NUM_UC"].items()}, removal, set())
    finally:
        legacy.REMOVAL_REVIEW_FILE = old_review
    latest_gd = states[gd_date]
    gd_columns = list(next(iter(latest_gd.values())))
    for index, row in base.iterrows():
        uc = row["NUM_UC"]
        gd = latest_gd[uc]
        # Direct GD dates/classification override lower-quality MDM fields.
        for field, value in gd.items():
            if field != "NUM_UC":
                base.at[index, field] = text(value)
        base.at[index, "POSSUI_GD_CLIENTE"] = gd["GD_GERADORA"]
        # Ending a beneficiary relationship cannot be inferred from absence.
        # Preserve explicitly dated MDM end dates as historical context.
    group_map = dict(zip(base["NUM_UC"], base["SITUACAO_INICIAL"].map(legacy.group_label)))
    events = mdm_events + gd_events
    for e in events:
        e["GRUPO_UC"] = group_map[e["NUM_UC"]]
    history = [e for e in events if "2026-01-01" <= e["DATA_ALERTA"] <= "2026-12-31"]
    history = sorted({e["ID_EVENTO"]: e for e in history}.values(), key=lambda e: (e["DATA_ALERTA"], e["NUM_UC"], e["CAMPO"], e["ID_EVENTO"]))
    latest = [e for e in history if (e["OBSERVACAO_ATUAL"] == gd_date and e["TIPO_ALERTA"] == "Alteração GD")
              or (e["OBSERVACAO_ATUAL"] == mdm_date_latest and e["TIPO_ALERTA"] != "Alteração GD")]
    latest_uc_ids = {r["uc"] for line, r in csv_rows(latest_mdm, {"uc"})}
    for uc in sorted(scope):
        current = mdm_current.get(uc, {})
        for field, expected in (("CLASSE", "B1"), ("GRUPO", "1")):
            if field in current and current[field] != expected:
                latest.append(event(uc, field, current[field], current[field], mdm_date_latest,
                    source=latest_mdm.name, kind="Fora do padrão", nature="Condição persistente",
                    detail=f"Valor esperado: {expected}. Não representa uma nova mudança."))
        if uc not in latest_uc_ids:
            latest.append(event(uc, "PRESENCA_NO_RELATORIO", "", "Não observado", mdm_date_latest,
                source=latest_mdm.name, kind="Sem atualização", nature="Condição persistente",
                detail="Ausência no último relatório MDM; não indica exclusão."))
    for e in latest:
        e["GRUPO_UC"] = group_map[e["NUM_UC"]]
    for source in sorted(mdm_dates, key=lambda p: (mdm_dates[p], p.name)):
        manifest.append(dict(arquivo=source.name, data=mdm_dates[source], tipo="MDM", sha256=digest(source), status="INCLUIDO"))
    manifest.append(dict(arquivo=baseline_path.name, data=BASELINE_DATE, tipo="AMOSTRA", sha256=digest(baseline_path), status="AUDITORIA"))
    if excluded_file.exists():
        manifest.append(dict(arquivo=excluded_file.name, data="", tipo="EXCLUSOES", sha256=digest(excluded_file), status="APLICADO"))
    summary = dict(arquivo_origem=latest_mdm.name, periodo_inicio=mdm_date_latest.replace("-", ""),
        periodo_fim=mdm_date_latest.replace("-", ""), data_gd=gd_date,
        data_ultimo_arquivo_gd=max(batches), lote_gd_incompleto=max(batches) != gd_date,
        total_base=len(scope), eventos_historicos=len(history), alertas=len(latest),
        eventos_gd_2026=sum(e["TIPO_ALERTA"] == "Alteração GD" for e in history),
        ucs_revisao_gd=sum(r["REVISAO_MANUAL"] == "S" for r in latest_gd.values()),
        divergencias_baseline=sum(r["STATUS"] in {"CORRIGIDO_PELA_FONTE_GD", "DIVERGENCIA_REVISAR", "REVISAR_FONTE_NAO_CONFIRMADA_OU_CONFLITANTE", "AUSENTE_AMOSTRA"} for r in audit),
        ucs_corrigidas_baseline=len({r["NUM_UC"] for r in audit if r["STATUS"] == "CORRIGIDO_PELA_FONTE_GD"}),
        ucs_revisao_baseline=len({r["NUM_UC"] for r in audit if r["STATUS"] in {"DIVERGENCIA_REVISAR", "REVISAR_FONTE_NAO_CONFIRMADA_OU_CONFLITANTE", "AUSENTE_AMOSTRA"}}),
        campos_complementados_baseline=sum(r["STATUS"] == "COMPLEMENTADO_PELA_FONTE_GD" for r in audit),
        campos_sem_informacao_amostra=sum(r["STATUS"] == "SEM_INFORMACAO_NA_AMOSTRA" for r in audit),
        arquivo_baseline=baseline_path.name, arquivo_mobiflex=removal.name,
        ucs_sem_atualizacao=len(scope - latest_uc_ids), unidade_potencia="kW",
        regra_inicio_geradora="DTA_SOL_ACES_KCG", regra_inicio_beneficiaria="DTA_INC_XBG",
        fontes=manifest, historico_inicio="2026-01-01", experimento_inicio="2026-03-01",
        regra_ausencia="Ausência não comprova encerramento; nenhuma exclusão automática.",
        baseline_limite="Classificação/potência retrospectivas conforme primeiro export GD; sem histórico de vigência destes campos.")
    # Publish a strict column allowlist inherited from the existing public base
    # plus the reviewed GD schema. Never copy source customer/name/meter columns.
    forbidden = {"NOME", "NOM_COMP_GERADOR", "NOM_COMP_BENEFIC", "CLIENTE", "NUM_CLI_UC", "CELULAR", "EMAIL", "MEDIDOR", "CPF", "CNPJ", "NUM_DOC_GERADOR", "NUM_DOC_BENEFIC"}
    if forbidden & {column.upper() for column in base.columns}:
        raise ValueError("Colunas pessoais detectadas no BI")
    base = base.astype("string").fillna("")
    write_rows(stage / "base_consolidada_BI.csv", base.to_dict("records"), list(base.columns))
    write_rows(stage / "gd_atual.csv", latest_gd.values(), gd_columns)
    write_rows(stage / "gd_snapshots.csv", (r for batch in states.values() for r in batch.values()), gd_columns)
    link_columns = ["UC_GERADORA", "UC_BENEFICIARIA", "POTENCIA_GERADOR_KW", "TIPO_GD_GERADOR", "PERCENTUAL_RATEIO", "PRIORIDADE", "DATA_INICIO", "DATA_INICIO_VIGENCIA", "MODALIDADE", "STATUS_QUALIDADE", "DATA_FONTE", "ARQUIVO_ORIGEM", "STATUS_VINCULO", "AUTO_RELACAO"]
    write_rows(stage / "gd_vinculos.csv", links, link_columns)
    write_rows(stage / "gd_historico_2026.csv", (e for e in history if e["TIPO_ALERTA"] == "Alteração GD"), ALERT_COLUMNS)
    write_rows(stage / "historico_alertas.csv", history, ALERT_COLUMNS)
    write_rows(stage / "ultima_atualizacao_alertas.csv", latest, ALERT_COLUMNS)
    write_rows(stage / "gd_qualidade.csv", quality, ["NUM_UC", "TIPO", "DETALHE", "ARQUIVO_ORIGEM", "DATA_FONTE"])
    write_rows(stage / "gd_auditoria_baseline.csv", audit, ["NUM_UC", "CAMPO", "VALOR_AMOSTRA", "VALOR_RECONSTRUIDO", "STATUS", "DATA_REFERENCIA", "DATA_FONTE_GD", "ARQUIVO_AMOSTRA", "LIMITACAO", "ABA_AMOSTRA", "LINHA_AMOSTRA", "COLUNA_AMOSTRA", "VALOR_AMOSTRA_ORIGINAL", "NOTA_AMOSTRA"])
    changed_cells, matched_full = stage_full_base(full_base, stage / full_base.name, base, gd_columns)
    summary.update(celulas_alteradas_base_completa=changed_cells, ucs_base_completa_atualizadas=matched_full)
    for filename in ("gd_manifesto.json", "ultima_atualizacao_resumo.json"):
        (stage / filename).write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_file = stage_report(stage, gd_date)
    # Verify scope and totals before publishing anything.
    assert set(base["NUM_UC"]) == scope
    for row in latest_gd.values():
        if row["POTENCIA_INSTALADA_KW"]:
            assert sum((number(row[f]) or ZERO for f in ("POTENCIA_GDI_KW", "POTENCIA_GDII_KW", "POTENCIA_OUTROS_KW", "POTENCIA_SEM_CLASSIFICACAO_KW")), ZERO) == number(row["POTENCIA_INSTALADA_KW"])
    destinations = {stage / "base_consolidada_BI.csv": base_file,
                    stage / full_base.name: full_base,
                    report_file: cadastro / "gd_report_atual" / report_file.name}
    for name in ("gd_atual.csv", "gd_vinculos.csv", "gd_historico_2026.csv", "gd_auditoria_baseline.csv", "gd_qualidade.csv", "gd_manifesto.json"):
        copied = stage / ("cadastro_" + name)
        shutil.copy2(stage / name, copied)
        destinations[copied] = cadastro / "gd_report_atual" / name
    for path in stage.iterdir():
        if path.suffix in {".csv", ".json"} and path.name != "base_consolidada_BI.csv" and not path.name.startswith("cadastro_"):
            destinations[path] = data_dir / path.name
    changed = {src: dst for src, dst in destinations.items() if not dst.exists() or digest(src) != digest(dst)}
    # Workbook ZIP metadata may vary even when no cells changed.
    if changed_cells == 0:
        changed.pop(stage / full_base.name, None)
    summary["arquivos_a_atualizar"] = [str(dst.relative_to(copel)) for dst in changed.values()]
    if not dry_run:
        backup = data_dir / "backups" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup.mkdir(parents=True)
        promoted = []
        saved = {}
        try:
            for index, (src, dst) in enumerate(changed.items()):
                if dst.exists():
                    saved[dst] = backup / f"{index}-{dst.name}"
                    shutil.copy2(dst, saved[dst])
            for src, dst in changed.items():
                # Move is only within this project's validated output paths.
                dst.parent.mkdir(parents=True, exist_ok=True)
                src.replace(dst)
                promoted.append(dst)
        except Exception:
            for dst in reversed(promoted):
                if dst in saved:
                    shutil.copy2(saved[dst], dst)
                else:
                    dst.unlink(missing_ok=True)
            raise
    print(json.dumps({k: v for k, v in summary.items() if k != "fontes"}, ensure_ascii=False, indent=2), flush=True)
    print("VALIDAÇÃO CONCLUÍDA; arquivos preparados em data/backups/pipeline-staging" if dry_run else "ATUALIZAÇÃO CONCLUÍDA; backup em data/backups", flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description="Atualiza Cadastro/GD, BI e base completa com histórico 2026.")
    parser.add_argument("--copel-dir", type=Path, default=COPEL)
    parser.add_argument("--bi-dir", type=Path, default=ROOT)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--base", type=Path, help="Base completa Excel")
    parser.add_argument("--input", type=Path, help="MDM adicional; histórico Cadastro continua incluído")
    parser.add_argument("--mobiflex-input", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="Compatibilidade: toda execução revalida as fontes")
    args = parser.parse_args()
    try:
        run(args.copel_dir, args.bi_dir, args.baseline, args.base, args.dry_run, args.input, args.mobiflex_input)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Erro: {exc}\nNenhuma base foi substituída antes da validação das fontes.\n")


if __name__ == "__main__":
    main()

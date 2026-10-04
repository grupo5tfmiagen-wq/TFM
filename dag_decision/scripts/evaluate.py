"""Evaluacion de la calidad de las decisiones del motor.

Lanza el pipeline completo, con el LLM real, sobre un conjunto de CV cuya
decision correcta se conoce de antemano (``data/eval_labels.csv``), repite
la ejecucion varias veces para medir la consistencia y calcula los
indicadores de la tabla 6.4, ademas de analisis complementarios (acierto
del LLM, errores criticos, inyeccion de instrucciones y pares de sesgo).

Uso (desde ``dag_decision/``, con el venv activo y Docker levantado):

    # 1) Ensayo sin coste, con un LLM simulado (comprueba que todo funciona)
    python scripts/evaluate.py --simulado --pasadas 1 --base-datos dag_eval_prueba

    # 2) Evaluacion real (requiere OPENAI_API_KEY en .env)
    python scripts/evaluate.py --pasadas 5 --base-datos dag_eval

``--base-datos`` hace que la evaluacion se ejecute en una base de datos
PostgreSQL aparte (la crea y la prepara si no existe), para no llenar la
cola de revision de la demo con los casos escalados de la evaluacion. Si se
omite, se usa la base de datos de ``DATABASE_URL``.

Salidas (en ``--salida``, por defecto ``eval_resultados/<fecha>``):
    casos.csv     una fila por caso y pasada
    resumen.md    tabla 6.4 rellena y analisis complementarios
    resumen.json  los mismos indicadores en formato maquina
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

ETIQUETAS_VALIDAS = {"apto", "no_apto", "descartado_reglas"}
NODOS_ESPERADOS = {
    "rechazo_reglas": ["rule_evaluator", "final_decision"],
    "aprobacion_automatica": ["rule_evaluator", "llm_decision", "validation", "final_decision"],
    "rechazo_automatico_llm": ["rule_evaluator", "llm_decision", "validation", "final_decision"],
    "escalado": ["rule_evaluator", "llm_decision", "validation", "human_escalation"],
}


# ---------------------------------------------------------------------------
# Preparacion de la base de datos de evaluacion
# ---------------------------------------------------------------------------


def _with_database(url: str, database: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "/" + database, parts.query, parts.fragment))


def preparar_base_datos(nombre: str) -> None:
    """Apunta DATABASE_URL y CHECKPOINTER_DATABASE_URL a ``nombre``, la crea si
    no existe, aplica las migraciones de Alembic y crea las tablas de checkpoint.

    Debe llamarse ANTES de importar ``src.*``, porque esos modulos leen las
    URL de conexion al importarse.
    """
    import psycopg

    base_url = os.environ["DATABASE_URL"]
    cp_url = os.environ["CHECKPOINTER_DATABASE_URL"]
    os.environ["DATABASE_URL"] = _with_database(base_url, nombre)
    os.environ["CHECKPOINTER_DATABASE_URL"] = _with_database(cp_url, nombre)

    try:
        conn = psycopg.connect(_with_database(cp_url, "postgres"), autocommit=True, connect_timeout=5)
    except psycopg.OperationalError as exc:
        sys.exit(f"No se puede conectar con PostgreSQL ({exc}).\n¿Esta levantado? Ejecuta: docker compose up -d")
    with conn:
        existe = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (nombre,)).fetchone()
        if not existe:
            conn.execute(f'CREATE DATABASE "{nombre}"')
            print(f"Base de datos creada: {nombre}")

    from alembic import command
    from alembic.config import Config

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "CargaInicial"))
    command.upgrade(cfg, "head")

    from src.db.checkpointer import setup_checkpointer

    setup_checkpointer()
    print(f"Base de datos de evaluacion lista: {nombre}")


# ---------------------------------------------------------------------------
# LLM simulado (solo para ensayos; sus resultados NO son validos)
# ---------------------------------------------------------------------------


class _LLMSimulado:
    """Devuelve valoraciones pseudoaleatorias deterministas a partir del prompt
    y de la pasada, para recorrer todas las ramas del grafo sin coste."""

    pasada = 1

    def with_structured_output(self, schema, include_raw=False):
        self._schema = schema
        return self

    def invoke(self, prompt):
        digest = hashlib.sha256(f"{prompt}|{self.pasada}".encode()).digest()
        etiqueta = ("fit", "fit", "not_fit", "unclear")[digest[0] % 4]
        confianza = round(0.55 + (digest[1] / 255) * 0.44, 2)
        tokens_in = 600 + digest[2] * 4
        assessment = self._schema(fit_label=etiqueta, confidence=confianza, justification="Valoracion simulada.")
        uso = {"input_tokens": tokens_in, "output_tokens": 90, "total_tokens": tokens_in + 90}
        return {"parsed": assessment, "raw": SimpleNamespace(usage_metadata=uso)}


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def leer_etiquetas(path: Path) -> dict[str, dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        filas = list(csv.DictReader(fh, delimiter=";"))
    etiquetas = {}
    for fila in filas:
        cid = (fila.get("candidate_id") or "").strip()
        etiqueta = (fila.get("etiqueta") or "").strip()
        if not cid:
            continue
        if etiqueta not in ETIQUETAS_VALIDAS:
            raise ValueError(f"Etiqueta no valida para {cid}: {etiqueta!r} (validas: {sorted(ETIQUETAS_VALIDAS)})")
        etiquetas[cid] = {**fila, "candidate_id": cid, "etiqueta": etiqueta}
    if not etiquetas:
        raise ValueError(f"No hay etiquetas en {path}")
    return etiquetas


def ruta_del_caso(result: dict, pausado: bool) -> str:
    if pausado:
        return "escalado"
    outcome = result.get("outcome")
    if outcome == "rejected":
        return "rechazo_reglas"
    if outcome == "fit":
        return "aprobacion_automatica"
    if outcome == "not_fit":
        return "rechazo_automatico_llm"
    return f"otro:{outcome}"


def pct(num: float, den: float) -> float | None:
    return round(100 * num / den, 1) if den else None


def mediana(valores):
    return round(statistics.median(valores), 2) if valores else None


def p95(valores):
    if not valores:
        return None
    ordenados = sorted(valores)
    return round(ordenados[max(0, int(round(0.95 * len(ordenados))) - 1)], 2)


def fmt(valor, sufijo="", dec=1):
    """Numero con coma decimal y ``dec`` decimales; "—" si no hay dato."""
    if valor is None:
        return "—"
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        texto = f"{valor:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return texto + sufijo
    return f"{valor}{sufijo}"


# ---------------------------------------------------------------------------
# Ejecucion
# ---------------------------------------------------------------------------


def ejecutar(args) -> None:
    if args.base_datos:
        preparar_base_datos(args.base_datos)

    # Importaciones diferidas: dependen de las URL de conexion ya ajustadas.
    from scripts.load_demo_data import seed_demo_data
    from src.db.base import SessionLocal
    from src.db.models import CVDocument, JobPosting
    from src.db.models.case import Case
    from src.db.models.final_decision import FinalDecision
    from src.db.models.human_escalation import HumanEscalation
    from src.db.models.node_execution import CaseNodeExecution
    from src.graph import nodes
    from src.ui_support import graph_runner

    if args.simulado:
        llm_simulado = _LLMSimulado()
        nodes._llm = lambda: llm_simulado
    elif not os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY", "").startswith("sk-..."):
        sys.exit("Falta OPENAI_API_KEY en el .env. Para un ensayo sin coste usa --simulado.")

    etiquetas = leer_etiquetas(Path(args.etiquetas))
    catalogo_path = Path(args.catalogo)
    if not args.no_cargar:
        print("Carga del catalogo:", seed_demo_data(catalogo_path))
    catalogo = json.loads(catalogo_path.read_text(encoding="utf-8"))
    oferta_ext = args.oferta or catalogo["job_postings"][0]["external_id"]

    with SessionLocal() as session:
        job = session.query(JobPosting).filter(JobPosting.external_id == oferta_ext).one_or_none()
        if job is None:
            sys.exit(f"No existe la oferta {oferta_ext!r} en la base de datos.")
        job_id = str(job.id)
        cvs = {
            cv.candidate_id: str(cv.id)
            for cv in session.query(CVDocument).filter(CVDocument.candidate_id.in_(list(etiquetas))).all()
        }
    faltan = sorted(set(etiquetas) - set(cvs))
    if faltan:
        sys.exit(f"Estos CV del fichero de etiquetas no estan en la base de datos: {faltan}")

    modelo = "SIMULADO" if args.simulado else os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    print(f"Modelo: {modelo} · umbral de confianza: {nodes.CONFIDENCE_THRESHOLD} · "
          f"{len(etiquetas)} CV · {args.pasadas} pasada(s) · oferta {oferta_ext}")

    filas: list[dict] = []
    total = len(etiquetas) * args.pasadas
    hechos = 0
    for pasada in range(1, args.pasadas + 1):
        if args.simulado:
            llm_simulado.pasada = pasada
        for cid in sorted(etiquetas):
            hechos += 1
            etiqueta = etiquetas[cid]
            fila = {"pasada": pasada, "candidate_id": cid, "etiqueta": etiqueta["etiqueta"],
                    "categoria": etiqueta.get("categoria", ""), "ruta_esperada": etiqueta.get("ruta_esperada", "")}
            inicio = time.perf_counter()
            try:
                res = graph_runner.start_case(cvs[cid], job_id)
            except Exception as exc:  # se registra y se continua con el siguiente caso
                fila.update({"error": f"{type(exc).__name__}: {exc}", "segundos": round(time.perf_counter() - inicio, 3)})
                filas.append(fila)
                print(f"[{hechos}/{total}] {cid}: ERROR {exc}")
                continue
            segundos = time.perf_counter() - inicio
            result = res["result"]
            pausado = res["interrupt"] is not None
            llm = result.get("llm_decision") or {}
            regla = result.get("rule_result") or {}
            ruta = ruta_del_caso(result, pausado)
            fila.update({
                "case_id": res["case_id"], "ruta": ruta, "outcome": result.get("outcome") or "",
                "reglas_superadas": regla.get("passed"),
                "requisitos_no_verificables": len(regla.get("unverified_requirements") or []),
                "fit_label": llm.get("fit_label", ""), "confianza": llm.get("confidence"),
                "input_tokens": llm.get("input_tokens"), "output_tokens": llm.get("output_tokens"),
                "total_tokens": llm.get("total_tokens"), "coste_usd": llm.get("estimated_cost_usd"),
                "segundos": round(segundos, 3), "error": "",
            })
            filas.append(fila)
            print(f"[{hechos}/{total}] {cid}: {ruta} ({llm.get('fit_label', '-')}, {llm.get('confidence', '-')})")

    # --- Trazabilidad y latencia del LLM, leidas de la auditoria en BD ---
    with SessionLocal() as session:
        for fila in filas:
            if not fila.get("case_id"):
                fila["trazable"] = False
                continue
            ejecuciones = session.query(CaseNodeExecution).filter_by(case_id=fila["case_id"]).all()
            por_nodo = {e.node_key: e for e in ejecuciones}
            esperados = NODOS_ESPERADOS.get(fila["ruta"], [])
            ok = bool(esperados) and all(k in por_nodo for k in esperados)
            for clave in esperados:
                ejecucion = por_nodo.get(clave)
                if ejecucion is None:
                    continue
                estado_ok = ejecucion.status == ("waiting" if clave == "human_escalation" else "completed")
                ok = ok and estado_ok and ejecucion.started_at is not None
                if clave != "human_escalation":
                    ok = ok and ejecucion.finished_at is not None
            if fila["ruta"] == "rechazo_reglas":
                ok = ok and bool(por_nodo["rule_evaluator"].rule_evaluations) if "rule_evaluator" in por_nodo else False
            if "llm_decision" in esperados and "llm_decision" in por_nodo:
                ok = ok and bool(por_nodo["llm_decision"].llm_decisions)
                e = por_nodo["llm_decision"]
                if e.started_at and e.finished_at:
                    fila["latencia_llm_s"] = round((e.finished_at - e.started_at).total_seconds(), 3)
            if fila["ruta"] == "escalado":
                ok = ok and session.query(HumanEscalation).filter_by(case_id=fila["case_id"], status="pending").count() == 1
            else:
                ok = ok and session.query(FinalDecision).filter_by(case_id=fila["case_id"]).count() == 1
                caso = session.get(Case, fila["case_id"])
                ok = ok and caso is not None and caso.status == "closed"
            fila["trazable"] = ok

    salida = Path(args.salida or (ROOT / "eval_resultados" / datetime.now().strftime("%Y%m%d_%H%M")))
    salida.mkdir(parents=True, exist_ok=True)
    escribir_casos(filas, salida / "casos.csv")
    indicadores = calcular_indicadores(filas, args, modelo, nodes.CONFIDENCE_THRESHOLD, oferta_ext)
    (salida / "resumen.json").write_text(json.dumps(indicadores, ensure_ascii=False, indent=2), encoding="utf-8")
    (salida / "resumen.md").write_text(informe_markdown(indicadores), encoding="utf-8")
    print(f"\nResultados en {salida}")
    print(informe_markdown(indicadores).split("## 2.")[0])


def escribir_casos(filas: list[dict], path: Path) -> None:
    campos = ["pasada", "candidate_id", "etiqueta", "categoria", "ruta_esperada", "ruta", "outcome",
              "reglas_superadas", "requisitos_no_verificables", "fit_label", "confianza", "input_tokens",
              "output_tokens", "total_tokens", "coste_usd", "segundos", "latencia_llm_s", "trazable", "case_id", "error"]
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=campos, delimiter=";", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(filas)


# ---------------------------------------------------------------------------
# Indicadores
# ---------------------------------------------------------------------------


def calcular_indicadores(filas, args, modelo, umbral, oferta) -> dict:
    validas = [f for f in filas if not f.get("error")]
    p1 = [f for f in validas if f["pasada"] == 1]
    n = len(p1)

    automaticas = [f for f in p1 if f["ruta"] in ("aprobacion_automatica", "rechazo_reglas", "rechazo_automatico_llm")]
    aprobaciones = [f for f in p1 if f["ruta"] == "aprobacion_automatica"]
    rechazos_reglas = [f for f in p1 if f["ruta"] == "rechazo_reglas"]
    escalados = [f for f in p1 if f["ruta"] == "escalado"]
    evaluados_llm = [f for f in p1 if f.get("fit_label")]

    def correcta(f):
        return (f["ruta"] == "aprobacion_automatica" and f["etiqueta"] == "apto") or (
            f["ruta"] == "rechazo_reglas" and f["etiqueta"] == "descartado_reglas") or (
            f["ruta"] == "rechazo_automatico_llm" and f["etiqueta"] == "no_apto")

    def acierto_llm(f):
        return (f["fit_label"] == "fit" and f["etiqueta"] == "apto") or (f["fit_label"] == "not_fit" and f["etiqueta"] == "no_apto")

    # Consistencia entre pasadas
    por_cv = defaultdict(list)
    for f in validas:
        por_cv[f["candidate_id"]].append(f)
    completos = {cid: fs for cid, fs in por_cv.items() if len(fs) == args.pasadas}
    con_llm = {cid: fs for cid, fs in completos.items() if all(f.get("fit_label") for f in fs)}
    misma_etiqueta = sum(1 for fs in con_llm.values() if len({f["fit_label"] for f in fs}) == 1)
    misma_ruta = sum(1 for fs in completos.values() if len({f["ruta"] for f in fs}) == 1)
    desv_conf = [statistics.pstdev([float(f["confianza"]) for f in fs]) for fs in con_llm.values() if args.pasadas > 1]

    llamadas = [f for f in validas if f.get("fit_label")]
    tokens = [f["total_tokens"] for f in llamadas if f.get("total_tokens") is not None]
    costes = [f["coste_usd"] for f in llamadas if f.get("coste_usd") is not None]
    latencias = [f["latencia_llm_s"] for f in validas if f.get("latencia_llm_s") is not None]
    t_auto = [f["segundos"] for f in validas if f["ruta"] in ("aprobacion_automatica", "rechazo_reglas")]
    t_aprob = [f["segundos"] for f in validas if f["ruta"] == "aprobacion_automatica"]
    t_reglas = [f["segundos"] for f in validas if f["ruta"] == "rechazo_reglas"]

    # Matriz etiqueta x propuesta del LLM (pasada 1)
    matriz = Counter((f["etiqueta"], f["fit_label"]) for f in evaluados_llm)

    # Errores criticos: aprobaciones automaticas de casos que no son aptos
    criticos = [
        {"pasada": f["pasada"], "candidate_id": f["candidate_id"], "etiqueta": f["etiqueta"], "categoria": f["categoria"],
         "confianza": f["confianza"]}
        for f in validas if f["ruta"] == "aprobacion_automatica" and f["etiqueta"] != "apto"
    ]

    # Por categoria (pasada 1)
    categorias = defaultdict(lambda: Counter())
    for f in p1:
        c = categorias[f["categoria"] or "-"]
        c["casos"] += 1
        c[f["ruta"]] += 1
        if f.get("fit_label"):
            c["llm_evaluados"] += 1
            c["llm_aciertos"] += int(acierto_llm(f))

    # Pares de sesgo (todas las pasadas)
    pares = defaultdict(dict)
    for f in validas:
        cat = f["categoria"] or ""
        if cat.startswith("sesgo_par"):
            pares[(cat, f["pasada"])][f["candidate_id"]] = f
    resumen_pares = defaultdict(lambda: {"comparaciones": 0, "misma_etiqueta": 0, "misma_ruta": 0, "dif_confianza": []})
    for (cat, _), miembros in pares.items():
        if len(miembros) != 2:
            continue
        a, b = miembros.values()
        r = resumen_pares[cat]
        r["comparaciones"] += 1
        r["misma_etiqueta"] += int(a.get("fit_label") == b.get("fit_label"))
        r["misma_ruta"] += int(a["ruta"] == b["ruta"])
        if a.get("confianza") is not None and b.get("confianza") is not None:
            r["dif_confianza"].append(abs(float(a["confianza"]) - float(b["confianza"])))

    return {
        "fecha": datetime.now().isoformat(timespec="minutes"),
        "simulado": bool(args.simulado),
        "modelo": modelo,
        "umbral_confianza": umbral,
        "oferta": oferta,
        "pasadas": args.pasadas,
        "cv": n,
        "errores_ejecucion": len(filas) - len(validas),
        "tabla_6_4": {
            "precision_decision_automatica": pct(sum(correcta(f) for f in automaticas), len(automaticas)),
            "decisiones_automaticas": len(automaticas),
            "precision_aprobaciones_automaticas": pct(sum(correcta(f) for f in aprobaciones), len(aprobaciones)),
            "aprobaciones_automaticas": len(aprobaciones),
            "precision_rechazos_reglas": pct(sum(correcta(f) for f in rechazos_reglas), len(rechazos_reglas)),
            "rechazos_reglas": len(rechazos_reglas),
            "tasa_escalado": pct(len(escalados), n),
            "tasa_escalado_sobre_evaluados_llm": pct(len(escalados), len(evaluados_llm)),
            "tasa_filtrado_reglas": pct(len(rechazos_reglas), n),
            "confianza_media": pct(sum(float(f["confianza"]) for f in evaluados_llm), len(evaluados_llm)),
            "consistencia_etiqueta": pct(misma_etiqueta, len(con_llm)) if args.pasadas > 1 else None,
            "consistencia_ruta": pct(misma_ruta, len(completos)) if args.pasadas > 1 else None,
            "desviacion_media_confianza": round(statistics.mean(desv_conf), 3) if desv_conf else None,
            "trazabilidad": pct(sum(bool(f.get("trazable")) for f in validas), len(validas)),
            "tiempo_decision_automatica_mediana_s": mediana(t_auto),
            "tiempo_decision_automatica_p95_s": p95(t_auto),
            "tiempo_aprobacion_automatica_mediana_s": mediana(t_aprob),
            "tiempo_rechazo_reglas_mediana_s": mediana(t_reglas),
            "latencia_llm_mediana_s": mediana(latencias),
            "latencia_llm_p95_s": p95(latencias),
            "tokens_medios_por_llamada": round(statistics.mean(tokens)) if tokens else None,
            "coste_medio_por_llamada_usd": round(statistics.mean(costes), 6) if costes else None,
            "coste_total_usd": round(sum(costes), 4) if costes else None,
            "coste_por_candidatura_usd": round(sum(costes) / len(validas), 6) if costes and validas else None,
        },
        "acierto_propuesta_llm": pct(sum(acierto_llm(f) for f in evaluados_llm), len(evaluados_llm)),
        "matriz_etiqueta_llm": {f"{e}|{l}": c for (e, l), c in sorted(matriz.items())},
        "errores_criticos": criticos,
        "por_categoria": {k: dict(v) for k, v in sorted(categorias.items())},
        "pares_sesgo": {
            k: {"comparaciones": v["comparaciones"],
                "misma_etiqueta_pct": pct(v["misma_etiqueta"], v["comparaciones"]),
                "misma_ruta_pct": pct(v["misma_ruta"], v["comparaciones"]),
                "dif_confianza_media": round(statistics.mean(v["dif_confianza"]), 3) if v["dif_confianza"] else None}
            for k, v in sorted(resumen_pares.items())
        },
    }


def informe_markdown(ind: dict) -> str:
    t = ind["tabla_6_4"]
    lineas = []
    if ind["simulado"]:
        lineas += ["> **ENSAYO CON LLM SIMULADO. Estos resultados NO son válidos para la memoria.**", ""]
    lineas += [
        f"# Evaluación del motor de decisión — {ind['fecha']}",
        "",
        f"Modelo: **{ind['modelo']}** · umbral de confianza: **{ind['umbral_confianza']}** · oferta: `{ind['oferta']}` · "
        f"{ind['cv']} CV · {ind['pasadas']} pasada(s) · errores de ejecución: {ind['errores_ejecucion']}",
        "",
        "## 1. Tabla 6.4. Indicadores de calidad de las decisiones",
        "",
        "Salvo la consistencia, que compara todas las pasadas, los porcentajes se calculan sobre la primera pasada.",
        "",
        "| Indicador | Resultado |",
        "|---|---|",
        f"| Precisión de la decisión automática | {fmt(t['precision_decision_automatica'], ' %')} "
        f"({t['decisiones_automaticas']} decisiones: aprobaciones {fmt(t['precision_aprobaciones_automaticas'], ' %')} de {t['aprobaciones_automaticas']}; "
        f"rechazos por reglas {fmt(t['precision_rechazos_reglas'], ' %')} de {t['rechazos_reglas']}) |",
        f"| Tasa de escalado | {fmt(t['tasa_escalado'], ' %')} del total; {fmt(t['tasa_escalado_sobre_evaluados_llm'], ' %')} de los evaluados por el LLM |",
        f"| Tasa de filtrado por reglas | {fmt(t['tasa_filtrado_reglas'], ' %')} |",
        f"| Confianza media del LLM | {fmt(t['confianza_media'], ' %')} |",
        f"| Consistencia | {fmt(t['consistencia_etiqueta'], ' %')} misma etiqueta en todas las pasadas; "
        f"{fmt(t['consistencia_ruta'], ' %')} misma ruta; desviación media de la confianza {fmt(t['desviacion_media_confianza'], dec=3)} |",
        f"| Trazabilidad | {fmt(t['trazabilidad'], ' %')} de los casos con recorrido completo en la auditoría |",
        f"| Tiempo de decisión automática | mediana {fmt(t['tiempo_decision_automatica_mediana_s'], ' s', 2)}, p95 {fmt(t['tiempo_decision_automatica_p95_s'], ' s', 2)} "
        f"(aprobaciones {fmt(t['tiempo_aprobacion_automatica_mediana_s'], ' s', 2)}; rechazos por reglas {fmt(t['tiempo_rechazo_reglas_mediana_s'], ' s', 2)}) |",
        f"| Tokens y coste por caso | {fmt(t['tokens_medios_por_llamada'], dec=0)} tokens por llamada; {fmt(t['coste_medio_por_llamada_usd'], dec=6)} USD por llamada; "
        f"{fmt(t['coste_por_candidatura_usd'], dec=6)} USD por candidatura; total {fmt(t['coste_total_usd'], dec=4)} USD |",
        "",
        f"Latencia de la llamada al LLM (para la tabla 8.2): mediana {fmt(t['latencia_llm_mediana_s'], ' s', 2)}, p95 {fmt(t['latencia_llm_p95_s'], ' s', 2)}.",
        "",
        "## 2. Acierto de la propuesta del LLM",
        "",
        f"Acierto de la etiqueta propuesta por el LLM frente a la etiqueta de referencia (incluidos los casos escalados): "
        f"**{fmt(ind['acierto_propuesta_llm'], ' %')}**.",
        "",
        "| Etiqueta de referencia | fit | not_fit | unclear |",
        "|---|---|---|---|",
    ]
    m = ind["matriz_etiqueta_llm"]
    for etiqueta in ("apto", "no_apto"):
        lineas.append(f"| {etiqueta} | {m.get(f'{etiqueta}|fit', 0)} | {m.get(f'{etiqueta}|not_fit', 0)} | {m.get(f'{etiqueta}|unclear', 0)} |")
    lineas += ["", "## 3. Errores críticos (aprobaciones automáticas de candidatos no aptos)", ""]
    if ind["errores_criticos"]:
        lineas += ["| Pasada | CV | Etiqueta | Categoría | Confianza |", "|---|---|---|---|---|"]
        lineas += [f"| {e['pasada']} | {e['candidate_id']} | {e['etiqueta']} | {e['categoria']} | {e['confianza']} |" for e in ind["errores_criticos"]]
    else:
        lineas.append("Ninguno.")
    lineas += ["", "## 4. Resultados por categoría (primera pasada)", "",
               "| Categoría | Casos | Aprobación automática | Rechazo por reglas | Escalado | Acierto del LLM |", "|---|---|---|---|---|---|"]
    for cat, c in ind["por_categoria"].items():
        lineas.append(f"| {cat} | {c.get('casos', 0)} | {c.get('aprobacion_automatica', 0)} | {c.get('rechazo_reglas', 0)} | "
                      f"{c.get('escalado', 0)} | {c.get('llm_aciertos', 0)}/{c.get('llm_evaluados', 0)} |")
    lineas += ["", "## 5. Pares de sesgo (CV idénticos salvo nombre, sexo o género gramatical)", "",
               "| Par | Comparaciones | Misma etiqueta | Misma ruta | Diferencia media de confianza |", "|---|---|---|---|---|"]
    for par, v in ind["pares_sesgo"].items():
        lineas.append(f"| {par} | {v['comparaciones']} | {fmt(v['misma_etiqueta_pct'], ' %')} | {fmt(v['misma_ruta_pct'], ' %')} | {fmt(v['dif_confianza_media'], dec=3)} |")
    lineas.append("")
    return "\n".join(lineas)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluacion de la calidad de las decisiones (tabla 6.4).")
    parser.add_argument("--catalogo", default=str(ROOT / "data" / "eval_catalog.json"))
    parser.add_argument("--etiquetas", default=str(ROOT / "data" / "eval_labels.csv"))
    parser.add_argument("--oferta", help="external_id de la oferta (por defecto, la primera del catalogo)")
    parser.add_argument("--pasadas", type=int, default=5, help="ejecuciones de cada CV, para medir la consistencia")
    parser.add_argument("--base-datos", help="nombre de una base de datos PostgreSQL aparte para la evaluacion")
    parser.add_argument("--salida", help="carpeta de resultados (por defecto eval_resultados/<fecha>)")
    parser.add_argument("--no-cargar", action="store_true", help="no cargar el catalogo (ya esta en la BD)")
    parser.add_argument("--simulado", action="store_true", help="LLM simulado, sin coste (solo para ensayos)")
    args = parser.parse_args()
    if args.pasadas < 1:
        parser.error("--pasadas debe ser al menos 1")
    ejecutar(args)


if __name__ == "__main__":
    main()

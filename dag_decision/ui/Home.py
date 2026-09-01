"""Punto de entrada de la UI Streamlit del motor de decision DAG.

Uso (desde `dag_decision/`, con el venv activo y `.env`/Postgres arriba):

    .venv\\Scripts\\python -m streamlit run ui\\Home.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # dag_decision/, para poder importar src.*

import streamlit as st

st.set_page_config(page_title="Motor de decision DAG", page_icon="🧭", layout="wide")

st.title("Motor de decision DAG — TFM")
st.markdown(
    """
Selecciona una pagina en la barra lateral:

- **Nuevo Caso**: lanza una candidatura (CV + oferta, ya cargados en BD) a
  traves del pipeline completo (reglas → LLM → validacion → escalacion
  humana si procede → decision final).
- **Cola de Escalaciones**: resuelve los casos pausados esperando revision
  humana (equivalente en el navegador a `scripts/review_escalations.py`).
- **Historial de Casos**: consulta el resultado y la auditoria completa
  (regla, LLM, validacion, escalacion, decision final) de cada caso.
"""
)

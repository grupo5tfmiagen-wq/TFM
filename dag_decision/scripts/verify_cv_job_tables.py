"""Script de verificación: comprueba que las tablas cv_documents y job_postings existen y funcionan.

Uso:
    python scripts/verify_cv_job_tables.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import inspect

from src.db.base import engine, SessionLocal
from src.db.models import CVDocument, JobPosting, Case


def verificar_tablas() -> None:
    """Verifica que las nuevas tablas existen en la base de datos."""
    inspector = inspect(engine)
    tables = sorted(inspector.get_table_names())
    
    print("=== Verificación de tablas ===")
    print(f"Total de tablas: {len(tables)}")
    
    required_tables = ["cv_documents", "job_postings", "cases"]
    for table in required_tables:
        if table in tables:
            print(f"✓ {table}")
        else:
            print(f"✗ {table} - NO ENCONTRADA")
    
    # Verificar columnas de cases
    if "cases" in tables:
        columns = [col["name"] for col in inspector.get_columns("cases")]
        print(f"\n=== Columnas de 'cases' ===")
        for col in ["cv_document_id", "job_posting_id"]:
            if col in columns:
                print(f"✓ {col}")
            else:
                print(f"✗ {col} - NO ENCONTRADA")


def contar_registros() -> None:
    """Cuenta los registros en las nuevas tablas."""
    db = SessionLocal()
    try:
        print(f"\n=== Registros actuales ===")
        print(f"CV Documents: {db.query(CVDocument).count()}")
        print(f"Job Postings: {db.query(JobPosting).count()}")
        print(f"Cases: {db.query(Case).count()}")
        
        # Mostrar casos con relaciones
        casos_con_cv = db.query(Case).filter(Case.cv_document_id.isnot(None)).count()
        casos_con_oferta = db.query(Case).filter(Case.job_posting_id.isnot(None)).count()
        print(f"\nCases con CV relacionado: {casos_con_cv}")
        print(f"Cases con oferta relacionada: {casos_con_oferta}")
    finally:
        db.close()


if __name__ == "__main__":
    try:
        verificar_tablas()
        contar_registros()
        print("\n✓ Verificación completada")
    except Exception as e:
        print(f"\n✗ Error durante la verificación: {e}")
        sys.exit(1)

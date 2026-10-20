import pandas as pd
import sqlite3
from fastapi import FastAPI, HTTPException

app = FastAPI(title="Auditor de Llamadas IFT + OSINT")
DB_PATH = "numeracion_ift.db"

def inicializar_bd(csv_path: str):
    """Carga el CSV del Plan Nacional de Numeración del IFT a SQLite."""
    df = pd.read_csv(csv_path, dtype=str)
    
    # Limpieza y conversión de rangos a enteros de 64 bits para búsqueda rápida
    df['inicio_int'] = df['NUMERACION_INICIAL'].str.strip().astype('int64')
    df['fin_int'] = df['NUMERACION_FINAL'].str.strip().astype('int64')
    
    conn = sqlite3.connect(DB_PATH)
    df.to_sql("rangos_ift", conn, if_exists="replace", index=False)
    
    # Índice compuesto para que la consulta por rango tome < 2 milisegundos
    conn.execute("CREATE INDEX idx_rango ON rangos_ift (inicio_int, fin_int);")
    
    # Tabla para tu propio registro de llamadas y detección de bloques
    conn.execute("""
        CREATE TABLE IF NOT EXISTS historial_spam (
            numero INTEGER PRIMARY KEY,
            prefijo_bloque TEXT,
            fecha_reporte TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            notas TEXT
        );
    """)
    conn.close()

@app.get("/consultar/{numero}")
def consultar_numero(numero: str):
    if len(numero) != 10 or not numero.isdigit():
        raise HTTPException(status_code=400, detail="El número debe tener 10 dígitos.")
    
    num_int = int(numero)
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    try:
        # Usar SELECT * evita que la app colapse si el IFT cambia el nombre de las columnas
        cur.execute("""
            SELECT *
            FROM rangos_ift
            WHERE ? BETWEEN inicio_int AND fin_int
            LIMIT 1
        """, (num_int,))
        info_ift = cur.fetchone()
        
        if not info_ift:
            return {"numero": numero, "estado": "No asignado en IFT (Posible Spoofing)"}
            
        # Convertir la fila a diccionario para leerla de forma segura
        datos = dict(info_ift)
        
        # Extraer datos soportando variaciones en los nombres de las columnas
        operador = datos.get("RAZON_SOCIAL", datos.get("RAZON SOCIAL", "Desconocido"))
        tipo_red = datos.get("TIPO_RED", datos.get("TIPO RED", "No especificado"))
        estado = datos.get("ESTADO", "---")
        municipio = datos.get("MUNICIPIO", "---")
        num_ini = datos.get("NUMERACION_INICIAL", "")
        num_fin = datos.get("NUMERACION_FINAL", "")
        
        es_voip_probable = not any(op in str(operador).upper() for op in ["RADIOMOVIL", "AT&T", "PEGASO", "TELMEX", "TELEFONOS DE MEXICO"])
        
        return {
            "numero": numero,
            "operador_concesionario": operador,
            "tipo_red": tipo_red,
            "ubicacion": f"{municipio}, {estado}".strip(", "),
            "rango_asignado": f"{num_ini} - {num_fin}",
            "alerta_callcenter_voip": es_voip_probable,
            "enlaces_osint": {
                "whatsapp_check": f"https://wa.me/521{numero}"
            }
        }
    finally:
        conn.close()
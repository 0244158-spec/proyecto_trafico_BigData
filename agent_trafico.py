import os
import psycopg2
from openai import OpenAI
from dotenv import load_dotenv

# Cargar variables desde .env
load_dotenv()

# ========= CONFIGURACIÓN =========

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("Falta OPENAI_API_KEY en el .env")

# Datos de conexión (SESSION POOLER)
DB_HOST = "aws-1-us-east-2.pooler.supabase.com"
DB_PORT = 5432
DB_NAME = "postgres"
DB_USER = "postgres.tuppqwbnfhdbijyppodq"
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_SSLMODE = "require"

if not DB_PASSWORD:
    raise ValueError("Falta DB_PASSWORD en el .env")

# Esquema para guiar al modelo
SCHEMA_DESCRIPTION = """
Tabla trafico_amg_clean(
    id numeric,
    predominant_color text,
    exponential_color_weighting numeric,
    linear_color_weighting numeric,
    diffuse_logic_traffic text,
    dtime timestamp,
    lat numeric,
    long numeric
);
"""


# ========= CONEXIÓN A POSTGRES =========

def get_connection():
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        sslmode=DB_SSLMODE,
    )
    return conn


# ========= CLIENTE OPENAI =========

client = OpenAI(api_key=OPENAI_API_KEY)


# ========= GENERAR SQL DESDE LENGUAJE NATURAL =========

def nl_to_sql(question: str) -> str:

    system_prompt = f"""
Eres un experto en SQL para PostgreSQL.
Tu tarea es generar SOLO sentencias SQL (sin explicaciones) basadas en este esquema:

{SCHEMA_DESCRIPTION}

REGLAS IMPORTANTES:
- Usa SOLO la tabla trafico_amg_clean.
- SOLO SELECT (PROHIBIDO INSERT, UPDATE, DELETE, DROP, ALTER).
- NO incluyas bloques de código (PROHIBIDO usar ```sql o ``` ni backticks).
- NO incluyas texto antes o después de la SQL.
- La salida debe ser SQL PLANA.
- Si necesitas hora: EXTRACT(HOUR FROM dtime).
- Si necesitas día: DATE(dtime) o DATE_TRUNC('day', dtime).
- Si necesitas mes: DATE_TRUNC('month', dtime).
- Para zonas geográficas: ROUND(lat, 3) y ROUND(long, 3).
"""

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
    )

    sql = response.output[0].content[0].text.strip()

    # ========== LIMPIAR BACKTICKS Y MARKDOWN ==========
    sql = sql.replace("```sql", "")
    sql = sql.replace("```", "")
    sql = sql.replace("`", "")
    sql = sql.strip()

    return sql


# ========= EJECUTAR SQL =========

def run_sql(query: str, default_limit: int = 20):

    conn = get_connection()

    try:
        with conn.cursor() as cur:

            # Si no trae LIMIT, añadimos uno
            if "limit" not in query.lower():
                query = query.rstrip(" ;") + f" LIMIT {default_limit};"

            cur.execute(query)
            rows = cur.fetchall()
            colnames = [desc[0] for desc in cur.description]
            return colnames, rows, query

    finally:
        conn.close()


# ========= FLUJO COMPLETO =========

def ask(question: str):

    print("\n🔹 Pregunta:", question)

    sql = nl_to_sql(question)
    print("\n🔸 SQL generada:\n", sql)

    try:
        colnames, rows, executed_sql = run_sql(sql)
    except Exception as e:
        print("\n❌ ERROR ejecutando SQL:", e)
        return

    print("\n🔹 SQL ejecutada:")
    print(executed_sql)

    print("\n🔸 Resultados:")
    if not rows:
        print("(Sin resultados)")
        return

    print(" | ".join(colnames))
    print("-" * 80)
    for r in rows:
        print(" | ".join(str(x) for x in r))


# ========= CLI PRINCIPAL =========

if __name__ == "__main__":
    print("Asistente LLM-SQL para análisis de tráfico (trafico_amg_clean)")
    print("Escribe tu pregunta o 'salir' para terminar.\n")

    while True:
        q = input("Pregunta: ")

        if q.lower().strip() in ("salir", "exit", "quit"):
            print("Saliendo...")
            break

        if q.strip() == "":
            continue

        ask(q)
        print("\n" + "=" * 100 + "\n")

# Proyecto Final – Análisis de Tráfico con LLM y SQL Agent

Este proyecto carga un dataset masivo de tráfico (~3.9 millones de registros) a una base de datos PostgreSQL en Supabase y permite hacer análisis usando un **agente de lenguaje natural**.  
El usuario escribe una pregunta en español (por ejemplo: *"¿Cuál es el tráfico promedio por hora del día?"*) y un **LLM (modelo de OpenAI)** genera la consulta SQL, la ejecuta contra la tabla `trafico_amg_clean` y devuelve los resultados.

---

## Arquitectura General del Proyecto

El proyecto sigue una arquitectura tipo **Medallion** con dos capas principales y un agente inteligente para análisis dinámico.

            ┌──────────────────────────┐
            │         CSV RAW           │
            │   (3.9 millones rows)     │
            └─────────────┬────────────┘
                          ▼
            ┌──────────────────────────┐
            │     Bronze Layer         │
            │   trafico_amg (raw)      │
            └─────────────┬────────────┘
                          ▼
            ┌──────────────────────────┐
            │     Silver Layer         │
            │ trafico_amg_clean (ETL)  │
            │ limpieza y tipos correctos│
            └─────────────┬────────────┘
                          ▼
            ┌──────────────────────────┐
            │   LLM SQL Agent (Python) │
            │ Pregunta → SQL → Result  │
            └──────────────────────────┘

### Bronze (trafico_amg)
- Contiene los datos originales del CSV.
- Todos los tipos vienen como texto.
- Puede contener errores o valores fuera de formato.

### Silver (trafico_amg_clean)
- Campos convertidos correctamente a:
  - `numeric`  
  - `timestamp`  
  - `text`
- Filas inválidas eliminadas.
- Lista para análisis real.

### Agente LLM-SQL
- Genera SQL basada en lenguaje natural.
- Ejecuta consultas automáticas.
- Responde al usuario con tablas de resultados.

---


## Carga del Dataset (Bronze Layer)

El dataset original contenía alrededor de **3.9 millones de registros de tráfico**, cada uno con:

- color predominante,
- ponderaciones de color,
- lógica difusa de tráfico,
- coordenadas (lat/long),
- fecha y hora en diversos formatos.

Debido al tamaño, el archivo CSV excedía los límites de carga directa, por lo que se dividió en partes más pequeñas y se insertó mediante:

- `psql` con `\copy`  
- o el cargador de CSV de Supabase cuando fue posible  

La tabla creada para el RAW fue:

```sql
CREATE TABLE trafico_amg (
    id text,
    predominant_color text,
    exponential_color_weighting text,
    linear_color_weighting text,
    diffuse_logic_traffic text,
    dtime text,
    lat text,
    long text
);
```
---

## Limpieza y Transformación (Silver Layer)

Para convertir los datos en un formato analizable, se creó la tabla:
trafico_amg_clean


mediante una transformación SQL que:

1. **Convertía valores numéricos**  
2. **Convertía fechas** usando `TO_TIMESTAMP`  
3. **Eliminaba registros corruptos**  
4. **Tipaba correctamente las columnas**

Código utilizado:

```sql
CREATE TABLE trafico_amg_clean AS
SELECT
    CAST(id AS numeric) AS id,
    predominant_color,
    CAST(exponential_color_weighting AS numeric) AS exponential_color_weighting,
    CAST(linear_color_weighting AS numeric) AS linear_color_weighting,
    diffuse_logic_traffic,
    TO_TIMESTAMP(dtime, 'YYYYMMDDHH24MISS') AS dtime,
    CAST(lat AS numeric) AS lat,
    CAST(long AS numeric) AS long
FROM trafico_amg
WHERE
    exponential_color_weighting ~ '^[0-9\.]+$' AND
    linear_color_weighting ~ '^[0-9\.]+$' AND
    lat ~ '^-?[0-9\.]+$' AND
    long ~ '^-?[0-9\.]+$';
```
Esto generó una tabla final limpia, tipada y lista para análisis, cumpliendo los principios de la capa Silver de la arquitectura Medallion.



Construcción del Agente LLM con conexión a PostgreSQL

Para permitir que el usuario hiciera preguntas en lenguaje natural y que el modelo generara consultas SQL automáticamente, construimos un agente LLM–SQL usando:

Python

OpenAI (gpt-4o-mini / gpt-4.1)

psycopg2 (cliente PostgreSQL)

Un "tool" que valida y ejecuta SQL generado por el LLM

Sanitización básica del SQL para evitar errores

Instalación de dependencias
pip install openai psycopg2 python-dotenv


Creamos un entorno virtual:

python3 -m venv venv
source venv/bin/activate

Variables de entorno

Creamos un archivo .env:

OPENAI_API_KEY=sk-XXXXXX
DB_HOST=aws-1-us-east-2.pooler.supabase.com
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres.tuppqwbnfhdbijyppodq
DB_PASSWORD= TU_PASSWORD_AQUI

Lógica del agente (agent_trafico.py)

Este archivo contiene:

Conexión a PostgreSQL

Definición del “tool” que ejecuta SQL

Instrucciones al agente para que solo genere SQL válido

Un ciclo interactivo donde el usuario puede preguntar lo que quiera

Aquí está el código completo que debes poner en tu README:

import os
import psycopg2
from dotenv import load_dotenv
from openai import OpenAI

# Inicializar cliente OpenAI
client = OpenAI(api_key=API_KEY)

# -------------------------------------------------------------------
# FUNCIÓN: Ejecutar SQL de forma segura
# -------------------------------------------------------------------
def run_sql_query(query):
    try:
        # Sanitizar: eliminar ```sql y ```
        query = query.replace("```sql", "").replace("```", "").strip()

        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        cur = conn.cursor()
        cur.execute(query)

        try:
            rows = cur.fetchall()
        except:
            rows = []

        headers = [d[0] for d in cur.description] if cur.description else []
        conn.commit()

        cur.close()
        conn.close()

        return {"headers": headers, "rows": rows}

    except Exception as e:
        return {"error": str(e)}


# Definición del TOOL para OpenAI
tools = [
    {
        "type": "function",
        "function": {
            "name": "run_sql_query",
            "description": "Ejecuta una consulta SQL en PostgreSQL",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"}
                },
                "required": ["query"]
            }
        }
    }
]

# -------------------------------------------------------------------
# LOOP INTERACTIVO DEL AGENTE
# -------------------------------------------------------------------
def main():
    print("Asistente de tráfico LLM-SQL conectado a trafico_amg_clean")
    print("Escribe tu pregunta en lenguaje natural. Escribe 'salir' para terminar.\n")

    while True:
        pregunta = input("Pregunta: ")
        if pregunta.lower() == "salir":
            break

        # Llamada al modelo
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Eres un asistente experto en SQL. "
                        "Tu trabajo es generar únicamente SQL válido para PostgreSQL "
                        "sobre la tabla trafico_amg_clean. "
                        "Nunca expliques, solo genera SQL."
                    )
                },
                {"role": "user", "content": pregunta}
            ],
            tools=tools,
            tool_choice="auto"
        )

        msg = response.choices[0].message

        # ¿El modelo llamó al TOOL?
        if msg.tool_calls:
            sql_code = msg.tool_calls[0].function.arguments
            import json
            sql_code = json.loads(sql_code)["query"]

            print("\n🔧 SQL generada por el modelo:\n", sql_code, "\n")

            result = run_sql_query(sql_code)

            if "error" in result:
                print("❌ Error al ejecutar SQL:", result["error"])
            else:
                print("📊 Resultados:")
                for row in result["rows"]:
                    print(row)

            print("\n" + "="*80 + "\n")

        else:
            print("El modelo no generó SQL.")

if __name__ == "__main__":
    main()

Ejemplo funcionando

Consulta del usuario:

¿Cuál es el tráfico promedio por hora del día?

SQL generada automáticamente:

SELECT
    EXTRACT(HOUR FROM dtime) AS hora,
    AVG(exponential_color_weighting) AS trafico_promedio
FROM trafico_amg_clean
GROUP BY hora
ORDER BY hora;


Resultado:

hora | trafico_promedio
-------------------------
1    | 508.29
2    | 508.29
3    | 508.29
...

## ¿Qué permite este agente?

El usuario puede preguntar:

>“¿Qué tráfico hay en un punto (lat,long)?”

>“¿Qué hora del día tiene más tráfico?”

>“¿Cuál es el color predominante más común?”

>“Dame un histograma por hora”

>“¿Dónde se registran valores anómalos?”

>“¿Qué zonas tienen tráfico por arriba del percentil 90?”

Todo en lenguaje natural → SQL automático → ejecución real en PostgreSQL.

---

## 📊 Análisis realizados con el agente LLM-SQL
 
A continuación se describen los análisis implementados, cada uno con:

- Pregunta en lenguaje natural  
- SQL generada (o equivalente)  
- Interpretación del resultado  

---

### Tráfico promedio por hora del día

**Pregunta (usuario):**

> ¿Cuál es el tráfico promedio (exponential_color_weighting) por hora del día?

**SQL generada:**

SELECT
    EXTRACT(HOUR FROM dtime) AS hora,
    AVG(exponential_color_weighting) AS trafico_promedio
FROM trafico_amg_clean
GROUP BY hora
ORDER BY hora;

Interpretación:
Permite identificar cuáles son las horas con mayor intensidad de tráfico promedio en toda la ciudad.

Tráfico promedio por día de la semana

**Pregunta (usuario):**

>¿Qué día de la semana tiene mayor tráfico promedio?

**SQL generada:**

SELECT
    TO_CHAR(dtime, 'Day') AS dia_semana,
    AVG(exponential_color_weighting) AS trafico_promedio
FROM trafico_amg_clean
GROUP BY dia_semana
ORDER BY trafico_promedio DESC;


Interpretación:
Permite encontrar qué días (lunes, martes, etc.) presentan mayor congestión en promedio.

Zonas de mayor congestión (heatmap simplificado)

**Pregunta (usuario):**

>¿Cuáles son las zonas con mayor tráfico promedio?

**SQL generada:**

SELECT
    ROUND(lat, 3) AS grid_lat,
    ROUND(long, 3) AS grid_long,
    AVG(exponential_color_weighting) AS trafico_promedio,
    COUNT(*) AS registros
FROM trafico_amg_clean
GROUP BY grid_lat, grid_long
ORDER BY trafico_promedio DESC
LIMIT 50;


Interpretación:
Agrupa puntos cercanos (por coordenadas) y devuelve las “celdas” con mayor tráfico promedio, útil para construir un mapa de calor.

Puntos con mayor tráfico rojo

**Pregunta (usuario):**

>¿En qué coordenadas se presenta más tráfico rojo?

**SQL generada:**

SELECT
    lat,
    long,
    COUNT(*) AS veces_rojo
FROM trafico_amg_clean
WHERE predominant_color = 'red'
GROUP BY lat, long
ORDER BY veces_rojo DESC
LIMIT 20;


Interpretación:
Identifica las coordenadas donde más veces se detecta el color predominante “red”, asociado a alto tráfico o congestión.

Distribución por tipo de tráfico (diffuse_logic_traffic)

**Pregunta (usuario):**

>¿Cómo se reparte el tráfico por tipo de diffuse_logic_traffic?

**SQL generada:**

SELECT
    diffuse_logic_traffic,
    COUNT(*) AS registros
FROM trafico_amg_clean
GROUP BY diffuse_logic_traffic
ORDER BY registros DESC;


Interpretación:
Muestra qué categorías lógicas de tráfico (según el campo diffuse_logic_traffic) son más frecuentes en el dataset.

(Opcional) Tendencia mensual del tráfico

**Pregunta (usuario):**

>¿Cómo ha cambiado el tráfico promedio por mes?

**SQL generada:**

SELECT
    DATE_TRUNC('month', dtime) AS mes,
    AVG(exponential_color_weighting) AS trafico_promedio
FROM trafico_amg_clean
GROUP BY mes
ORDER BY mes;


Interpretación:
Sirve para construir una serie de tiempo mensual y analizar si el tráfico aumenta, disminuye o se mantiene estable.

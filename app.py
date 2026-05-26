import json
import os
import re
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path

import google.generativeai as genai
from dotenv import load_dotenv
from flask import Flask, redirect, render_template, request, url_for


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "du-ra-dev-secret")

dudas = []
ultimo_analisis = None
contador_dudas = 1


CATEGORIAS_LOCALES = {
    "Subneteo": ["subneteo", "mascara", "host", "hosts", "/24", "/26", "red"],
    "VLAN": ["vlan", "trunk", "access", "switch"],
    "Router/Switch": ["router", "switch", "capa", "gateway"],
    "Programacion": ["error", "codigo", "variable", "funcion", "clase"],
    "Base de datos": ["sql", "tabla", "consulta", "mysql", "sqlite"],
}


def limpiar_texto(texto):
    return texto.strip()


def validar_duda(texto):
    if not texto:
        return False, "La duda no puede estar vacia."
    if len(texto) < 5:
        return False, "La duda debe tener al menos 5 caracteres."
    if len(texto) > 500:
        return False, "La duda no puede superar los 500 caracteres."
    return True, ""


def normalizar_texto(texto):
    texto_normalizado = unicodedata.normalize("NFKD", texto.lower())
    return "".join(
        caracter
        for caracter in texto_normalizado
        if not unicodedata.combining(caracter)
    )


def crear_duda(texto):
    global contador_dudas

    duda = {
        "id": contador_dudas,
        "texto": texto,
        "fecha_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "categoria": None,
        "solucion": None,
        "origen_solucion": None,
        "fecha_solucion": None,
    }
    dudas.append(duda)
    contador_dudas += 1
    return duda


def buscar_duda_por_id(duda_id):
    return next((duda for duda in dudas if duda["id"] == duda_id), None)


def normalizar_origen(origen):
    origen_limpio = normalizar_texto(str(origen or ""))
    if origen_limpio in ("ia", "gemini", "api"):
        return "ia"
    return "local"


def mensaje_origen(origen):
    if normalizar_origen(origen) == "ia":
        return "Respuesta generada con IA"
    return "Respuesta generada con análisis local"


def extraer_json(texto):
    texto_limpio = texto.strip()

    if texto_limpio.startswith("```"):
        texto_limpio = re.sub(r"^```(?:json)?", "", texto_limpio, flags=re.IGNORECASE).strip()
        texto_limpio = re.sub(r"```$", "", texto_limpio).strip()

    inicio = texto_limpio.find("{")
    fin = texto_limpio.rfind("}")
    if inicio == -1 or fin == -1 or fin < inicio:
        raise ValueError("La respuesta no contiene JSON.")

    return json.loads(texto_limpio[inicio : fin + 1])


def normalizar_analisis(datos):
    origen = normalizar_origen(datos.get("origen", "ia"))
    return {
        "temas_detectados": datos.get("temas_detectados", []),
        "tema_mas_confuso": datos.get("tema_mas_confuso", "General"),
        "resumen": datos.get("resumen", "No se pudo generar un resumen detallado."),
        "sugerencia_profesor": datos.get(
            "sugerencia_profesor",
            "Se recomienda revisar las dudas recibidas y reforzar el tema principal.",
        ),
        "preguntas_guia": datos.get("preguntas_guia", []),
        "origen": origen,
        "origen_mensaje": mensaje_origen(origen),
    }


def analizar_con_gemini(dudas_recibidas):
    api_key = os.getenv("GEMINI_API_KEY")
    modelo = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    if not api_key:
        raise RuntimeError("No hay GEMINI_API_KEY configurada.")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(modelo)

    dudas_texto = "\n".join(
        f"{duda['id']}. {duda['texto']}" for duda in dudas_recibidas
    )

    prompt = f"""
Analiza estas dudas anonimas de alumnos y responde unicamente con JSON valido.
No uses markdown, explicaciones ni texto fuera del JSON.

Dudas:
{dudas_texto}

La estructura exacta debe ser:
{{
  "temas_detectados": [
    {{
      "tema": "Nombre del tema",
      "cantidad": 1,
      "dudas_relacionadas": ["Texto de duda"]
    }}
  ],
  "tema_mas_confuso": "Nombre del tema",
  "resumen": "Resumen breve",
  "sugerencia_profesor": "Sugerencia clara para volver a explicar",
  "preguntas_guia": ["Pregunta 1", "Pregunta 2", "Pregunta 3"]
}}
"""

    respuesta = model.generate_content(prompt)
    texto_respuesta = getattr(respuesta, "text", "")
    if not texto_respuesta:
        raise ValueError("Gemini no devolvio texto.")

    analisis = extraer_json(texto_respuesta)
    analisis["origen"] = "ia"
    return normalizar_analisis(analisis)


def detectar_categoria(texto):
    texto_minuscula = normalizar_texto(texto)
    puntajes = {}

    for categoria, palabras in CATEGORIAS_LOCALES.items():
        puntajes[categoria] = sum(1 for palabra in palabras if palabra in texto_minuscula)

    mejor_categoria = max(puntajes, key=puntajes.get)
    if puntajes[mejor_categoria] == 0:
        return "General"
    return mejor_categoria


def analizar_localmente(dudas_recibidas):
    grupos = {}
    palabras = []

    for duda in dudas_recibidas:
        categoria = detectar_categoria(duda["texto"])
        grupos.setdefault(categoria, []).append(duda["texto"])
        palabras.extend(
            palabra
            for palabra in re.findall(r"\b[\w/]+\b", normalizar_texto(duda["texto"]))
            if len(palabra) > 3
        )

    temas_detectados = [
        {
            "tema": tema,
            "cantidad": len(dudas_relacionadas),
            "dudas_relacionadas": dudas_relacionadas,
        }
        for tema, dudas_relacionadas in sorted(
            grupos.items(), key=lambda item: len(item[1]), reverse=True
        )
    ]

    tema_mas_confuso = temas_detectados[0]["tema"] if temas_detectados else "General"
    frecuentes = [palabra for palabra, _ in Counter(palabras).most_common(5)]
    palabras_resumen = ", ".join(frecuentes) if frecuentes else "las dudas recibidas"

    analisis = {
        "temas_detectados": temas_detectados,
        "tema_mas_confuso": tema_mas_confuso,
        "resumen": (
            f"El tema con mas dudas parece ser {tema_mas_confuso}. "
            f"Palabras frecuentes: {palabras_resumen}."
        ),
        "sugerencia_profesor": (
            f"Se recomienda volver a explicar {tema_mas_confuso}, usando ejemplos "
            "paso a paso y resolviendo una duda representativa frente al grupo."
        ),
        "preguntas_guia": [
            f"Que conceptos basicos de {tema_mas_confuso} deben quedar claros?",
            "Cual es el paso que mas se repite en las dudas?",
            "Que ejemplo corto puede resolver varias dudas a la vez?",
        ],
        "origen": "local",
    }
    return normalizar_analisis(analisis)


def obtener_analisis(dudas_recibidas):
    if not dudas_recibidas:
        return None

    try:
        return analizar_con_gemini(dudas_recibidas)
    except Exception:
        return analizar_localmente(dudas_recibidas)


def detectar_categoria_desde_analisis(duda):
    if duda.get("categoria"):
        return duda["categoria"]

    if ultimo_analisis:
        for tema in ultimo_analisis.get("temas_detectados", []):
            if duda["texto"] in tema.get("dudas_relacionadas", []):
                return tema.get("tema", "General")

    return detectar_categoria(duda["texto"])


def generar_solucion_con_gemini(duda):
    api_key = os.getenv("GEMINI_API_KEY")
    modelo = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    if not api_key:
        raise RuntimeError("No hay GEMINI_API_KEY configurada.")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(modelo)

    prompt = f"""
Responde la siguiente duda de clase con una explicacion breve y clara para un estudiante.
Devuelve unicamente JSON valido, sin markdown ni texto adicional.

Duda:
{duda["texto"]}

La estructura exacta debe ser:
{{
  "tema": "Tema detectado",
  "solucion": "Explicacion sugerida en 2 a 4 frases"
}}
"""

    respuesta = model.generate_content(prompt)
    texto_respuesta = getattr(respuesta, "text", "")
    if not texto_respuesta:
        raise ValueError("Gemini no devolvio texto.")

    datos = extraer_json(texto_respuesta)
    return {
        "categoria": datos.get("tema") or detectar_categoria(duda["texto"]),
        "solucion": datos.get("solucion") or "Se recomienda revisar esta duda con un ejemplo guiado.",
        "origen_solucion": "ia",
    }


def generar_solucion_local(duda):
    categoria = detectar_categoria(duda["texto"])

    explicaciones = {
        "Subneteo": (
            "Esta duda parece relacionada con subneteo. Conviene repasar como se lee "
            "la notacion CIDR, como se obtiene la mascara y como se calcula la cantidad "
            "de hosts utiles. Un buen ejemplo es resolver una red /26 paso a paso."
        ),
        "VLAN": (
            "Esta duda parece relacionada con VLAN. Revisa la diferencia entre puertos "
            "access y trunk, y como una VLAN separa dominios de broadcast dentro de un switch."
        ),
        "Router/Switch": (
            "Esta duda parece relacionada con router o switch. Explica que dispositivo "
            "conecta redes, cual conmuta dentro de una red local y que papel cumple el gateway."
        ),
        "Programacion": (
            "Esta duda parece relacionada con programacion. Sugiere revisar el error, "
            "leer el mensaje que aparece y seguir el flujo del codigo con valores pequenos."
        ),
        "Base de datos": (
            "Esta duda parece relacionada con bases de datos. Conviene repasar tablas, "
            "consultas SQL basicas y como filtrar informacion con una consulta simple."
        ),
        "General": (
            "La duda es general o no coincide con una categoria especifica. Conviene "
            "pedir un ejemplo concreto y explicar el concepto principal con un caso corto."
        ),
    }

    return {
        "categoria": categoria,
        "solucion": explicaciones.get(categoria, explicaciones["General"]),
        "origen_solucion": "local",
    }


def obtener_solucion_duda(duda):
    if duda.get("solucion"):
        return duda

    try:
        resultado = generar_solucion_con_gemini(duda)
    except Exception:
        resultado = generar_solucion_local(duda)

    duda["categoria"] = resultado["categoria"]
    duda["solucion"] = resultado["solucion"]
    duda["origen_solucion"] = resultado["origen_solucion"]
    duda["fecha_solucion"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return duda


@app.route("/", methods=["GET", "POST"])
def index():
    mensaje = None
    error = None

    if request.method == "POST":
        texto = limpiar_texto(request.form.get("duda", ""))
        es_valida, error_validacion = validar_duda(texto)

        if es_valida:
            crear_duda(texto)
            mensaje = "Tu duda anonima fue enviada correctamente."
        else:
            error = error_validacion

    return render_template("index.html", mensaje=mensaje, error=error)


@app.route("/profesor", methods=["GET", "POST"])
def profesor():
    global ultimo_analisis

    if request.method == "POST":
        accion = request.form.get("accion")

        if accion == "analizar":
            ultimo_analisis = obtener_analisis(dudas)
        elif accion == "limpiar":
            dudas.clear()
            ultimo_analisis = None

        return redirect(url_for("profesor"))

    return render_template(
        "profesor.html",
        dudas=dudas,
        total_dudas=len(dudas),
        analisis=ultimo_analisis,
        mensaje=request.args.get("mensaje"),
        error=request.args.get("error"),
        mensaje_origen=mensaje_origen,
    )


@app.route("/duda/<int:duda_id>")
def detalle_duda(duda_id):
    duda = buscar_duda_por_id(duda_id)
    if not duda:
        return redirect(
            url_for("profesor", error="La duda solicitada no existe o ya fue limpiada.")
        )

    obtener_solucion_duda(duda)
    duda["categoria"] = duda.get("categoria") or detectar_categoria_desde_analisis(duda)

    return render_template(
        "duda.html",
        duda=duda,
        mensaje_origen=mensaje_origen(duda.get("origen_solucion")),
    )


@app.route("/duda/<int:duda_id>/solucion", methods=["POST"])
def generar_solucion(duda_id):
    duda = buscar_duda_por_id(duda_id)
    if not duda:
        return redirect(
            url_for("profesor", error="No se encontro la duda para generar solucion.")
        )

    obtener_solucion_duda(duda)
    return redirect(url_for("detalle_duda", duda_id=duda_id))


if __name__ == "__main__":
    debug_activo = os.getenv("FLASK_DEBUG", "0") == "1"
    puerto = int(os.getenv("PORT", "5000"))
    app.run(port=puerto, debug=debug_activo, use_reloader=False)

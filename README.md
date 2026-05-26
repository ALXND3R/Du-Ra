# Du-Ra

Du-Ra es una aplicacion web para clases donde los alumnos envian dudas anonimas y el profesor identifica rapidamente que temas necesitan volver a explicarse.

## Que hace

- Permite recibir dudas anonimas durante una sesion de clase.
- Muestra un panel para el profesor con las dudas.
- Analiza las dudas con Gemini API.
- Usa analisis local si Gemini no esta disponible.
- Genera una solucion por duda y muestra si fue creada con IA o con analisis local.

## Tecnologias usadas

- Backend: Flask
- Frontend: HTML, CSS y Bootstrap
- IA de texto: Gemini API

## Instalacion

```bash
cd dura
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Configuracion


Edita `.env` y agrega tu clave:

```env
GEMINI_API_KEY=tu_api_key_aqui
GEMINI_MODEL=gemini-2.5-flash
```


## Ejecucion

```bash
python app.py
```

La app quedara disponible en:

```text
http://127.0.0.1:5000
```

## Rutas disponibles

- `/`: pagina para alumnos. Permite enviar una duda anonima.
- `/profesor`: panel del profesor. Muestra dudas, analiza con IA y limpia la clase.
  
## Flujo de uso

1. Los alumnos escriben sus dudas anonimas.
2. Cada duda se valida y se guarda en una lista temporal en memoria.
3. El profesor entra a `/profesor`.
4. El profesor presiona "Analizar dudas con IA".
5. La app intenta usar Gemini API para agrupar temas, detectar el tema mas confuso y generar sugerencias.
6. Si Gemini no responde, la app usa analisis local.
7. El profesor puede abrir una duda especifica para ver o generar su solucion.
8. La solucion queda guardada en memoria junto con su origen: IA o analisis local.
9. Al finalizar la clase, el profesor puede presionar "Limpiar dudas de la clase".

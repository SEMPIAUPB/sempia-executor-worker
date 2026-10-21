# SEMPIA Executor Worker (Evaluación en Sandbox y Patrón Outbox)

<p align="center">
  <img src="https://img.shields.io/badge/Celery-5.x-37814A?logo=celery&logoColor=white&style=for-the-badge" alt="Celery" />
  <img src="https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white&style=for-the-badge" alt="Redis" />
  <img src="https://img.shields.io/badge/Judge0_CE-1.13.1-000000?style=for-the-badge" alt="Judge0" />
  <img src="https://img.shields.io/badge/SQLite-Outbox_Pattern-003B57?logo=sqlite&logoColor=white&style=for-the-badge" alt="SQLite" />
  <img src="https://img.shields.io/badge/Sandbox-Isolate%20cgroups-8A2BE2?style=for-the-badge" alt="Isolate" />
</p>

---

## 📖 Descripción

**`sempia-executor-worker`** es el componente de ejecución y evaluación segura de código de la plataforma SEMPIA. Opera como un trabajador asíncrono distribuido mediante **Celery**, consumiendo trabajos de evaluación desde Redis, despachando la compilación y ejecución aislada hacia el motor **Judge0 CE** (Sandboxing con `isolate` y `cgroups` de Linux) y garantizando la entrega de calificaciones al servidor central mediante el **Patrón Outbox Transaccional** en SQLite.

Este servicio se ubica en el **Nodo 3** de la arquitectura, garantizando que el código no confiable enviado por los alumnos jamás se ejecute en el servidor central ni en el microservicio de IA.

---

## ✨ Componentes y Principios de Diseño

### 1. Consumo Seguro de Trabajos Celery
* **Cola de Evaluación:** Escucha de manera exclusiva la cola `judge_submissions`.
* **Acuse Tardío de Recibo (`task_acks_late=True`):** La tarea solo se retira formalmente de Redis una vez que ha finalizado la evaluación y ha sido persistida en el buzón local, previniendo pérdida de tareas ante caídas intempestivas del contenedor.
* **Prefetch Unitario (`worker_prefetch_multiplier=1`):** Impide que un solo trabajador monopolice múltiples tareas pesadas, balanceando equitativamente la carga computacional.

### 2. Aislamiento y Sandboxing con Judge0 CE (`judge0.py`)
* El worker actúa exclusivamente como un orquestador seguro y **nunca ejecuta código de terceros localmente**.
* Delega la ejecución en Judge0 CE, el cual confina el código en jaulas `isolate`:
  * **Límite de CPU:** Parada forzosa con señal `SIGXCPU` si se supera el tiempo límite ($1{,}000\text{ ms}$).
  * **Límite de Memoria RAM:** Monitoreado por `cgroups` ($256{,}000\text{ KB}$), invocando al OOM Killer ante fugas de memoria.
  * **Aislamiento de Red:** Bandera `--share-net=false` activa para impedir ataques de *Reverse Shell* o escaneo de puertos internos.
  * **Sistema de Archivos:** Montaje en modo solo lectura (`ro`) con cuotas estrictas de disco en `/tmp`.
* **Mapeo Normalizado de Estados:** Transforma los códigos nativos de Judge0 en estados normalizados de SEMPIA:
  * `3` $\to$ `ACCEPTED`
  * `4` $\to$ `WRONG_ANSWER`
  * `5` $\to$ `TIME_LIMIT_EXCEEDED`
  * `6` $\to$ `COMPILATION_ERROR`
  * `7..12` $\to$ `RUNTIME_ERROR`
  * `13` $\to$ `INTERNAL_ERROR`

### 3. Patrón Outbox Transaccional y Resiliencia de Red (`outbox.py`)
Para prevenir la pérdida de calificaciones si el enlace HTTP entre el Nodo 3 y el Nodo 1 experimenta cortes o el servidor central se reinicia:
1. Inmediatamente finalizada la evaluación en Judge0, el veredicto normalizado se inserta en `outbox.db` (SQLite local) con estado `PENDING`.
2. Se intenta notificar síncronamente al Nodo 1: `POST /api/v1/submissions/{id}/callback`.
3. Si el servidor central responde con HTTP 200, el evento se marca como `PROCESSED`.
4. Si la red falla (HTTP 500, timeout o caída de red), un proceso programado de **Celery Beat** (`flush_outbox`) reintenta la entrega cada $10\text{ segundos}$ aplicando retroceso exponencial (*exponential backoff*).
5. Se garantiza semántica de **entrega al menos una vez (*at-least-once delivery*)** con 0% de pérdidas de calificación.

---

## 🛠️ Solución al Conflicto de Puertos en Windows (Judge0 Server)

En sistemas Windows con Hyper-V, el rango dinámico `2292 - 2391` queda reservado por el sistema operativo, bloqueando el puerto nativo de Judge0 (`2358`).

**Solución Implementada:**
* El puerto expuesto hacia el host anfitrión se reasigna a **`23580`**, mientras que dentro de la red Docker interna sigue operando en `http://judge0-server:2358`.
* Configurable vía variable de entorno: `JUDGE0_PORT=23580`.

---

## 🚀 Configuración y Despliegue

### 1. Variables de Entorno (`.env`)
Crea un archivo `.env` en la raíz de `sempia-executor-worker/`:
```bash
CELERY_BROKER_URL=redis://192.168.1.10:6379/1
JUDGE0_API_URL=http://localhost:23580
API_BASE_URL=http://192.168.1.10:8000/api/v1
API_AUTH_TOKEN=secret_s2s_token
```

### 2. Despliegue con Docker Compose
```bash
docker compose up -d --build
```
El comando iniciará concurrentemente:
1. El demonio **Celery Worker** con 4 procesos paralelos (`--concurrency=4`).
2. El planificador **Celery Beat** para el barrido periódico del Outbox cada 10 segundos.

### 3. Ejecución en Entorno Local (Virtualenv)
```bash
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
pip install -r requirements.txt

# Iniciar worker y beat en segundo plano
celery -A worker worker -Q judge_submissions --loglevel=info --concurrency=4 &
celery -A worker beat --loglevel=info
```

---

## 🧪 Pruebas Automatizadas

El repositorio incluye pruebas unitarias para validación del contrato de datos, ejecución secuencial de casos de prueba y simulación de contingencia del Outbox:

```bash
pytest tests/test_worker.py
```
*Cobertura: 8 casos de prueba con 100% de éxito.*

---

## 📂 Estructura del Proyecto

```
sempia-executor-worker/
├── api_client.py        # Cliente HTTP hacia Node 1 (fetch_exercise_data, notify_result)
├── judge0.py            # Adaptador de integración, polling y mapeo de estados de Judge0
├── outbox.py            # Motor de persistencia SQLite local para el Patrón Outbox
├── schemas.py           # Modelos Pydantic (SubmissionContract, NormalizedResult)
├── worker.py            # Tareas Celery (judge_submission, flush_outbox periódica)
├── tests/               # Pruebas unitarias automatizadas con Mocks
├── Dockerfile           # Imagen Docker basada en Python 3.11 Slim
├── requirements.txt     # Dependencias (celery, redis, requests, pydantic)
└── README.md
```

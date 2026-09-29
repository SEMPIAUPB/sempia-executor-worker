# SEMPIA - Nodo 2: Executor Worker

Worker de evaluación de código para SEMPIA usando Judge0 CE y Celery.

## Configuración y Despliegue

1. Clonar este repositorio.
2. Copiar `.env.example` a `.env` y ajustar las variables de entorno.
3. Asegurarse de tener Judge0 CE desplegado y accesible desde este worker.
4. Levantar los servicios con Docker Compose:
   ```bash
   docker-compose up -d --build
   ```

## Aislamiento y Seguridad (Sandbox)

El aislamiento de seguridad se delega en **Judge0 CE**.
Es **CRÍTICO** que la instancia de Judge0 esté configurada adecuadamente:

*   Debe correr en contenedores aislados sin privilegios (no root).
*   Se deben configurar límites a nivel de cgroups (memoria, pids, CPU).
*   Se deben aplicar los profiles de seccomp recomendados por Judge0.
*   Desactivar el acceso a internet (`enable_network=false`) en los envíos si no es estrictamente necesario.
*   El worker NO debe correr en el mismo host que el servidor central (Nodo 1) a menos que esté en una red aislada.
*   El worker actúa solo como orquestador y nunca ejecuta código arbitrario de los estudiantes localmente.

## Tests

Para ejecutar las pruebas:

```bash
pip install -r requirements.txt
pytest tests/
```

# Project Dossier · Proyecto APT (Capstone, Duoc UC)

Continuidad de Project Dossier: cierre de brechas para alcanzar el MVP de preparación automatizada de
reuniones. Equipo: Felipe Andrés Docmac Bravo, Darío García Avendaño y Felipe Orellana Álvarez.

**Sistema desplegado:** <https://frontend.158.69.0.151.nip.io/login>

El repositorio se organiza por fases de la asignatura:

| Carpeta | Contenido |
|---|---|
| [`Fase_1/`](Fase_1/) | Evidencias de la Fase 1 (definición del proyecto): individuales y grupales, tal como se evaluaron |
| [`Fase_2/`](Fase_2/) | Evidencias de la Fase 2 (desarrollo): individuales, grupales y las evidencias del proyecto |
| [`Fase_2/Evidencias_de_Proyecto/Evidencia_de_sistema_Aplicacion/`](Fase_2/Evidencias_de_Proyecto/Evidencia_de_sistema_Aplicacion/) | **El sistema completo**: backend, frontend, despliegue, documentación, especificaciones y registro de tareas. Su [README](Fase_2/Evidencias_de_Proyecto/Evidencia_de_sistema_Aplicacion/README.md) explica cómo ejecutarlo |
| [`Fase_2/Evidencias_de_Proyecto/Evidencia_de_sistema_Base_de_Datos/`](Fase_2/Evidencias_de_Proyecto/Evidencia_de_sistema_Base_de_Datos/) | Evidencias de la base de datos: migraciones versionadas con Alembic, modelo de datos y almacenamiento en PostgreSQL |
| [`Fase_3/`](Fase_3/) | Evidencias de la Fase 3 (se completa al cierre del proyecto) |

`.github/` queda en la raíz porque GitHub solo lee los workflows desde ahí; trabajan sobre la carpeta
del sistema.

Para trabajar en el código, abre la carpeta del sistema: todas las rutas de su documentación son
relativas a ella.

## Inicio rápido

Versión breve del [manual técnico](Fase_2/Evidencias_grupales/Manual_Tecnico_Project_Dossier.pdf).
Requisitos: Python 3.12, Node.js 20 o superior, PostgreSQL 16 y Git. En Windows (PowerShell) usa
`python` en vez de `python3`, `.venv\Scripts\activate` en vez de `source .venv/bin/activate` y
`copy` en vez de `cp`.

### 1. Descargar

```bash
git clone https://github.com/Xamppy/Project-Dossier.git
cd Project-Dossier/Fase_2/Evidencias_de_Proyecto/Evidencia_de_sistema_Aplicacion
```

### 2. Configurar

Crea la base de datos (con PostgreSQL en ejecución):

```bash
psql -U postgres -c "CREATE DATABASE sistemadossier;"
```

Backend:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

En `backend/.env` completa al menos:

| Variable | Valor |
|---|---|
| `DATABASE_URL` | `postgresql://postgres:TU_CLAVE@localhost:5432/sistemadossier` |
| `JWT_SECRET` | 16 caracteres o más; genéralo con `openssl rand -hex 32` |
| `DEEPSEEK_API_KEY` | Clave de DeepSeek con saldo (necesaria para generar dossiers) |

Las demás claves (PDL, Companies House, calendarios, correo) son opcionales: cada integración se
apaga sola si falta su clave. Luego crea el esquema, desde `backend/`:

```bash
alembic upgrade head
```

Frontend, en una segunda terminal desde la carpeta del sistema:

```bash
cd frontend
npm ci
cp .env.local.example .env.local
```

`frontend/.env.local` debe tener `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000`.

### 3. Ejecutar

Terminal 1, API (en `backend/`, con el entorno virtual activo):

```bash
python main.py
```

Terminal 2, dashboard (en `frontend/`):

```bash
npm run dev
```

Abre el dashboard en `http://127.0.0.1:3000`. Usa el mismo host (`127.0.0.1`) que la API: si mezclas
`localhost` y `127.0.0.1`, la sesión se cierra a los 15 minutos.

### 4. Probar

| Prueba | Resultado esperado |
|---|---|
| `http://127.0.0.1:8000/health` | Responde 200: la API está viva |
| `http://127.0.0.1:8000/db/health` | Confirma la conexión con PostgreSQL |
| `http://127.0.0.1:3000/register` | Creas una cuenta y una organización y entras al dashboard |
| Generar un dossier de empresa (Reino Unido o EE. UU.) | Pasa de «en cola» a «listo» y el informe se abre |

Pruebas automatizadas (opcional):

```bash
cd backend && pip install -r requirements-dev.txt && pytest
```

```bash
cd frontend && npm run lint && npm test
```

Con Node 26, ejecuta `npm test` con `NODE_OPTIONS=--no-experimental-webstorage`. Problemas frecuentes,
variables completas y despliegue con Docker: ver el [manual técnico](Fase_2/Evidencias_grupales/Manual_Tecnico_Project_Dossier.pdf).

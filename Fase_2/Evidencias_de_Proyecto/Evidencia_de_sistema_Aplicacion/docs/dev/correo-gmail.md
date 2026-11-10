# Envío de dossiers por correo con Gmail

La aplicación envía el dossier **completo**, con un **PDF adjunto**, al correo del usuario de
dos formas:

- **Automática:** cada dossier de Personas, al terminar, se envía solo a quien lo pidió. El
  formulario lo avisa: «Al terminar, te enviaremos el dossier en PDF a …».
- **Manual:** en el detalle de un dossier completo, botón «Enviarme por correo».

El correo siempre va a la dirección de quien lo pide. Para pasarle un dossier a un colega se
usa «Compartir».

Contrato y criterios: [specs/proposals/S6.1-envio-dossier-correo.md](../../specs/proposals/S6.1-envio-dossier-correo.md).
Decisión: [ADR 0005](../architecture/decisions/0005-proveedor-correo.md), actualización del 2026-11-02.

---

## 1. Crear la contraseña de aplicación

Gmail no acepta la contraseña normal de la cuenta por SMTP. Hace falta una **contraseña de
aplicación**:

1. Usa una cuenta de Gmail **de prueba o del proyecto**, no la personal.
2. Activa la verificación en dos pasos: Cuenta de Google → Seguridad → Verificación en 2 pasos.
   Sin ella, Google no muestra la opción del paso siguiente.
3. Ve a Cuenta de Google → Seguridad → **Contraseñas de aplicaciones** (o busca «contraseñas de
   aplicaciones» en la configuración de la cuenta).
4. Crea una con el nombre «Project Dossier». Google muestra 16 letras en cuatro grupos
   (`abcd efgh ijkl mnop`). Cópiala: no se vuelve a mostrar.

## 2. Configurar el backend

En `backend/.env` (local) o en las variables del servidor (Render, Dokploy):

```dotenv
SMTP_USERNAME=cuenta-del-proyecto@gmail.com
SMTP_PASSWORD=abcd efgh ijkl mnop
```

Con eso basta: el resto tiene valores por omisión para Gmail (`smtp.gmail.com`, puerto `587`,
STARTTLS). La contraseña se acepta con o sin espacios.

| Variable | Por omisión | Para qué |
|---|---|---|
| `SMTP_HOST` | `smtp.gmail.com` | Servidor |
| `SMTP_PORT` | `587` (`465` con `ssl`) | Puerto |
| `SMTP_SECURITY` | `starttls` | `starttls`, `ssl` o `none` (solo servidor local de pruebas) |
| `SMTP_FROM_EMAIL` | `SMTP_USERNAME` | Remitente. Gmail lo reescribe si no es de la cuenta |
| `SMTP_FROM_NAME` | `Project Dossier` | Nombre visible del remitente |
| `SMTP_TIMEOUT_SECONDS` | `20` | Tiempo máximo de espera del servidor |
| `DOSSIER_FRONTEND_URL` / `FRONTEND_URL` | `http://localhost:3000` | Base del enlace «Abrir en Project Dossier» |

Reinicia la API. `GET /auth/me` devuelve `email_delivery_available: true` y la interfaz muestra
la casilla y el botón. Si faltan `SMTP_USERNAME` o `SMTP_PASSWORD`, el envío queda desactivado y
la interfaz lo oculta.

**Nunca** subas la contraseña a git. `.env` ya está en `.gitignore`.

## 3. Probar sin Gmail

Para desarrollar sin mandar correos reales, usa un servidor que los atrape, como
[Mailpit](https://mailpit.axllent.org/):

```bash
docker run --rm -p 1025:1025 -p 8025:8025 axllent/mailpit
```

```dotenv
SMTP_HOST=127.0.0.1
SMTP_PORT=1025
SMTP_SECURITY=none
SMTP_FROM_EMAIL=dossier@example.com
```

Los correos se ven en <http://localhost:8025>. Las pruebas automáticas no necesitan nada de esto:
levantan su propio servidor SMTP en loopback (fixture `servidor_smtp` en `backend/tests/conftest.py`).

## 4. Problemas comunes

| Síntoma | Causa probable |
|---|---|
| El botón responde «No se pudo enviar el correo» y el log dice `(535)` | Contraseña de aplicación mal copiada, o se usó la contraseña normal de la cuenta |
| No aparece «Contraseñas de aplicaciones» en Google | Falta activar la verificación en dos pasos, o la cuenta es de Workspace y el administrador lo bloqueó |
| «Este dossier se acaba de enviar» (429) | Hay que esperar 60 s entre dos envíos manuales del mismo dossier |
| No llega nada y no hay error | Revisa la carpeta de spam. Gmail limita una cuenta personal a unos 500 correos al día |
| El envío automático no llegó | El job sigue `completed` aunque el correo falle (por diseño). Busca `No se pudo enviar por correo el dossier` en el log y reenvía con el botón |
| El correo llegó sin PDF | Busca `No se pudo generar el PDF del dossier` en el log. El informe va igual en el cuerpo |
| En el PDF falta un emoji | Se omite a propósito: DejaVu Sans no tiene emojis, y antes salían como ■ |

## 5. Qué contiene el correo

- Asunto `Dossier: <nombre>`, en el idioma del dossier (es, en, pt, it, fr, de).
- Un cuerpo corto: «Tu dossier está listo», la línea que menciona el PDF, el botón «Abrir en
  Project Dossier» y un pie que lo marca como confidencial. El informe no va en el cuerpo.
- **`dossier-<nombre>.pdf` adjunto**, con el formato del detalle web:
  - logo TraceLens, estado, idioma, nombre y fechas;
  - «Informe generado por IA» con el informe completo;
  - alertas y «Página n de N».

  Se lee sin entrar a la plataforma. Lo genera ReportLab (Python puro, sin dependencias del
  sistema) con DejaVu Sans incrustada, así que guiones, comillas, flechas y acentos se ven tal
  cual.
- Si el PDF fallara, el correo sale sin adjunto y con el informe en el cuerpo, para que no llegue
  vacío.

El correo es una copia que sale del sistema: no se borra con la retención de dossiers. Se aceptó
así porque el usuario ya puede descargar el dossier (DG, 2026-11-02).

## 6. Reintentos (S6.4)

Los envíos **automáticos** (Personas al terminar y reuniones del calendario) reintentan solos:

1. **3 intentos seguidos**, esperando 2 s y luego 5 s.
2. Si siguen fallando por algo **pasajero** (sin conexión, tiempo agotado, respuesta 4xx), el envío
   queda en `dossier_email_retries` y se reintenta **cada 10 minutos, hasta 1 hora** (6 veces).
3. Un fallo **definitivo** (5xx, como un buzón inexistente, o usuario y contraseña rechazados) no se
   reintenta.

Cada ronda queda en `audit_logs` (`EMAIL dossier_auto`) con `intentos`, `reintento` y `agotado`.
La fila en espera no guarda la dirección del destinatario: se lee de `users.email` al reintentar.
Si los dossiers se borraron entretanto (retención o el usuario), el envío se descarta.

El botón **Enviar por correo** no reintenta: el usuario ve el error y puede volver a pulsar.

Variables: `DOSSIER_EMAIL_RETRY_WORKER_ENABLED` (1) y `DOSSIER_EMAIL_RETRY_POLL_SECONDS` (60).
Para ver lo que está en espera:

```sql
SELECT kind, attempts, next_attempt_at, last_error FROM dossier_email_retries ORDER BY next_attempt_at;
```

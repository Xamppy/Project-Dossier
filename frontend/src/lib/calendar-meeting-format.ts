/**
 * Etiquetas aceptadas en la descripción del evento (alineado con calendar_meeting_labels.py).
 * Idiomas: es, en, pt, it, fr, de.
 */
export const CALENDAR_FIELD_LABELS = {
  company: [
    "empresa", "company", "compañía", "compania", "compañia", "cliente", "client",
    "organización", "organizacion", "organization", "organização", "organizacao",
    "entreprise", "société", "societe", "azienda", "impresa", "società", "societa",
    "unternehmen", "firma", "kunde",
  ],
  person: [
    "contacto", "contact", "nombre", "name", "nome", "nom", "contatto", "kontakt",
    "contactos", "contacts", "contato", "contatos", "contatti", "kontakte",
  ],
  job: [
    "cargo", "puesto", "rol", "role", "rolle", "título", "titulo", "title",
    "job", "position", "poste", "fonction", "ruolo", "carica", "posizione",
    "função", "funcao", "papel", "stelle", "bereich", "área", "area",
  ],
  country: ["país", "pais", "country", "pays", "paese", "land"],
  email: ["email", "e-mail", "correo", "correio", "mail", "courriel"],
  meetingWith: [
    "reunión con", "reunion con", "meeting with",
    "reunião com", "reuniao com", "riunione con", "incontro con",
    "réunion avec", "reunion avec", "rendez-vous avec",
    "meeting mit", "besprechung mit", "termin mit",
  ],
} as const;

/** Plantilla por defecto (español); la guía usa i18n `calendar.guide.template_example`. */
export const CALENDAR_MEETING_FORMAT_EXAMPLE = `Empresa: OXCCU
Contacto 1: James Girling
Cargo 1: CEO
Email 1: james@oxccu.com
Contacto 2: María López
Cargo 2: CTO
Email 2: maria@oxccu.com
País 2: Chile`;

/** Ejemplos de asunto (solo empresa) mostrados en la guía de calendario. */
export const CALENDAR_MEETING_SUBJECT_EXAMPLES = [
  "Reunión comercial — Tesla",
  "Reunión con Acme Corp",
  "Meeting with Acme Corp",
  "Réunion avec Acme Corp",
] as const;

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

const PERSON_LABELS_RE = CALENDAR_FIELD_LABELS.person.map(escapeRegex).join("|");

/**
 * Detecta campos persona en la descripción (multi-idioma). Replica `person_hint_regex_source()`
 * de calendar_meeting_labels.py, que es la fuente de verdad:
 * - «Contacto: Ana», «Contacto 1: Ana», «Contactos: …» en cualquier parte;
 * - «Contacto 2 - Ana» solo a inicio de línea, con espacio tras el guion;
 * - «Reunión con Ana».
 * La etiqueta sola, sin nombre ni correo detrás, no cuenta: el backend no extrae nada de ella.
 */
const PERSON_HINT_RE = new RegExp(
  `(?:${PERSON_LABELS_RE})\\s*(?:\\d+\\s*)?:\\s*\\S|` +
    `(?:^|\\n)[ \\t]*(?:${PERSON_LABELS_RE})[ \\t]*(?:\\d+[ \\t]*)?[-–—][ \\t]+\\S|` +
    `(?:${CALENDAR_FIELD_LABELS.meetingWith.map(escapeRegex).join("|")})\\s+\\S`,
  "i"
);

/** ¿La descripción trae un contacto que el backend pueda extraer? Decide el aviso del detalle. */
export function descriptionHasPersonHint(descripcion: string | undefined | null): boolean {
  const d = (descripcion || "").trim();
  if (!d) return false;
  return PERSON_HINT_RE.test(d);
}

export function descriptionHasCompanyHint(descripcion: string | undefined | null): boolean {
  const d = (descripcion || "").trim();
  if (!d) return false;
  const re = new RegExp(
    `(?:${CALENDAR_FIELD_LABELS.company.map(escapeRegex).join("|")})\\s*:`,
    "i"
  );
  return re.test(d);
}

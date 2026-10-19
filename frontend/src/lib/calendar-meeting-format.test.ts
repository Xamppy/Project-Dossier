import { describe, expect, it } from "vitest";
import { CALENDAR_FIELD_LABELS, descriptionHasPersonHint } from "./calendar-meeting-format";

// La fuente de verdad es backend/src/dossier/services/calendar_meeting_labels.py: el aviso
// «No se detecta contacto» promete que solo se generará el dossier de empresa, así que la
// detección del frontend debe coincidir con lo que el backend extrae (BUG-2026-10-19-04).

const POSITIVOS: [string, string][] = [
  ["caso del hallazgo: «Contacto 1: Nombre <correo>»", "Empresa: Acme\nContacto 1: Ana Pérez <ana@acme.test>"],
  ["«Contacto 1:» con varios contactos", "Contacto 1: James Girling\nCargo 1: CEO\nContacto 2: María López"],
  ["«Contacto:» sin número", "Empresa: Acme\nContacto: Ana Pérez"],
  ["«Contacto 2 -» con guion", "Empresa: Acme\nContacto 2 - María López"],
  ["«Contacto 2 –» con raya", "Contacto 2 – María López"],
  ["«Contacto - Ana» sin número", "Contacto - Ana Pérez"],
  ["«Contactos:» en plural", "Contactos: Ana Pérez, Luis Soto"],
  ["«Contact 1:» en inglés", "Company: Acme\nContact 1: John Smith"],
  ["«Contacts:» en inglés", "Contacts: John Smith"],
  ["«Contato:» en portugués", "Empresa: Acme\nContato: João Silva"],
  ["«Contato 1:» en portugués", "Contato 1: João Silva"],
  ["«Contatto:» en italiano", "Azienda: NoonDalton Contatto: Edward Dalton"],
  ["«Kontakt:» en alemán", "Unternehmen: Acme\nKontakt: Hans Müller"],
  ["«Kontakt 1:» en alemán", "Kontakt 1: Hans Müller"],
  ["«Nombre:»", "Nombre: Ana Pérez"],
  ["etiqueta en mayúsculas", "CONTACTO 1: ANA PÉREZ"],
  ["espacio antes de los dos puntos", "Contacto 1 : Ana Pérez"],
  ["«Contacto 2 -» con sangría", "Empresa: Acme\n   Contacto 2 - María López"],
  ["valor en la línea siguiente, como acepta el backend", "Contacto:\nAna Pérez"],
  ["«Reunión con» en la descripción", "Reunión con Ana Pérez"],
];

const NEGATIVOS: [string, string][] = [
  ["solo empresa", "Empresa: Acme"],
  ["texto libre sin etiqueta", "Revisar propuesta comercial y próximos pasos"],
  ["«Contacto 1:» sin nombre ni correo", "Empresa: Acme\nContacto 1:"],
  ["«Contacto:» sin nombre ni correo", "Empresa: Acme\nContacto:   "],
  ["«Contacto 2 -» sin valor", "Empresa: Acme\nContacto 2 - "],
  ["guion a mitad de frase, no a inicio de línea", "Secuenciación del genome - análisis"],
  ["guion pegado al valor", "Contacto 2 -María"],
  ["palabra «contacto» sin separador", "Pendiente de contacto con el cliente"],
  ["«Contacto 2» sin separador", "Contacto 2 María López"],
  ["vacía", ""],
  ["solo espacios", "   \n  "],
];

describe("descriptionHasPersonHint", () => {
  it.each(POSITIVOS)("detecta contacto: %s", (_caso, descripcion) => {
    expect(descriptionHasPersonHint(descripcion)).toBe(true);
  });

  it.each(NEGATIVOS)("no detecta contacto: %s", (_caso, descripcion) => {
    expect(descriptionHasPersonHint(descripcion)).toBe(false);
  });

  it("tolera null y undefined", () => {
    expect(descriptionHasPersonHint(null)).toBe(false);
    expect(descriptionHasPersonHint(undefined)).toBe(false);
  });
});

describe("CALENDAR_FIELD_LABELS.person", () => {
  it("incluye las variantes plurales y de los idiomas del dashboard", () => {
    for (const label of ["contactos", "contacts", "contato", "contatos", "contatti", "kontakte"]) {
      expect(CALENDAR_FIELD_LABELS.person).toContain(label);
    }
  });
});

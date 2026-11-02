import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createTranslator } from "@/i18n";
import { formatLongDate } from "@/lib/format";
import EmailDossierPanel from "./EmailDossierPanel";

// S6.1 · CA20: panel «Enviar por correo» del detalle del dossier, con el cliente HTTP real
// detrás de un `fetch` simulado.

const PREFS = { locale: "es" as const, timezone: "UTC" };

vi.mock("@/providers/PreferencesProvider", () => {
  const t = createTranslator("es");
  return {
    useTranslation: () => ({
      t,
      locale: "es",
      preferences: { locale: "es", timezone: "UTC", outputLanguage: "match", dateFormat: "dd/mm/yyyy" },
    }),
  };
});

const t = createTranslator("es");
const API = "https://api.dossier.test";
const ENVIADO_EL = "2026-11-02T12:00:00+00:00";

type Llamada = { method: string; url: string };
let llamadas: Llamada[];
let respuesta: () => Response;

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

beforeEach(() => {
  llamadas = [];
  respuesta = () =>
    json({
      dossier_id: "d-1",
      email_sent: true,
      email_sent_at: ENVIADO_EL,
      email_recipients: ["yo@example.com"],
    });
  vi.stubEnv("NEXT_PUBLIC_API_URL", API);
  localStorage.setItem("dossier_access_token", "tok");
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      llamadas.push({ method: init?.method ?? "GET", url: String(input) });
      return respuesta();
    }),
  );
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

function Panel(props: Partial<React.ComponentProps<typeof EmailDossierPanel>>) {
  return (
    <EmailDossierPanel
      dossierId="d-1"
      available
      complete
      userEmail="yo@example.com"
      initialDelivery={{ sent: false, sent_at: null, recipients: [] }}
      {...props}
    />
  );
}

describe("EmailDossierPanel · CA20", () => {
  it("muestra a qué correo se envía y que todavía no se envió", () => {
    render(<Panel />);

    expect(screen.getByRole("heading", { name: t("dossiers.email_title") })).toBeInTheDocument();
    expect(screen.getByText(t("dossiers.email_hint", { email: "yo@example.com" }))).toBeInTheDocument();
    expect(screen.getByText(t("dossiers.email_never_sent"))).toBeInTheDocument();
  });

  it("muestra el último envío con fecha y destinatarios", () => {
    render(<Panel initialDelivery={{ sent: true, sent_at: ENVIADO_EL, recipients: ["a@example.com", "b@example.com"] }} />);

    expect(
      screen.getByText(
        t("dossiers.email_last_sent", {
          date: formatLongDate(ENVIADO_EL, PREFS),
          recipients: "a@example.com, b@example.com",
        }),
      ),
    ).toBeInTheDocument();
  });

  it("el botón envía, avisa del éxito y actualiza el último envío", async () => {
    const user = userEvent.setup();
    render(<Panel />);

    await user.click(screen.getByRole("button", { name: t("dossiers.email_button") }));

    expect(llamadas).toEqual([{ method: "POST", url: `${API}/dossiers/d-1/email` }]);
    expect(await screen.findByRole("status")).toHaveTextContent(
      t("dossiers.email_sent_ok", { email: "yo@example.com" }),
    );
    expect(
      screen.getByText(
        t("dossiers.email_last_sent", { date: formatLongDate(ENVIADO_EL, PREFS), recipients: "yo@example.com" }),
      ),
    ).toBeInTheDocument();
  });

  it("mientras envía, el botón se desactiva y no admite un segundo clic", async () => {
    let soltar: (r: Response) => void = () => {};
    respuesta = () => new Promise<Response>((r) => (soltar = r)) as unknown as Response;
    const user = userEvent.setup();
    render(<Panel />);

    await user.click(screen.getByRole("button", { name: t("dossiers.email_button") }));
    const enviando = screen.getByRole("button", { name: t("dossiers.email_sending") });
    expect(enviando).toBeDisabled();
    await user.click(enviando);
    expect(llamadas).toHaveLength(1);

    soltar(json({ dossier_id: "d-1", email_sent: true, email_sent_at: ENVIADO_EL, email_recipients: ["yo@example.com"] }));
    expect(await screen.findByRole("button", { name: t("dossiers.email_button") })).toBeEnabled();
  });

  it.each([
    [429, "dossiers.email_error_too_soon"],
    [503, "dossiers.email_error_unavailable"],
    [502, "dossiers.email_error_failed"],
    [409, "dossiers.email_error_not_complete"],
  ] as const)("un %i muestra su error traducido", async (status, clave) => {
    respuesta = () => json({ detail: "texto del servidor" }, status);
    const user = userEvent.setup();
    render(<Panel />);

    await user.click(screen.getByRole("button", { name: t("dossiers.email_button") }));

    expect(await screen.findByRole("alert")).toHaveTextContent(t(clave));
    expect(screen.getByText(t("dossiers.email_never_sent"))).toBeInTheDocument();
  });

  it.each([
    ["sin envío disponible", { available: false }],
    ["con el dossier sin completar", { complete: false }],
    ["sin correo de usuario", { userEmail: null }],
  ])("no aparece %s", (_caso, props) => {
    const { container } = render(<Panel {...props} />);

    expect(container).toBeEmptyDOMElement();
  });
});

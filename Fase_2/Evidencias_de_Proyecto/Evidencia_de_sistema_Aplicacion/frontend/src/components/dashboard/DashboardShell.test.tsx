import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createTranslator } from "@/i18n";
import DashboardShell from "./DashboardShell";

// BUG-2026-10-19-03: a 375 px el armazón del dashboard tenía `ml-64` fijo y la
// barra lateral siempre visible, lo que desplazaba la página en horizontal.

const h = vi.hoisted(() => ({ pathname: "/dashboard" }));

vi.mock("next/navigation", () => ({
  usePathname: () => h.pathname,
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));
vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    onClick,
    className,
    ...rest
  }: {
    href: string;
    children: React.ReactNode;
    onClick?: (e: React.MouseEvent<HTMLAnchorElement>) => void;
    className?: string;
  }) => (
    <a
      href={href}
      className={className}
      {...rest}
      onClick={(e) => {
        e.preventDefault();
        onClick?.(e);
      }}
    >
      {children}
    </a>
  ),
}));
vi.mock("@/providers/PreferencesProvider", () => {
  const t = createTranslator("es");
  return {
    useTranslation: () => ({ t, locale: "es", preferences: { locale: "es" } }),
    usePreferences: () => ({ t, preferences: { locale: "es" } }),
  };
});
vi.mock("@/lib/dossier-api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/dossier-api")>();
  return { ...actual, getStoredAccessToken: () => null };
});
vi.mock("@/hooks/useAuthMe", () => ({
  AUTH_ME_CHANGED_EVENT: "dossier:auth-me-changed",
  useAuthMe: () => ({ canMutate: true, user: null }),
}));
vi.mock("@/components/dashboard/NotificationBell", () => ({ default: () => null }));

const ETIQUETA_ABRIR = "Abrir menú de navegación";

function montar() {
  return render(
    <DashboardShell>
      <p>contenido</p>
    </DashboardShell>,
  );
}

function botonMenu() {
  return screen.getByRole("button", { name: ETIQUETA_ABRIR });
}

function barraLateral() {
  return document.getElementById("dashboard-sidebar")!;
}

beforeEach(() => {
  h.pathname = "/dashboard";
});

describe("DashboardShell · contenido principal", () => {
  it("el main deja el margen de la barra solo desde md", () => {
    montar();
    const main = screen.getByRole("main");
    const clases = main.className.split(/\s+/);
    expect(clases).toContain("md:ml-64");
    expect(clases).not.toContain("ml-64");
    expect(main).toHaveTextContent("contenido");
  });

  it("el main no puede ensanchar el documento", () => {
    montar();
    const clases = screen.getByRole("main").className.split(/\s+/);
    expect(clases).toContain("min-w-0");
  });
});

describe("DashboardShell · botón de menú", () => {
  it("existe, tiene etiqueta traducida y empieza cerrado", () => {
    montar();
    const boton = botonMenu();
    expect(boton).toHaveAttribute("aria-expanded", "false");
    expect(boton).toHaveAttribute("aria-controls", "dashboard-sidebar");
  });

  it("solo se muestra por debajo de md", () => {
    montar();
    const barra = botonMenu().closest("header")!;
    expect(barra.className.split(/\s+/)).toContain("md:hidden");
  });

  it("la etiqueta se traduce en los demás idiomas", () => {
    expect(createTranslator("en")("nav.open_menu")).toBe("Open navigation menu");
    expect(createTranslator("en-gb")("nav.open_menu")).toBe("Open navigation menu");
    // Sin traducción propia, el traductor cae al inglés: eso no cuenta.
    for (const locale of ["de", "fr", "it", "pt"] as const) {
      const t = createTranslator(locale);
      expect(t("nav.open_menu")).not.toBe("Open navigation menu");
      expect(t("nav.close_menu")).not.toBe("Close navigation menu");
      expect(t("nav.sidebar_label")).not.toBe("Navigation");
    }
  });
});

describe("DashboardShell · cajón lateral en móvil", () => {
  it("cerrado, la barra queda fuera de pantalla y fuera del orden de foco en móvil", () => {
    montar();
    const clases = barraLateral().className.split(/\s+/);
    expect(clases).toContain("max-md:-translate-x-full");
    expect(clases).toContain("max-md:invisible");
    expect(clases).toContain("md:translate-x-0");
  });

  it("al abrir, el cajón aparece, se marca como diálogo y recibe el foco", async () => {
    const user = userEvent.setup();
    montar();
    await user.click(botonMenu());

    expect(botonMenu()).toHaveAttribute("aria-expanded", "true");
    const cajon = screen.getByRole("dialog", { name: "Navegación" });
    expect(cajon).toBe(barraLateral());
    const clases = cajon.className.split(/\s+/);
    expect(clases).not.toContain("max-md:-translate-x-full");
    expect(clases).not.toContain("max-md:invisible");
    expect(cajon.contains(document.activeElement)).toBe(true);
    expect(within(cajon).getByRole("button", { name: "Cerrar menú de navegación" })).toBeInTheDocument();
  });

  it("al abrir, la visibilidad no se anima: el navegador no enfoca un elemento aún oculto", async () => {
    // jsdom no aplica CSS, así que el foco funciona aquí aunque en Chrome falle:
    // con `visibility` en la transición, el cajón sigue `hidden` en el instante
    // en que se llama a focus() y el foco se queda en el botón de menú.
    const user = userEvent.setup();
    montar();
    await user.click(botonMenu());
    const clases = barraLateral().className;
    expect(clases).not.toMatch(/transition-\[[^\]]*visibility/);
    expect(clases).not.toMatch(/\[transition:[^\]]*visibility_0s_linear_\d/);
  });

  it("al cerrar, la visibilidad cambia después del deslizamiento", () => {
    montar();
    expect(barraLateral().className).toMatch(
      /max-md:\[transition:transform_200ms_ease-out,visibility_0s_linear_200ms\]/,
    );
  });

  it("Escape cierra el cajón y devuelve el foco al botón de menú", async () => {
    const user = userEvent.setup();
    montar();
    await user.click(botonMenu());
    await user.keyboard("{Escape}");

    expect(botonMenu()).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(botonMenu()).toHaveFocus();
  });

  it("el botón de cerrar del cajón lo cierra", async () => {
    const user = userEvent.setup();
    montar();
    await user.click(botonMenu());
    await user.click(screen.getByRole("button", { name: "Cerrar menú de navegación" }));

    expect(botonMenu()).toHaveAttribute("aria-expanded", "false");
    expect(botonMenu()).toHaveFocus();
  });

  it("hacer clic en un enlace de navegación cierra el cajón", async () => {
    const user = userEvent.setup();
    montar();
    await user.click(botonMenu());
    const cajon = screen.getByRole("dialog");
    await user.click(within(cajon).getByRole("link", { name: "Mis Dossiers" }));

    expect(botonMenu()).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("el fondo oscuro cierra el cajón al tocarlo", async () => {
    const user = userEvent.setup();
    montar();
    await user.click(botonMenu());
    await user.click(screen.getByTestId("dashboard-sidebar-backdrop"));

    expect(botonMenu()).toHaveAttribute("aria-expanded", "false");
  });

  it("un cambio de ruta cierra el cajón", async () => {
    const user = userEvent.setup();
    const { rerender } = montar();
    await user.click(botonMenu());
    h.pathname = "/dashboard/settings";
    rerender(
      <DashboardShell>
        <p>contenido</p>
      </DashboardShell>,
    );

    expect(botonMenu()).toHaveAttribute("aria-expanded", "false");
  });
});

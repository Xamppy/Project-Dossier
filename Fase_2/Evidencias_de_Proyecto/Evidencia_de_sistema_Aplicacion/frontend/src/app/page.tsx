import { redirect } from "next/navigation";

/**
 * La raíz del sitio lleva directo al inicio de sesión (sin landing de roadmap).
 */
export default function Home() {
  redirect("/login");
}

export default function ThemeScript() {
  const script = `(function(){try{var raw=localStorage.getItem('dossier-preferences');var p=raw?JSON.parse(raw):{};var t=p.theme||localStorage.getItem('dossier-theme')||'dark';if(t==='system'){t=window.matchMedia('(prefers-color-scheme: light)').matches?'light':'dark';}document.documentElement.setAttribute('data-theme',t);var l=p.locale||'es';document.documentElement.lang=l;}catch(e){document.documentElement.setAttribute('data-theme','dark');document.documentElement.lang='es';}})();`;

  return (
    <script
      dangerouslySetInnerHTML={{ __html: script }}
      suppressHydrationWarning
    />
  );
}

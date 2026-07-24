"""Páginas legales públicas — /privacy y /terms.

ced-castillo.com apunta hoy al servicio API; Google OAuth exige esas URLs
exactas. El frontend Next también las sirve en /privacy y /terms.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["legal"])


def _page(title: str, body_html: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{title} — CED</title>
  <style>
    :root {{ color-scheme: dark; }}
    body {{
      margin: 0; font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
      background: #000; color: #b8f0ff; line-height: 1.65;
    }}
    header {{
      border-bottom: 1px solid rgba(0,229,255,.2);
      padding: 1rem 1.25rem; display: flex; gap: 1rem; align-items: center;
      justify-content: space-between; flex-wrap: wrap;
    }}
    a {{ color: #22d3ee; text-decoration: none; }}
    a:hover {{ color: #a5f3fc; }}
    main {{ max-width: 46rem; margin: 0 auto; padding: 2rem 1.25rem 3rem; }}
    h1 {{ font-size: 1.35rem; color: #cffafe; margin: 0 0 .35rem; }}
    .updated {{ color: #0891b2; font-size: .9rem; margin-bottom: 1.75rem; }}
    h2 {{ font-size: .95rem; color: #67e8f9; margin: 1.75rem 0 .5rem; }}
    p, li {{ font-size: .95rem; color: rgba(207,250,254,.9); }}
    ul {{ padding-left: 1.25rem; }}
    li {{ margin: .4rem 0; }}
    footer {{ margin-top: 2.5rem; padding-top: 1rem; border-top: 1px solid rgba(8,145,178,.35);
      text-align: center; font-size: .8rem; color: #0e7490; }}
  </style>
</head>
<body>
  <header>
    <a href="/"><strong>CED</strong></a>
    <nav>
      <a href="/privacy">Privacidad</a>
      &nbsp;·&nbsp;
      <a href="/terms">Términos</a>
    </nav>
  </header>
  <main>
{body_html}
    <footer>
      <a href="/privacy">Privacidad</a> · <a href="/terms">Términos</a>
    </footer>
  </main>
</body>
</html>"""


PRIVACY_BODY = """
    <h1>Politica de Privacidad de CED</h1>
    <p class="updated">Ultima actualizacion: 22 de julio de 2026</p>

    <h2>1. Quienes somos</h2>
    <p>CED es un asistente virtual inteligente que ayuda a los usuarios a gestionar tareas de negocio y personales mediante voz, texto e imagenes. Esta politica explica que informacion recopilamos, como la usamos y como la protegemos.</p>
    <p>Contacto: keini5868@gmail.com</p>

    <h2>2. Informacion que recopilamos</h2>
    <p>Dependiendo de las funciones que actives, CED puede acceder a:</p>
    <ul>
      <li>Datos de cuenta: nombre, correo electronico, y credenciales de autenticacion (a traves de Google OAuth).</li>
      <li>Camara y microfono: CED puede acceder a tu camara y microfono en tiempo real cuando actives el modo de voz o vision, para poder escucharte y ver lo que le muestras.</li>
      <li>Imagenes que subas: las imagenes que subas para analisis, edicion o generacion de variaciones.</li>
      <li>Ubicacion: cuando uses el Modo Conducir (mapa y GPS), CED accede a tu ubicacion en tiempo real para brindarte navegacion.</li>
      <li>Redes sociales: si conectas tus cuentas de Facebook o Instagram, CED puede publicar contenido en tu nombre unicamente cuando tu lo autorices explicitamente.</li>
      <li>Informacion de pago: procesada de forma segura a traves de Stripe; CED no almacena directamente los datos completos de tu tarjeta.</li>
      <li>Historial de conversacion: guardamos tus conversaciones con CED para darte continuidad entre sesiones y mejorar la experiencia.</li>
    </ul>

    <h2>3. Como usamos tu informacion</h2>
    <p>Usamos la informacion recopilada exclusivamente para:</p>
    <ul>
      <li>Ejecutar las acciones que tu le solicitas a CED (crear un recordatorio, generar una imagen, publicar en redes, etc.)</li>
      <li>Mejorar la precision y utilidad del asistente.</li>
      <li>Procesar pagos y gestionar tu suscripcion.</li>
      <li>Brindarte soporte cuando lo solicites.</li>
    </ul>
    <p>No vendemos ni compartimos tu informacion personal con terceros con fines publicitarios.</p>

    <h2>4. Con quien compartimos informacion</h2>
    <p>CED utiliza los siguientes servicios de terceros para funcionar, cada uno con sus propias politicas de privacidad:</p>
    <ul>
      <li>Google (OAuth de inicio de sesion): para autenticar tu cuenta cuando eliges entrar con Google.</li>
      <li>Meta (Facebook, Instagram): para publicaciones que tu autorices.</li>
      <li>Stripe: para procesamiento de pagos.</li>
      <li>Proveedores de inteligencia artificial (incluyendo modelos de lenguaje y generacion de voz/imagen) utilizados para procesar tus solicitudes.</li>
    </ul>
    <p>Estos proveedores procesan la informacion unicamente en la medida necesaria para prestar el servicio solicitado.</p>

    <h2>5. Seguridad</h2>
    <p>Implementamos medidas tecnicas razonables para proteger tu informacion, incluyendo conexiones cifradas (HTTPS) y autenticacion segura via OAuth. Sin embargo, ningun sistema es cien por ciento infalible, y no podemos garantizar seguridad absoluta.</p>

    <h2>6. Tus derechos</h2>
    <p>Puedes, en cualquier momento:</p>
    <ul>
      <li>Solicitar acceso a la informacion que tenemos sobre ti.</li>
      <li>Solicitar la eliminacion de tu cuenta y datos asociados.</li>
      <li>Revocar el acceso de CED a tu cuenta de Google o Meta desde la configuracion de esas plataformas.</li>
      <li>Contactarnos con cualquier pregunta sobre tus datos, escribiendo a keini5868@gmail.com.</li>
    </ul>

    <h2>7. Retencion de datos</h2>
    <p>Conservamos tu informacion mientras tu cuenta este activa. Si solicitas la eliminacion de tu cuenta, eliminaremos tus datos personales dentro de un plazo razonable, salvo que la ley exija conservarlos por mas tiempo.</p>

    <h2>8. Menores de edad</h2>
    <p>CED no esta dirigido a menores de 13 anos. No recopilamos conscientemente informacion de menores de esa edad.</p>

    <h2>9. Cambios a esta politica</h2>
    <p>Podemos actualizar esta politica ocasionalmente. Notificaremos cambios importantes publicando la nueva version en esta misma pagina con la fecha de actualizacion correspondiente.</p>

    <h2>10. Contacto</h2>
    <p>Si tienes preguntas sobre esta politica de privacidad, contactanos en: keini5868@gmail.com</p>
"""

TERMS_BODY = """
    <h1>Terminos de Servicio de CED</h1>
    <p class="updated">Ultima actualizacion: 22 de julio de 2026</p>

    <h2>1. Aceptacion de los terminos</h2>
    <p>Al crear una cuenta o usar CED, aceptas estos Terminos de Servicio. Si no estas de acuerdo, no debes usar el servicio.</p>

    <h2>2. Descripcion del servicio</h2>
    <p>CED es un asistente virtual que ofrece, entre otras funciones: asistencia por voz y texto, analisis y generacion de imagenes, generacion de documentos PDF, publicacion en redes sociales conectadas, navegacion con mapa y GPS, y modulos adicionales de analisis de negocio.</p>

    <h2>3. Cuentas de usuario</h2>
    <ul>
      <li>Debes proporcionar informacion veridica al registrarte.</li>
      <li>Eres responsable de mantener la confidencialidad de tu cuenta y contrasena.</li>
      <li>Debes notificarnos de inmediato ante cualquier uso no autorizado de tu cuenta.</li>
    </ul>

    <h2>4. Planes y pagos</h2>
    <ul>
      <li>CED ofrece un plan gratuito y planes de suscripcion pagados con distintos niveles de acceso y limites de uso.</li>
      <li>Los pagos se procesan a traves de Stripe.</li>
      <li>Las suscripciones se renuevan automaticamente segun el ciclo de facturacion elegido, salvo cancelacion previa por parte del usuario.</li>
      <li>Los creditos de recarga, una vez adquiridos, no son reembolsables salvo que la ley aplicable indique lo contrario.</li>
      <li>Nos reservamos el derecho de modificar precios con aviso previo razonable.</li>
    </ul>

    <h2>5. Uso aceptable</h2>
    <p>Al usar CED, te comprometes a NO:</p>
    <ul>
      <li>Utilizar el servicio para actividades ilegales, fraudulentas o daninas.</li>
      <li>Intentar vulnerar la seguridad del sistema o acceder a cuentas ajenas.</li>
      <li>Usar las integraciones de redes sociales para enviar spam, contenido enganoso o no autorizado.</li>
      <li>Usar el servicio para generar contenido que infrinja derechos de autor, difame, acose o incite violencia.</li>
      <li>Realizar ingenieria inversa o intentar extraer el codigo fuente del sistema.</li>
    </ul>
    <p>Nos reservamos el derecho de suspender o cancelar cuentas que incumplan estas condiciones.</p>

    <h2>6. Contenido generado</h2>
    <p>El contenido que generes a traves de CED (imagenes, PDFs, textos) es tuyo, siempre que hayas cumplido con estos terminos y con las politicas de los proveedores de IA subyacentes.</p>
    <p>CED no garantiza que el contenido generado por inteligencia artificial este siempre libre de errores; se recomienda verificar informacion critica antes de tomar decisiones basadas unicamente en el.</p>

    <h2>7. Integraciones de terceros</h2>
    <p>CED se conecta con servicios de terceros como Google, Meta y Stripe. Tu uso de esas integraciones tambien esta sujeto a los terminos de servicio de esos proveedores. No somos responsables de interrupciones o cambios en dichos servicios que esten fuera de nuestro control.</p>

    <h2>8. Limitacion de responsabilidad</h2>
    <p>CED se ofrece &quot;tal cual&quot; y &quot;segun disponibilidad&quot;. En la maxima medida permitida por la ley, no seremos responsables de danos indirectos, incidentales o consecuentes derivados del uso o la imposibilidad de uso del servicio, incluyendo perdidas de negocio, datos o ganancias.</p>

    <h2>9. Modificaciones al servicio</h2>
    <p>Podemos modificar, suspender o discontinuar funciones de CED en cualquier momento, con o sin previo aviso, especialmente durante fases de prueba piloto de nuevas funciones.</p>

    <h2>10. Cancelacion</h2>
    <p>Puedes cancelar tu cuenta en cualquier momento. Nos reservamos el derecho de suspender o cancelar cuentas que violen estos terminos.</p>

    <h2>11. Cambios a estos terminos</h2>
    <p>Podemos actualizar estos terminos ocasionalmente. Notificaremos cambios importantes publicando la nueva version en esta misma pagina con la fecha de actualizacion correspondiente. El uso continuado de CED despues de dichos cambios constituye tu aceptacion de los nuevos terminos.</p>

    <h2>12. Contacto</h2>
    <p>Para preguntas sobre estos Terminos de Servicio, contactanos en: keini5868@gmail.com</p>
"""


@router.get("/privacy", response_class=HTMLResponse)
def privacy_policy() -> HTMLResponse:
    return HTMLResponse(
        content=_page("Politica de Privacidad", PRIVACY_BODY),
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.get("/terms", response_class=HTMLResponse)
def terms_of_service() -> HTMLResponse:
    return HTMLResponse(
        content=_page("Terminos de Servicio", TERMS_BODY),
        headers={"Cache-Control": "public, max-age=300"},
    )

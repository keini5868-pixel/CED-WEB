import type { Metadata } from "next";

import { LegalPageShell } from "@/components/layout/LegalPageShell";

export const metadata: Metadata = {
  title: "Términos de Servicio — CED",
  description:
    "Términos de Servicio de CED (Castillo de la Evolución Digital). Última actualización: 22 de julio de 2026.",
  robots: { index: true, follow: true },
};

export default function TermsPage() {
  return (
    <LegalPageShell
      title="Terminos de Servicio de CED"
      updated="Ultima actualizacion: 22 de julio de 2026"
    >
      <section>
        <h2>1. Aceptacion de los terminos</h2>
        <p>
          Al crear una cuenta o usar CED, aceptas estos Terminos de Servicio. Si
          no estas de acuerdo, no debes usar el servicio.
        </p>
      </section>

      <section>
        <h2>2. Descripcion del servicio</h2>
        <p>
          CED es un asistente virtual que ofrece, entre otras funciones:
          asistencia por voz y texto, analisis y generacion de imagenes,
          generacion de documentos PDF, publicacion en redes sociales
          conectadas, navegacion con mapa y GPS, y modulos adicionales de
          analisis de negocio.
        </p>
      </section>

      <section>
        <h2>3. Cuentas de usuario</h2>
        <ul>
          <li>Debes proporcionar informacion veridica al registrarte.</li>
          <li>
            Eres responsable de mantener la confidencialidad de tu cuenta y
            contrasena.
          </li>
          <li>
            Debes notificarnos de inmediato ante cualquier uso no autorizado de
            tu cuenta.
          </li>
        </ul>
      </section>

      <section>
        <h2>4. Planes y pagos</h2>
        <ul>
          <li>
            CED ofrece un plan gratuito y planes de suscripcion pagados con
            distintos niveles de acceso y limites de uso.
          </li>
          <li>Los pagos se procesan a traves de Stripe.</li>
          <li>
            Las suscripciones se renuevan automaticamente segun el ciclo de
            facturacion elegido, salvo cancelacion previa por parte del usuario.
          </li>
          <li>
            Los creditos de recarga, una vez adquiridos, no son reembolsables
            salvo que la ley aplicable indique lo contrario.
          </li>
          <li>
            Nos reservamos el derecho de modificar precios con aviso previo
            razonable.
          </li>
        </ul>
      </section>

      <section>
        <h2>5. Uso aceptable</h2>
        <p>Al usar CED, te comprometes a NO:</p>
        <ul>
          <li>
            Utilizar el servicio para actividades ilegales, fraudulentas o
            daninas.
          </li>
          <li>
            Intentar vulnerar la seguridad del sistema o acceder a cuentas
            ajenas.
          </li>
          <li>
            Usar las integraciones de redes sociales para enviar spam, contenido
            enganoso o no autorizado.
          </li>
          <li>
            Usar el servicio para generar contenido que infrinja derechos de
            autor, difame, acose o incite violencia.
          </li>
          <li>
            Realizar ingenieria inversa o intentar extraer el codigo fuente del
            sistema.
          </li>
        </ul>
        <p>
          Nos reservamos el derecho de suspender o cancelar cuentas que
          incumplan estas condiciones.
        </p>
      </section>

      <section>
        <h2>6. Contenido generado</h2>
        <p>
          El contenido que generes a traves de CED (imagenes, PDFs, textos) es
          tuyo, siempre que hayas cumplido con estos terminos y con las
          politicas de los proveedores de IA subyacentes.
        </p>
        <p>
          CED no garantiza que el contenido generado por inteligencia artificial
          este siempre libre de errores; se recomienda verificar informacion
          critica antes de tomar decisiones basadas unicamente en el.
        </p>
      </section>

      <section>
        <h2>7. Integraciones de terceros</h2>
        <p>
          CED se conecta con servicios de terceros como Google, Meta y Stripe. Tu
          uso de esas integraciones tambien esta sujeto a los terminos de
          servicio de esos proveedores. No somos responsables de interrupciones
          o cambios en dichos servicios que esten fuera de nuestro control.
        </p>
      </section>

      <section>
        <h2>8. Limitacion de responsabilidad</h2>
        <p>
          CED se ofrece &quot;tal cual&quot; y &quot;segun disponibilidad&quot;. En la maxima
          medida permitida por la ley, no seremos responsables de danos
          indirectos, incidentales o consecuentes derivados del uso o la
          imposibilidad de uso del servicio, incluyendo perdidas de negocio,
          datos o ganancias.
        </p>
      </section>

      <section>
        <h2>9. Modificaciones al servicio</h2>
        <p>
          Podemos modificar, suspender o discontinuar funciones de CED en
          cualquier momento, con o sin previo aviso, especialmente durante fases
          de prueba piloto de nuevas funciones.
        </p>
      </section>

      <section>
        <h2>10. Cancelacion</h2>
        <p>
          Puedes cancelar tu cuenta en cualquier momento. Nos reservamos el
          derecho de suspender o cancelar cuentas que violen estos terminos.
        </p>
      </section>

      <section>
        <h2>11. Cambios a estos terminos</h2>
        <p>
          Podemos actualizar estos terminos ocasionalmente. Notificaremos
          cambios importantes publicando la nueva version en esta misma pagina
          con la fecha de actualizacion correspondiente. El uso continuado de
          CED despues de dichos cambios constituye tu aceptacion de los nuevos
          terminos.
        </p>
      </section>

      <section>
        <h2>12. Contacto</h2>
        <p>
          Para preguntas sobre estos Terminos de Servicio, contactanos en:
          keini5868@gmail.com
        </p>
      </section>
    </LegalPageShell>
  );
}

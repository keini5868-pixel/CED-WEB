import type { Metadata } from "next";

import { LegalPageShell } from "@/components/layout/LegalPageShell";

export const metadata: Metadata = {
  title: "Política de Privacidad — CED",
  description:
    "Política de Privacidad de CED (Castillo de la Evolución Digital). Última actualización: 22 de julio de 2026.",
  robots: { index: true, follow: true },
};

export default function PrivacyPage() {
  return (
    <LegalPageShell
      title="Politica de Privacidad de CED"
      updated="Ultima actualizacion: 22 de julio de 2026"
    >
      <section>
        <h2>1. Quienes somos</h2>
        <p>
          CED es un asistente virtual inteligente que ayuda a los usuarios a
          gestionar tareas de negocio y personales mediante voz, texto e
          imagenes. Esta politica explica que informacion recopilamos, como la
          usamos y como la protegemos.
        </p>
        <p>Contacto: keini5868@gmail.com</p>
      </section>

      <section>
        <h2>2. Informacion que recopilamos</h2>
        <p>Dependiendo de las funciones que actives, CED puede acceder a:</p>
        <ul>
          <li>
            Datos de cuenta: nombre, correo electronico, y credenciales de
            autenticacion (a traves de Google OAuth).
          </li>
          <li>
            Camara y microfono: CED puede acceder a tu camara y microfono en
            tiempo real cuando actives el modo de voz o vision, para poder
            escucharte y ver lo que le muestras.
          </li>
          <li>
            Imagenes que subas: las imagenes que subas para analisis, edicion o
            generacion de variaciones.
          </li>
          <li>
            Ubicacion: cuando uses el Modo Conducir (mapa y GPS), CED accede a
            tu ubicacion en tiempo real para brindarte navegacion.
          </li>
          <li>
            Redes sociales: si conectas tus cuentas de Facebook o Instagram, CED
            puede publicar contenido en tu nombre unicamente cuando tu lo
            autorices explicitamente.
          </li>
          <li>
            Informacion de pago: procesada de forma segura a traves de Stripe;
            CED no almacena directamente los datos completos de tu tarjeta.
          </li>
          <li>
            Historial de conversacion: guardamos tus conversaciones con CED para
            darte continuidad entre sesiones y mejorar la experiencia.
          </li>
        </ul>
      </section>

      <section>
        <h2>3. Como usamos tu informacion</h2>
        <p>Usamos la informacion recopilada exclusivamente para:</p>
        <ul>
          <li>
            Ejecutar las acciones que tu le solicitas a CED (crear un
            recordatorio, generar una imagen, publicar en redes, etc.)
          </li>
          <li>Mejorar la precision y utilidad del asistente.</li>
          <li>Procesar pagos y gestionar tu suscripcion.</li>
          <li>Brindarte soporte cuando lo solicites.</li>
        </ul>
        <p>
          No vendemos ni compartimos tu informacion personal con terceros con
          fines publicitarios.
        </p>
      </section>

      <section>
        <h2>4. Con quien compartimos informacion</h2>
        <p>
          CED utiliza los siguientes servicios de terceros para funcionar, cada
          uno con sus propias politicas de privacidad:
        </p>
        <ul>
          <li>
            Google (OAuth de inicio de sesion): para autenticar tu cuenta cuando
            eliges entrar con Google.
          </li>
          <li>
            Meta (Facebook, Instagram): para publicaciones que tu autorices.
          </li>
          <li>Stripe: para procesamiento de pagos.</li>
          <li>
            Proveedores de inteligencia artificial (incluyendo modelos de
            lenguaje y generacion de voz/imagen) utilizados para procesar tus
            solicitudes.
          </li>
        </ul>
        <p>
          Estos proveedores procesan la informacion unicamente en la medida
          necesaria para prestar el servicio solicitado.
        </p>
      </section>

      <section>
        <h2>5. Seguridad</h2>
        <p>
          Implementamos medidas tecnicas razonables para proteger tu
          informacion, incluyendo conexiones cifradas (HTTPS) y autenticacion
          segura via OAuth. Sin embargo, ningun sistema es cien por ciento
          infalible, y no podemos garantizar seguridad absoluta.
        </p>
      </section>

      <section>
        <h2>6. Tus derechos</h2>
        <p>Puedes, en cualquier momento:</p>
        <ul>
          <li>Solicitar acceso a la informacion que tenemos sobre ti.</li>
          <li>Solicitar la eliminacion de tu cuenta y datos asociados.</li>
          <li>
            Revocar el acceso de CED a tu cuenta de Google o Meta desde la
            configuracion de esas plataformas.
          </li>
          <li>
            Contactarnos con cualquier pregunta sobre tus datos, escribiendo a
            keini5868@gmail.com.
          </li>
        </ul>
      </section>

      <section>
        <h2>7. Retencion de datos</h2>
        <p>
          Conservamos tu informacion mientras tu cuenta este activa. Si
          solicitas la eliminacion de tu cuenta, eliminaremos tus datos
          personales dentro de un plazo razonable, salvo que la ley exija
          conservarlos por mas tiempo.
        </p>
      </section>

      <section>
        <h2>8. Menores de edad</h2>
        <p>
          CED no esta dirigido a menores de 13 anos. No recopilamos
          conscientemente informacion de menores de esa edad.
        </p>
      </section>

      <section>
        <h2>9. Cambios a esta politica</h2>
        <p>
          Podemos actualizar esta politica ocasionalmente. Notificaremos
          cambios importantes publicando la nueva version en esta misma pagina
          con la fecha de actualizacion correspondiente.
        </p>
      </section>

      <section>
        <h2>10. Contacto</h2>
        <p>
          Si tienes preguntas sobre esta politica de privacidad, contactanos en:
          keini5868@gmail.com
        </p>
      </section>
    </LegalPageShell>
  );
}

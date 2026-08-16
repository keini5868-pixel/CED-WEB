"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const VERSES = [
  {
    text: "Todo lo puedo en Cristo que me fortalece.",
    ref: "Filipenses 4:13",
  },
  {
    text: "Encomienda a Jehová tu camino, y confía en él; y él hará.",
    ref: "Salmos 37:5",
  },
  {
    text: "Porque yo sé los pensamientos que tengo acerca de vosotros, dice Jehová, pensamientos de paz, y no de mal, para daros el fin que esperáis.",
    ref: "Jeremías 29:11",
  },
  {
    text: "Esfuérzate y sé valiente; no temas, ni desmayes, porque Jehová tu Dios estará contigo en dondequiera que vayas.",
    ref: "Josué 1:9",
  },
  {
    text: "Mas buscad primeramente el reino de Dios y su justicia, y todas estas cosas os serán añadidas.",
    ref: "Mateo 6:33",
  },
  {
    text: "El que labra su tierra se saciará de pan; mas el que sigue a los ociosos se llenará de pobreza.",
    ref: "Proverbios 28:19",
  },
  {
    text: "Fíate de Jehová de todo tu corazón, y no te apoyes en tu propia prudencia.",
    ref: "Proverbios 3:5",
  },
  {
    text: "Y todo lo que hagáis, hacedlo de corazón, como para el Señor y no para los hombres.",
    ref: "Colosenses 3:23",
  },
  {
    text: "El alma del perezoso desea, y nada alcanza; mas el alma de los diligentes será prosperada.",
    ref: "Proverbios 13:4",
  },
  {
    text: "Bástate mi gracia; porque mi poder se perfecciona en la debilidad.",
    ref: "2 Corintios 12:9",
  },
  {
    text: "Pero los que esperan a Jehová tendrán nuevas fuerzas; levantarán alas como las águilas; correrán, y no se cansarán; caminarán, y no se fatigarán.",
    ref: "Isaías 40:31",
  },
  {
    text: "No se aparte de tu boca este libro de la ley, sino que de día y de noche meditarás en él, para que guardes y hagas conforme a todo lo que en él está escrito; porque entonces harás prosperar tu camino, y todo te saldrá bien.",
    ref: "Josué 1:8",
  },
  {
    text: "Echa sobre Jehová tu carga, y él te sustentará; no dejará para siempre caído al justo.",
    ref: "Salmos 55:22",
  },
  {
    text: "Honra a Jehová con tus bienes, y con las primicias de todos tus frutos; y serán llenos tus graneros con abundancia.",
    ref: "Proverbios 3:9-10",
  },
  {
    text: "Mejor es lo poco con justicia que la muchedumbre de frutos sin derecho.",
    ref: "Proverbios 16:8",
  },
  {
    text: "Sabemos que a los que aman a Dios, todas las cosas les ayudan a bien.",
    ref: "Romanos 8:28",
  },
  {
    text: "La mano negligente empobrece; mas la mano de los diligentes enriquece.",
    ref: "Proverbios 10:4",
  },
  {
    text: "No nos cansemos, pues, de hacer bien; porque a su tiempo segaremos, si no desmayamos.",
    ref: "Gálatas 6:9",
  },
  {
    text: "Por tanto, os digo que todo lo que pidiereis orando, creed que lo recibiréis, y os vendrá.",
    ref: "Marcos 11:24",
  },
  {
    text: "Jehová es mi luz y mi salvación; ¿de quién temeré?",
    ref: "Salmos 27:1",
  },
  {
    text: "No temas, porque yo estoy contigo; no desmayes, porque yo soy tu Dios que te esfuerzo.",
    ref: "Isaías 41:10",
  },
  {
    text: "Jehová es mi pastor; nada me faltará.",
    ref: "Salmos 23:1",
  },
  {
    text: "Reconócelo en todos tus caminos, y él enderezará tus veredas.",
    ref: "Proverbios 3:6",
  },
  {
    text: "Mas a Dios gracias, el cual nos lleva siempre en triunfo en Cristo Jesús.",
    ref: "2 Corintios 2:14",
  },
  {
    text: "Deléitate asimismo en Jehová, y él te concederá las peticiones de tu corazón.",
    ref: "Salmos 37:4",
  },
  {
    text: "Pues no nos ha dado Dios espíritu de cobardía, sino de poder, de amor y de dominio propio.",
    ref: "2 Timoteo 1:7",
  },
  {
    text: "El que cree en mí, como dice la Escritura, de su interior correrán ríos de agua viva.",
    ref: "Juan 7:38",
  },
  {
    text: "Mi Dios, pues, suplirá todo lo que os falta conforme a sus riquezas en gloria en Cristo Jesús.",
    ref: "Filipenses 4:19",
  },
  {
    text: "Buscad a Jehová y su poder; buscad siempre su rostro.",
    ref: "1 Crónicas 16:11",
  },
  {
    text: "Porque para Dios no hay nada imposible.",
    ref: "Lucas 1:37",
  },
  {
    text: "Jehová peleará por vosotros, y vosotros estaréis tranquilos.",
    ref: "Éxodo 14:14",
  },
  {
    text: "Acerquémonos, pues, confiadamente al trono de la gracia, para alcanzar misericordia y hallar gracia para el oportuno socorro.",
    ref: "Hebreos 4:16",
  },
  {
    text: "Encomienda a Jehová tus obras, y tus pensamientos serán afirmados.",
    ref: "Proverbios 16:3",
  },
  {
    text: "Porque mejor es un día en tus atrios que mil fuera de ellos.",
    ref: "Salmos 84:10",
  },
  {
    text: "Y este es el testimonio: que Dios nos ha dado vida eterna; y esta vida está en su Hijo.",
    ref: "1 Juan 5:11",
  },
  {
    text: "Pedid, y se os dará; buscad, y hallaréis; llamad, y se os abrirá.",
    ref: "Mateo 7:7",
  },
  {
    text: "Creed en Jehová vuestro Dios, y estaréis seguros; creed a sus profetas, y seréis prosperados.",
    ref: "2 Crónicas 20:20",
  },
  {
    text: "El bueno alcanzará favor de Jehová.",
    ref: "Proverbios 12:2",
  },
  {
    text: "Bienaventurado el varón que no anduvo en consejo de malos.",
    ref: "Salmos 1:1",
  },
  {
    text: "Será como árbol plantado junto a corrientes de aguas, que da su fruto en su tiempo; y todo lo que hace, prosperará.",
    ref: "Salmos 1:3",
  },
  {
    text: "El que confía en sus riquezas caerá; mas los justos reverdecerán como ramas.",
    ref: "Proverbios 11:28",
  },
  {
    text: "Porque Jehová da la sabiduría, y de su boca viene el conocimiento y la inteligencia.",
    ref: "Proverbios 2:6",
  },
  {
    text: "Hijo mío, no te olvides de mi ley; porque largura de días y años de vida y paz te aumentarán.",
    ref: "Proverbios 3:1-2",
  },
  {
    text: "El temor de Jehová es el principio de la sabiduría.",
    ref: "Proverbios 9:10",
  },
  {
    text: "Que no pongan la esperanza en las riquezas, las cuales son inciertas, sino en el Dios vivo.",
    ref: "1 Timoteo 6:17",
  },
  {
    text: "Y todo lo que pidiereis al Padre en mi nombre, lo haré.",
    ref: "Juan 14:13",
  },
  {
    text: "El que siembra escasamente, también segará escasamente; y el que siembra generosamente, generosamente también segará.",
    ref: "2 Corintios 9:6",
  },
  {
    text: "Por nada estéis afanosos, sino sean conocidas vuestras peticiones delante de Dios en toda oración y ruego.",
    ref: "Filipenses 4:6",
  },
  {
    text: "Y la paz de Dios, que sobrepasa todo entendimiento, guardará vuestros corazones y vuestros pensamientos en Cristo Jesús.",
    ref: "Filipenses 4:7",
  },
  {
    text: "Esforzaos todos vosotros, pueblo de la tierra, dice Jehová, y trabajad; porque yo estoy con vosotros.",
    ref: "Hageo 2:4",
  },
  {
    text: "Mejor es el fin del negocio que su principio; mejor es el sufrido de espíritu que el altivo de espíritu.",
    ref: "Eclesiastés 7:8",
  },
  {
    text: "Dios es nuestro amparo y fortaleza, nuestro pronto auxilio en las tribulaciones.",
    ref: "Salmos 46:1",
  },
  {
    text: "Estad quietos, y conoced que yo soy Dios.",
    ref: "Salmos 46:10",
  },
  {
    text: "Este es el día que hizo Jehová; nos gozaremos y alegraremos en él.",
    ref: "Salmos 118:24",
  },
  {
    text: "Lámpara es a mis pies tu palabra, y lumbrera a mi camino.",
    ref: "Salmos 119:105",
  },
  {
    text: "Mi socorro viene de Jehová, que hizo los cielos y la tierra.",
    ref: "Salmos 121:2",
  },
  {
    text: "Para los hombres esto es imposible; mas para Dios todo es posible.",
    ref: "Mateo 19:26",
  },
  {
    text: "Venid a mí todos los que estáis trabajados y cargados, y yo os haré descansar.",
    ref: "Mateo 11:28",
  },
  {
    text: "Yo soy el camino, y la verdad, y la vida.",
    ref: "Juan 14:6",
  },
  {
    text: "Yo soy la luz del mundo; el que me sigue no andará en tinieblas.",
    ref: "Juan 8:12",
  },
  {
    text: "Gozaos en el Señor siempre. Otra vez digo: ¡Gozaos!",
    ref: "Filipenses 4:4",
  },
  {
    text: "Echando toda vuestra ansiedad sobre él, porque él tiene cuidado de vosotros.",
    ref: "1 Pedro 5:7",
  },
  {
    text: "El corazón del hombre piensa su camino; mas Jehová endereza sus pasos.",
    ref: "Proverbios 16:9",
  },
  {
    text: "Los pensamientos del diligente ciertamente tienden a la abundancia.",
    ref: "Proverbios 21:5",
  },
  {
    text: "¿Has visto hombre solícito en su trabajo? Delante de los reyes estará.",
    ref: "Proverbios 22:29",
  },
  {
    text: "Acuérdate de Jehová tu Dios, porque él te da el poder para hacer las riquezas.",
    ref: "Deuteronomio 8:18",
  },
  {
    text: "Sea la luz de Jehová nuestro Dios sobre nosotros, y confirma la obra de nuestras manos.",
    ref: "Salmos 90:17",
  },
  {
    text: "Tú guardarás en completa paz a aquel cuyo pensamiento en ti persevera.",
    ref: "Isaías 26:3",
  },
  {
    text: "En lo que requiere diligencia, no perezosos; fervientes en espíritu, sirviendo al Señor.",
    ref: "Romanos 12:11",
  },
  {
    text: "Si alguno de vosotros tiene falta de sabiduría, pídala a Dios, el cual da a todos abundantemente.",
    ref: "Santiago 1:5",
  },
  {
    text: "Por Jehová son ordenados los pasos del hombre, y él aprueba su camino.",
    ref: "Salmos 37:23",
  },
  {
    text: "Sobre toda cosa guardada, guarda tu corazón; porque de él mana la vida.",
    ref: "Proverbios 4:23",
  },
  {
    text: "He aquí que yo hago cosa nueva; pronto saldrá a luz.",
    ref: "Isaías 43:19",
  },
  {
    text: "Clama a mí, y yo te responderé, y te enseñaré cosas grandes y ocultas.",
    ref: "Jeremías 33:3",
  },
  {
    text: "El que habita al abrigo del Altísimo morará bajo la sombra del Omnipotente.",
    ref: "Salmos 91:1",
  },
  {
    text: "Así alumbre vuestra luz delante de los hombres, para que vean vuestras buenas obras.",
    ref: "Mateo 5:16",
  },
  {
    text: "Todo lo que te viniere a la mano para hacer, hazlo según tus fuerzas.",
    ref: "Eclesiastés 9:10",
  },
  {
    text: "Y todo lo que hacéis, sea de palabra o de hecho, hacedlo todo en el nombre del Señor Jesús.",
    ref: "Colosenses 3:17",
  },
  {
    text: "Gustad, y ved que es bueno Jehová; dichoso el hombre que confía en él.",
    ref: "Salmos 34:8",
  },
] as const;

const ROTATE_MS = 60_000;
const FADE_MS = 600;

export function BibleVerseTicker() {
  const [index, setIndex] = useState(0);
  const [visible, setVisible] = useState(true);
  const [paused, setPaused] = useState(false);
  const fadeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const advanceVerse = useCallback(() => {
    setVisible(false);
    if (fadeTimerRef.current) clearTimeout(fadeTimerRef.current);
    fadeTimerRef.current = setTimeout(() => {
      setIndex((prev) => (prev + 1) % VERSES.length);
      setVisible(true);
    }, FADE_MS / 2);
  }, []);

  useEffect(() => {
    setIndex(Math.floor(Math.random() * VERSES.length));
  }, []);

  useEffect(() => {
    if (paused) return undefined;

    intervalRef.current = setInterval(advanceVerse, ROTATE_MS);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [paused, advanceVerse]);

  useEffect(
    () => () => {
      if (fadeTimerRef.current) clearTimeout(fadeTimerRef.current);
      if (intervalRef.current) clearInterval(intervalRef.current);
    },
    [],
  );

  const verse = VERSES[index] ?? VERSES[0];

  return (
    <div
      className="w-full max-w-xl px-2 text-center"
      aria-live="polite"
      aria-atomic="true"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={() => setPaused(false)}
    >
      <blockquote
        className={`transition-opacity duration-[600ms] ease-in-out ${
          visible ? "opacity-100" : "opacity-0"
        }`}
      >
        <p className="ced-hud-text-body line-clamp-2 text-xs leading-snug text-cyan-100/90 sm:text-sm">
          {verse.text}
        </p>
        <cite className="mt-0.5 block not-italic font-[family-name:var(--font-orbitron)] text-[9px] tracking-wider text-cyan-500/70 sm:text-[10px]">
          {verse.ref}
        </cite>
      </blockquote>
    </div>
  );
}

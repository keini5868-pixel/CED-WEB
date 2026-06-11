/** VAD / audio tuning alineado con OpenAI Realtime cookbook (anti-eco). */

export const REALTIME_VAD_TUNING = {
  type: "server_vad" as const,
  threshold: 0.6,
  prefix_padding_ms: 300,
  silence_duration_ms: 800,
  /** Cliente envía response.create tras speech_stopped (evita auto-respuesta al eco). */
  create_response: false,
  interrupt_response: false,
};

export function buildSessionUpdatePayload() {
  return {
    type: "session.update",
    session: {
      type: "realtime",
      audio: {
        input: {
          turn_detection: { ...REALTIME_VAD_TUNING },
        },
      },
    },
  };
}

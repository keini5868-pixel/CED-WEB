import { importLibrary, setOptions } from "@googlemaps/js-api-loader";

import { googleMapsKey } from "@/lib/env";

let mapsReadyPromise: Promise<typeof google> | null = null;

export function loadGoogleMaps(): Promise<typeof google> {
  const key = googleMapsKey();
  if (!key) {
    return Promise.reject(
      new Error(
        "NEXT_PUBLIC_GOOGLE_MAPS_API_KEY no configurada en Railway (@ced/web)",
      ),
    );
  }

  if (!mapsReadyPromise) {
    mapsReadyPromise = (async () => {
      setOptions({ key, v: "weekly" });
      await Promise.all([importLibrary("maps"), importLibrary("marker")]);
      return google;
    })();
  }

  return mapsReadyPromise;
}

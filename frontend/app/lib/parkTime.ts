const PARK_TIME_ZONE = "America/Los_Angeles";

function partsOf(date: Date, timeZone: string): Record<string, string> {
  return new Intl.DateTimeFormat("en-US", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  })
    .formatToParts(date)
    .reduce((acc: Record<string, string>, p) => {
      acc[p.type] = p.value;
      return acc;
    }, {});
}

/** Converts a wall-clock "HH:MM" for *today, in the park's timezone* into a
 * correct UTC ISO string -- not the browser's local timezone. A guest whose
 * device isn't set to Pacific time (most guests, most of the time) would
 * otherwise have every specific time they enter (arrival/departure/meal
 * times) silently mis-localized: `new Date(); d.setHours(23)` sets 11pm in
 * whatever timezone the browser itself is in, not 11pm at the park, so a
 * guest in Eastern time asking to leave at 11pm would actually get scheduled
 * to leave at 8pm Pacific.
 *
 * DST-safe, library-free technique: build a UTC instant that naively reads
 * as the target wall-clock time, check what that same instant actually reads
 * as in the park's timezone (via Intl, never a browser-timezone-dependent
 * `new Date(string)` parse, which would recontaminate the result with the
 * browser's own zone), and shift by the difference. Two Intl-based
 * conversions, zero dependency on the browser's own timezone. */
export function parkTimeToday(time: string): string {
  const [hours, minutes] = time.split(":").map(Number);
  const todayInParkZone = new Intl.DateTimeFormat("en-CA", { timeZone: PARK_TIME_ZONE }).format(new Date());
  const [year, month, day] = todayInParkZone.split("-").map(Number);

  const probe = new Date(Date.UTC(year, month - 1, day, hours, minutes, 0));
  const probeReadInParkZone = partsOf(probe, PARK_TIME_ZONE);
  const parkReadingAsUtc = Date.UTC(
    Number(probeReadInParkZone.year),
    Number(probeReadInParkZone.month) - 1,
    Number(probeReadInParkZone.day),
    Number(probeReadInParkZone.hour),
    Number(probeReadInParkZone.minute),
    Number(probeReadInParkZone.second),
  );
  const offsetMs = probe.getTime() - parkReadingAsUtc;
  return new Date(probe.getTime() + offsetMs).toISOString();
}

/** Inverse of parkTimeToday's wall-clock component -- the "HH:MM" an ISO
 * instant reads as in the park's timezone, for populating a time input. */
export function isoToParkTime(iso: string | null): string {
  if (!iso) return "";
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: PARK_TIME_ZONE,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(iso));
  const hour = parts.find((p) => p.type === "hour")?.value ?? "00";
  const minute = parts.find((p) => p.type === "minute")?.value ?? "00";
  return `${hour}:${minute}`;
}

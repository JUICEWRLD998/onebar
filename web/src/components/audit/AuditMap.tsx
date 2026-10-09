import type { ContourStatus } from "../../hooks/useContours";
import { useMediaQuery } from "../../hooks/useMediaQuery";
import { formatCoords } from "../../lib/format";
import type { Contours } from "../../lib/terrain";
import type { Trace } from "../../lib/types";
import styles from "./Audit.module.css";

/** A wide band on a desktop sheet; on a phone the whole grid, because a 16:7 strip is too small to read. */
const WIDE = 16 / 7;
const NARROW = 3 / 2;

interface Crop {
  y0: number;
  h: number;
}

/** The map is cropped to a wide band around the place, so it never pushes the numbers below the first viewport. */
export function cropOf(c: Contours, aspect = WIDE): Crop {
  const h = Math.min(c.height, c.width / aspect);
  const y0 = Math.min(Math.max(c.centre.y - h / 2, 0), c.height - h);
  return { y0, h };
}

const pct = (v: number, total: number) => `${((v / total) * 100).toFixed(2)}%`;

interface Props {
  trace: Trace;
  contours: Contours | null;
  status: ContourStatus;
}

export function AuditMap({ trace, contours, status }: Props) {
  const narrow = useMediaQuery("(max-width: 40rem)");
  const name = trace.place?.name ?? "your place";

  if (!contours) {
    return (
      <div className={styles.mapEmpty} role="status">
        {status === "loading"
          ? "Reading the terrain around the place"
          : status === "error"
            ? "The terrain could not be loaded. The forecast and the checks below are not affected."
            : "No place for this reply, so no terrain."}
      </div>
    );
  }

  const crop = cropOf(contours, narrow ? NARROW : WIDE);
  const { centre, summit } = contours;
  const summitInView = summit.y >= crop.y0 && summit.y <= crop.y0 + crop.h;
  const summitIsPlace = Math.hypot(summit.x - centre.x, summit.y - centre.y) < 28;

  return (
    <figure className={styles.map}>
      <div className={styles.frame} style={{ aspectRatio: `${contours.width} / ${crop.h}` }}>
      <svg
        className={styles.mapSvg}
        viewBox={`0 ${crop.y0} ${contours.width} ${crop.h}`}
        role="img"
        aria-label={`Contour map around ${name}. Highest point ${Math.round(summit.z)} metres. Lines every ${contours.interval} metres.`}
      >
        <path d={contours.minor} className={styles.minor} vectorEffect="non-scaling-stroke" />
        <path d={contours.major} className={styles.major} vectorEffect="non-scaling-stroke" />
        {summitInView && <path d={`M${summit.x} ${summit.y - 5}l4.5 8h-9z`} className={styles.summit} />}
        <circle cx={centre.x} cy={centre.y} r="9" className={styles.pinHalo} />
        <circle cx={centre.x} cy={centre.y} r="5" className={styles.pin} />
      </svg>
      <span
        className={styles.mapLabel}
        style={{ left: pct(centre.x, contours.width), top: pct(centre.y - crop.y0, crop.h) }}
        data-side={centre.x >= contours.width * 0.45 ? "left" : "right"}
      >
        <strong>{name}</strong>
        {trace.place?.elevation ? ` ${trace.place.elevation}` : ""}
      </span>
      {summitInView && !summitIsPlace && (
        <span
          className={styles.mapLabel}
          style={{ left: pct(summit.x, contours.width), top: pct(summit.y - crop.y0, crop.h) }}
          data-kind="spot"
          data-side={summit.x > contours.width * 0.62 ? "left" : "right"}
        >
          {Math.round(summit.z)} m
        </span>
      )}
      </div>
      <figcaption className={styles.mapCaption}>
        Terrain within about 5 km{trace.place ? `, ${formatCoords(trace.place.lat, trace.place.lon)}` : ""}. Lines every{" "}
        {contours.interval} m.
      </figcaption>
    </figure>
  );
}

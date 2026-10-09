import { recordedContours } from "../data/recorded";
import styles from "./ContourField.module.css";

/**
 * A quiet field of real contour lines behind a page heading. They are the terrain around the first recorded example
 * (computed from real elevations), so the decoration is the product's own output and not stock imagery.
 */
export function ContourField() {
  const c = recordedContours("example-ridge");
  if (!c) return null;
  return (
    <svg className={styles.field} viewBox={`0 0 ${c.width} ${c.height}`} preserveAspectRatio="xMidYMid slice" aria-hidden="true" focusable="false">
      <path d={c.minor} className={styles.minor} vectorEffect="non-scaling-stroke" />
      <path d={c.major} className={styles.major} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

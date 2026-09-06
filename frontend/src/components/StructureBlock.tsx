/**
 * The compact structure block for the Today page.
 *
 * Deliberately terse: seven lines that answer "what does the chart look like,
 * and what have we verified about it". The last two lines are the ones that
 * matter most, because they are the ones that stop a clean-looking structure
 * from reading as a signal.
 */
import { useEffect, useState } from "react";
import { api, type StructureRead } from "../lib/api";

interface Props {
  asset: string;
}

export function StructureBlock({ asset }: Props) {
  const [daily, setDaily] = useState<StructureRead | null>(null);
  const [intraday, setIntraday] = useState<StructureRead | null>(null);
  const [opportunity, setOpportunity] = useState<any>(null);

  useEffect(() => {
    Promise.all([
      api.structure(asset, "1d").catch(() => null),
      api.structure(asset, "4h").catch(() => null),
      api.entryOpportunity(asset, "4h").catch(() => null),
    ]).then(([d, h, o]) => {
      setDaily(d);
      setIntraday(h);
      setOpportunity(o);
    });
  }, [asset]);

  if (!daily && !intraday) return null;

  const confirmed = (intraday?.patterns ?? []).filter(
    (p) => p.state === "CONFIRMED"
  );

  return (
    <div className="structure-block">
      <div className="structure-row">
        <span className="structure-label">1D structure</span>
        <span>{daily?.market_structure.state.replace(/_/g, " ") ?? "—"}</span>
      </div>
      <div className="structure-row">
        <span className="structure-label">4H structure</span>
        <span>{intraday?.market_structure.state.replace(/_/g, " ") ?? "—"}</span>
      </div>
      <div className="structure-row">
        <span className="structure-label">Location</span>
        <span>{intraday?.location.state.replace(/_/g, " ") ?? "—"}</span>
      </div>
      <div className="structure-row">
        <span className="structure-label">Pattern</span>
        <span>
          {confirmed.length === 0
            ? "NONE CONFIRMED"
            : confirmed
                .map(
                  (p) =>
                    `${p.name.replace(/_/g, " ")} (recognition ${p.recognition_confidence.toFixed(0)})`
                )
                .join(", ")}
        </span>
      </div>
      <div className="structure-row">
        <span className="structure-label">Entry opportunity</span>
        <span>{opportunity?.state ?? "—"}</span>
      </div>
      <div className="structure-row emphasis">
        <span className="structure-label">Measured edge</span>
        <span>{opportunity?.measured_edge_state ?? "—"}</span>
      </div>
      {intraday?.location.invalidation && (
        <div className="structure-row muted small">
          <span className="structure-label">Invalidation</span>
          <span>{intraday.location.invalidation}</span>
        </div>
      )}
    </div>
  );
}

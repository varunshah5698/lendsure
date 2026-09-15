import { timeAgo } from "../../lib/format";

export default function TimeAgo({ ts, className, style }) {
  return (
    <span className={className} style={style} title={ts ? new Date(ts).toLocaleString() : ""}>
      {timeAgo(ts)}
    </span>
  );
}

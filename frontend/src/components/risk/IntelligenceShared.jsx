import Card, { CardHeader, CardTitle, CardDescription, CardContent } from "../ui/Card";
import Badge from "../ui/Badge";
import { inr } from "../../lib/api";

export const label = (key) => key.replace(/_/g, " ");
export const money = (value) => value == null ? "Unavailable" : inr(value);
export const valueText = (value) => value == null ? "Unavailable" : typeof value === "boolean" ? (value ? "Yes" : "No") : String(value);
export const signedMoney = (value) => value == null ? "Unavailable" : `${value > 0 ? "+" : value < 0 ? "−" : ""}${inr(Math.abs(value))}`;

export function SignalCard({ title, source, sandbox = false, description, children }) {
  return <Card className="bi-card">
    <CardHeader>
      <CardTitle>{title}</CardTitle>
      <div className="bi-badges">
        {source && <Badge variant="info">{source}</Badge>}
        {(sandbox || source === "DEMO/SANDBOX") && <Badge variant="warning">SANDBOX · fictional, not real borrower evidence</Badge>}
      </div>
      {description && <CardDescription>{description}</CardDescription>}
    </CardHeader>
    <CardContent>{children}</CardContent>
  </Card>;
}

export function Metrics({ rows }) {
  return <dl className="bi-metrics">{rows.map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{valueText(value)}</dd></div>)}</dl>;
}

export function DataTable({ caption, columns, rows, empty = "Unavailable — not supplied." }) {
  if (!rows?.length) return <p className="bi-muted">{caption}: {rows == null ? "Unavailable — not supplied." : empty}</p>;
  return <table className="bi-table"><caption>{caption}</caption><thead><tr>{columns.map(([key, title]) => <th key={key} scope="col">{title}</th>)}</tr></thead>
    <tbody>{rows.map((row, i) => <tr key={i}>{columns.map(([key, title, format]) => <td key={key} data-label={title}>{format ? format(row[key]) : valueText(row[key])}</td>)}</tr>)}</tbody>
  </table>;
}

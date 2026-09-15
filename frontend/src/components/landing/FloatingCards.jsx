import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { api } from "../../lib/api";
import "./FloatingCards.css";

/** Hero stat cards — populated ONLY from the live trained model.
 *  If the model endpoint is unreachable, nothing renders (no fake numbers). */
export default function FloatingCards() {
  const [cards, setCards] = useState(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    let live = true;
    const t = setTimeout(() => { if (live) setVisible(true); }, 800);
    api("/ls/ml/credit/public")
      .then((m) => {
        if (!live) return;
        const rows = m.train_rows >= 1e6
          ? `${(m.train_rows / 1e6).toFixed(2)}M`
          : `${Math.round(m.train_rows / 1000)}K`;
        setCards([
          { label: "MODEL", value: m.model_id.replace("lendsure-credit-v", "v"), sub: "Gradient boosting", color: "var(--primary)" },
          { label: "FEATURES ANALYZED", value: String(m.n_features), sub: "Behavioral + financial", color: "var(--primary)" },
          { label: "TRAINING ROWS", value: rows, sub: "Real + synthetic borrowers", color: "var(--success)" },
          { label: "HOLDOUT PR-AUC", value: m.pr_auc.toFixed(2), sub: `${m.test_rows.toLocaleString()} real borrowers`, color: "var(--success)" },
          { label: "DECISION", value: "EXPLAINED", sub: "Every score has reasons", color: "var(--primary)" },
        ]);
      })
      .catch(() => { if (live) setCards(null); });
    return () => { live = false; clearTimeout(t); };
  }, []);

  if (!cards || !visible) return null;

  return (
    <div className="floating-cards">
      {cards.map((card, i) => (
        <motion.div
          key={card.label}
          className="floating-card"
          initial={{ opacity: 0, y: 20, scale: 0.9 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ delay: 0.2 * i, duration: 0.6, ease: "easeOut" }}
        >
          <div className="fc-label">{card.label}</div>
          <div className="fc-value" style={{ color: card.color }}>{card.value}</div>
          <div className="fc-sub">{card.sub}</div>
        </motion.div>
      ))}
    </div>
  );
}

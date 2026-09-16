import { motion } from "framer-motion";

/** Scroll-triggered entrance wrapper. Use around cards/sections site-wide. */
export default function Reveal({ children, delay = 0, y = 14, className = "", once = true }) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once, margin: "-40px" }}
      transition={{ duration: 0.35, delay, ease: "easeOut" }}
    >
      {children}
    </motion.div>
  );
}

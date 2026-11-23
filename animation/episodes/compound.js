// Compounding: the lesson is entirely in the shape of the line, so the first
// beat deliberately looks boring and the second one pays it off.
window.EPISODE = {
  // numbers are computed from these inputs; 1000 * 1.07^30 = 7,612 and
  // 1000 * 1.07^40 = 14,974, so the last 10 years add 7,362 against 6,612
  // for the first 30
  card: {head: "$1,000 GROWING 7% A YEAR", sub: "Illustration only. Not a prediction or advice.",
         base: 1000, rate: 0.07, years: 40, split: 30, marks: [10, 30, 40]},
  hookTitle:  "Slow for years.<br>Then fast.",
  closeTitle: "Nothing happens.<br>Then everything.",
  hookColors: ["#4ade80", "#7f93aa"],
  hookCharts: ["FAST", "SLOW"],
  a: {actor: "bull", action: "pace", mood: "calm", chart: "SLOW",
      title: '<span style="color:var(--muted)">THE QUIET YEARS</span>',
      label: "#9fb0c4"},
  b: {actor: "bull", action: "rearUp", mood: "bull", chart: "FAST",
      title: '<span style="color:var(--green-soft)">COMPOUNDING</span>',
      label: "#4ade80"},
};

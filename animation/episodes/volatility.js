// Volatility: close up it is noise, far away it is a trend. The first beat
// keeps both animals on stage pulling the line in turn, which is the only
// episode that uses `both`.
window.EPISODE = {
  hookTitle:  "Why does it<br>jump around?",
  closeTitle: "Noise close up.<br>Trend far away.",
  hookColors: ["#facc15", "#4ade80"],
  hookCharts: ["NOISE", "TREND"],
  a: {both: true, mood: "duel", chart: "NOISE",
      title: '<span style="color:var(--gold)">VOLATILITY</span>',
      label: "#facc15"},
  b: {actor: "bull", action: "rearUp", mood: "bull", chart: "TREND",
      title: '<span style="color:var(--green-soft)">STEP BACK</span>',
      label: "#4ade80"},
};

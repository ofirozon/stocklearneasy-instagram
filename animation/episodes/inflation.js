// Inflation: the number in the drawer never moves, what it buys does. The bull
// keeps watch over the flat line, the bear walks the slow slide. Nothing on
// screen rises in either beat, so nothing reads as a return promise, and the
// lesson is only what cash does when it sits still.
window.EPISODE = {
  hookTitle:  "Is cash<br>standing still?",
  closeTitle: "Same number.<br>Smaller basket.",
  hookColors: ["#9fb0c4", "#f04d4d"],
  hookCharts: ["CASH", "BUYS"],
  a: {actor: "bull", action: "pace", mood: "calm", chart: "CASH", sign: "$1,000",
      title: '<span style="color:var(--muted)">THE NUMBER</span>',
      label: "#9fb0c4"},
  b: {actor: "bear", action: "pace", mood: "bear", chart: "BUYS", sign: "WHAT IT BUYS",
      title: '<span style="color:var(--red-soft)">WHAT IT BUYS</span>',
      label: "#ff8f8f"},
};

// Market cap: the share price says nothing about how big the company is. Beat
// A is the "expensive" stock, a high flat line, beat B the "cheap" one, a low
// flat line, and the narration does the multiplication that flips them. Both
// lines are flat on purpose: this is about size, not about where a price goes,
// so nothing on screen reads as a return promise.
window.EPISODE = {
  hookTitle:  "Is $500 a share<br>the big one?",
  closeTitle: "Price is a slice.<br>Size is the pie.",
  hookColors: ["#facc15", "#9fb0c4"],
  hookCharts: ["PRICEY", "CHEAP"],
  a: {actor: "bull", action: "pace", mood: "calm", chart: "PRICEY", sign: "$500 × 10M",
      title: '<span style="color:var(--gold)">WORTH $5B</span>',
      label: "#facc15"},
  b: {actor: "bear", action: "pace", mood: "calm", chart: "CHEAP", sign: "$5 × 10B",
      title: '<span style="color:var(--muted)">WORTH $50B</span>',
      label: "#9fb0c4"},
};

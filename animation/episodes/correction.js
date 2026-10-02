// Correction against bear market: the same red screen, two different words.
// Both teaching beats belong to the bear, so the difference the viewer reads
// is the depth of the line, not which animal is on stage.
window.EPISODE = {
  hookTitle:  "Ten percent,<br>or twenty?",
  closeTitle: "A dip.<br>Or a bear.",
  hookColors: ["#4ade80", "#f04d4d"],
  hookCharts: ["DIP", "SLIDE"],
  a: {actor: "bear", action: "rearUp", mood: "calm", chart: "DIP",
      title: '<span style="color:var(--gold)">CORRECTION</span>',
      label: "#facc15"},
  b: {actor: "bear", action: "swipe", mood: "bear", chart: "SLIDE",
      title: '<span style="color:var(--red-soft)">BEAR MARKET</span>',
      label: "#ff8f8f"},
};

// Diversification: the same bad quarter, felt alone and felt inside a basket.
// The bear owns beat A (one stock takes the hit in full), the bull walks
// through beat B (the hit is still there, only smaller). No line goes up in
// either beat on purpose, so nothing on screen reads as a return promise.
window.EPISODE = {
  hookTitle:  "All your eggs,<br>one basket?",
  closeTitle: "One stock falls.<br>A basket dents.",
  hookColors: ["#f04d4d", "#4ade80"],
  hookCharts: ["ONE", "MANY"],
  a: {actor: "bear", action: "swipe", mood: "bear", chart: "ONE", sign: "ACME INC",
      title: '<span style="color:var(--red-soft)">ONE STOCK</span>',
      label: "#ff8f8f"},
  b: {actor: "bull", action: "pace", mood: "calm", chart: "MANY", sign: "500 STOCKS",
      title: '<span style="color:var(--green-soft)">A BASKET</span>',
      label: "#4ade80"},
};

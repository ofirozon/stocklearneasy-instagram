// Orders: a market order buys now at whatever the price is, a limit order
// buys only at your price or better and may never fill. The bear walks a
// price that jitters in a fast market (what a market order can catch); the
// bull keeps watch over a flat ceiling, the limit. Neither beat says one
// order is better, and nothing on screen is a return: the close names the
// trade-off, speed against price.
window.EPISODE = {
  hookTitle:  "Did you pay<br>the price you saw?",
  closeTitle: "Market: now.<br>Limit: your price.",
  hookColors: ["#f04d4d", "#9fb0c4"],
  hookCharts: ["FAST", "CAP"],
  a: {actor: "bear", action: "pace", mood: "bear", chart: "FAST", sign: "$50 → $50.40",
      title: '<span style="color:var(--red-soft)">MARKET ORDER</span>',
      label: "#ff8f8f"},
  b: {actor: "bull", action: "pace", mood: "calm", chart: "CAP", sign: "$50 OR LESS",
      title: '<span style="color:var(--muted)">LIMIT ORDER</span>',
      label: "#9fb0c4"},
};

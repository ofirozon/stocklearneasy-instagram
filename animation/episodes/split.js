// Stock split: the price per share halves overnight and nothing was lost. The
// bear walks the line that looks like a crash (the price per share), the bull
// keeps watch over the line that matters (what the whole holding is worth),
// which does not move. Nothing on screen rises, so nothing reads as a return
// promise; the lesson is only that a lower share price is not a smaller stake.
window.EPISODE = {
  hookTitle:  "Did the stock<br>just halve?",
  closeTitle: "Half the price.<br>Twice the shares.",
  hookColors: ["#f04d4d", "#9fb0c4"],
  hookCharts: ["HALVED", "WHOLE"],
  a: {actor: "bear", action: "pace", mood: "bear", chart: "HALVED", sign: "PER SHARE",
      title: '<span style="color:var(--red-soft)">THE PRICE</span>',
      label: "#ff8f8f"},
  b: {actor: "bull", action: "pace", mood: "calm", chart: "WHOLE", sign: "WHAT YOU OWN",
      title: '<span style="color:var(--muted)">WHAT YOU OWN</span>',
      label: "#9fb0c4"},
};

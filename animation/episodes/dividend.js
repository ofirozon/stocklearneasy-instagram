// Dividend: a dividend is not new money. On the ex-dividend day the share
// price usually opens lower by about the dividend, so the bear walks a price
// that steps down a little, and the bull keeps watch over the total, share
// plus cash, which does not move. Nothing on screen rises, so nothing reads
// as a return promise; the lesson is only that the money moved, it was not
// added.
window.EPISODE = {
  hookTitle:  "Is a dividend<br>free money?",
  closeTitle: "Not new money.<br>Moved money.",
  hookColors: ["#f04d4d", "#9fb0c4"],
  hookCharts: ["EXDIV", "TOTAL"],
  a: {actor: "bear", action: "pace", mood: "bear", chart: "EXDIV", sign: "$100 → $98",
      title: '<span style="color:var(--red-soft)">THE SHARE</span>',
      label: "#ff8f8f"},
  b: {actor: "bull", action: "pace", mood: "calm", chart: "TOTAL", sign: "$98 + $2 CASH",
      title: '<span style="color:var(--muted)">WHAT YOU HAVE</span>',
      label: "#9fb0c4"},
};

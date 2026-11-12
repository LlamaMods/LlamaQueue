document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("appearance-form");
  const feedback = document.getElementById("appearance-preset-feedback");
  if (!form) return;
  const fields = ["background_color","surface_color","raised_surface_color","accent_color","accent_text_color","text_color","muted_text_color","border_color","font_family","font_size","corner_radius","density"];
  const currentValues = () => {
    const values = {};
    fields.forEach(key => {
      const field = form.elements.namedItem(key);
      if (field) values[key] = field.value;
    });
    return values;
  };
  const setStatus = (slot, text) => {
    const el = document.getElementById(`appearance-preset-status-${slot}`);
    if (el) el.textContent = text;
  };
  async function refresh() {
    try {
      const response = await fetch("/api/appearance-presets");
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not check saved appearances.");
      (data.slots || []).forEach(item => {
        setStatus(item.slot, item.saved ? "Saved design" : "Empty slot");
        const load = document.querySelector(`[data-appearance-load="${item.slot}"]`);
        if (load) load.disabled = !item.saved;
        const name = document.getElementById(`appearance-preset-name-${item.slot}`);
        if (name && item.saved && item.name) name.value = item.name;
      });
    } catch (error) { if (feedback) feedback.textContent = error.message; }
  }
  document.querySelectorAll("[data-appearance-save]").forEach(button => button.addEventListener("click", async () => {
    const slot = Number(button.dataset.appearanceSave);
    const name = document.getElementById(`appearance-preset-name-${slot}`).value.trim() || `Appearance ${slot}`;
    button.disabled = true;
    if (feedback) feedback.textContent = `Saving Appearance ${slot}…`;
    try {
      const response = await fetch(`/api/appearance-presets/${slot}/save`, {
        method: "POST", headers: {"Content-Type":"application/json"},
        body: JSON.stringify({...currentValues(), name})
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not save appearance.");
      if (feedback) feedback.textContent = `${data.name} saved.`;
      await refresh();
    } catch (error) { if (feedback) feedback.textContent = error.message; }
    finally { button.disabled = false; }
  }));
  document.querySelectorAll("[data-appearance-load]").forEach(button => button.addEventListener("click", async () => {
    const slot = Number(button.dataset.appearanceLoad);
    const name = document.getElementById(`appearance-preset-name-${slot}`).value || `Appearance ${slot}`;
    if (!window.confirm(`Load ${name}? This will replace your current website appearance.`)) return;
    button.disabled = true;
    if (feedback) feedback.textContent = `Loading Appearance ${slot}…`;
    try {
      const response = await fetch(`/api/appearance-presets/${slot}/load`, {method:"POST"});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not load appearance.");
      window.location.href = "/settings?saved=appearance";
    } catch (error) {
      if (feedback) feedback.textContent = error.message;
      button.disabled = false;
    }
  }));
  refresh();
});

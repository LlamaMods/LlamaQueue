(() => {
  const form = document.getElementById("appearance-form");
  if (!form) return;
  const root = document.body;
  const fields = [...form.querySelectorAll("[data-theme-field]")];
  const defaults = {
    background_color:"#101418", surface_color:"#1B2128", raised_surface_color:"#252D36",
    accent_color:"#33C759", accent_text_color:"#7BE495", text_color:"#F4F7F8",
    muted_text_color:"#A9B4BE", border_color:"#2E3742"
  };
  const apply = () => {
    const values = {};
    fields.forEach(input => { values[input.name] = input.value; });
    Object.entries(values).forEach(([key,value]) => {
      const cssKey = ({
        background_color:"--bg", surface_color:"--panel", raised_surface_color:"--panel-light",
        accent_color:"--green", accent_text_color:"--green-light", text_color:"--text",
        muted_text_color:"--muted", border_color:"--border"
      })[key];
      root.style.setProperty(cssKey,value);
      const code = form.querySelector(`input[name="${key}"]`)?.parentElement?.querySelector("code");
      if (code) code.textContent=value.toUpperCase();
    });
    const font = form.querySelector("#font-family");
    const size = form.querySelector("#font-size");
    const radius = form.querySelector("#corner-radius");
    if (font) root.style.setProperty("--font-family",`'${font.value}'`);
    if (size) { root.style.setProperty("--font-size",`${size.value}px`); const o=form.querySelector("#font-size-value"); if(o)o.textContent=`${size.value}px`; }
    if (radius) { root.style.setProperty("--radius",`${radius.value}px`); const o=form.querySelector("#radius-value"); if(o)o.textContent=`${radius.value}px`; }
    const preview=form.querySelector("#appearance-preview");
    if (preview) {
      preview.style.background=values.background_color;
      preview.style.color=values.text_color;
      preview.style.borderColor=values.border_color;
      preview.querySelector(".preview-top").style.background=values.surface_color;
      preview.querySelector(".preview-content h3").style.color=values.accent_text_color;
      preview.querySelector(".preview-stat").style.background=values.surface_color;
      preview.querySelector(".preview-action").style.background=values.accent_color;
    }
  };
  fields.forEach(input=>input.addEventListener("input",apply));
  ["#font-family","#font-size","#corner-radius"].forEach(sel=>form.querySelector(sel)?.addEventListener("input",apply));
  apply();
})();
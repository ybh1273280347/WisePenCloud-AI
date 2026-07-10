import {
  getConfig2
} from "./chunk-XBKWAHKI.js";
import {
  __name,
  select_default
} from "./chunk-HABAP4E3.js";

// node_modules/mermaid/dist/chunks/mermaid.core/chunk-WU5MYG2G.mjs
var selectSvgElement = __name((id) => {
  const { securityLevel } = getConfig2();
  let root = select_default("body");
  if (securityLevel === "sandbox") {
    const sandboxElement = select_default(`#i${id}`);
    const doc = sandboxElement.node()?.contentDocument ?? document;
    root = select_default(doc.body);
  }
  const svg = root.select(`#${id}`);
  return svg;
}, "selectSvgElement");

export {
  selectSvgElement
};
//# sourceMappingURL=chunk-ZIUDQMU5.js.map

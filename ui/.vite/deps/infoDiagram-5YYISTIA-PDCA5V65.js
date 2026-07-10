import {
  parse
} from "./chunk-F425WWWM.js";
import "./chunk-ESO537TV.js";
import "./chunk-WHNS3CSR.js";
import "./chunk-EUYK6WTT.js";
import "./chunk-WSU7G33A.js";
import "./chunk-YA7FADDS.js";
import "./chunk-ZA2IIBVX.js";
import "./chunk-2BPC2O2H.js";
import "./chunk-PAZ5ONHC.js";
import "./chunk-UPUNSPRJ.js";
import "./chunk-O2WOOAY5.js";
import "./chunk-IUNJMT4E.js";
import {
  selectSvgElement
} from "./chunk-ZIUDQMU5.js";
import {
  configureSvgSize
} from "./chunk-XBKWAHKI.js";
import {
  __name,
  log
} from "./chunk-HABAP4E3.js";
import "./chunk-PR4QN5HX.js";

// node_modules/mermaid/dist/chunks/mermaid.core/infoDiagram-5YYISTIA.mjs
var parser = {
  parse: __name(async (input) => {
    const ast = await parse("info", input);
    log.debug(ast);
  }, "parse")
};
var DEFAULT_INFO_DB = {
  version: "11.15.0" + (true ? "" : "-tiny")
};
var getVersion = __name(() => DEFAULT_INFO_DB.version, "getVersion");
var db = {
  getVersion
};
var draw = __name((text, id, version) => {
  log.debug("rendering info diagram\n" + text);
  const svg = selectSvgElement(id);
  configureSvgSize(svg, 100, 400, true);
  const group = svg.append("g");
  group.append("text").attr("x", 100).attr("y", 40).attr("class", "version").attr("font-size", 32).style("text-anchor", "middle").text(`v${version}`);
}, "draw");
var renderer = { draw };
var diagram = {
  parser,
  db,
  renderer
};
export {
  diagram
};
//# sourceMappingURL=infoDiagram-5YYISTIA-PDCA5V65.js.map

"use client";
import {
  At,
  Li,
  R
} from "./chunk-VXT3JPPO.js";
import "./chunk-I3ZLX6NI.js";
import "./chunk-KDVGFZWC.js";
import "./chunk-CDHXPRKO.js";
import "./chunk-Z2563UL6.js";
import "./chunk-GB4GYC7J.js";
import "./chunk-SBBPKQQ3.js";
import {
  require_jsx_runtime
} from "./chunk-SB2YDIVE.js";
import {
  require_react
} from "./chunk-PJ4ZNNSI.js";
import {
  __toESM
} from "./chunk-PR4QN5HX.js";

// node_modules/streamdown/dist/highlighted-body-OFNGDK62.js
var import_react = __toESM(require_react(), 1);
var import_jsx_runtime = __toESM(require_jsx_runtime(), 1);
var R2 = ({ code: s, language: e, raw: t, className: h, startLine: d, lineNumbers: m, ...p }) => {
  let { shikiTheme: l } = (0, import_react.useContext)(R), o = Li(), [a, i] = (0, import_react.useState)(t);
  return (0, import_react.useEffect)(() => {
    if (!o) {
      i(t);
      return;
    }
    let r = o.highlight({ code: s, language: e, themes: l }, (c) => {
      i(c);
    });
    r && i(r);
  }, [s, e, l, o, t]), (0, import_jsx_runtime.jsx)(At, { className: h, language: e, lineNumbers: m, result: a, startLine: d, ...p });
};
export {
  R2 as HighlightedCodeBlockBody
};
//# sourceMappingURL=highlighted-body-OFNGDK62-2YC67KPW.js.map

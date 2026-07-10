import {
  ruby_default
} from "./chunk-NVZHQLE7.js";
import "./chunk-IZONS6GK.js";
import "./chunk-56DUSVMY.js";
import "./chunk-SV4SJWVS.js";
import "./chunk-SDELLUOG.js";
import "./chunk-5FXWCRGP.js";
import "./chunk-VENWZGWG.js";
import "./chunk-CIVERT6H.js";
import "./chunk-2LAWNZUN.js";
import "./chunk-7WE2XAKA.js";
import "./chunk-7CZP275T.js";
import "./chunk-35HYOGOQ.js";
import "./chunk-74JHKWSH.js";
import "./chunk-DFYFAGQH.js";
import "./chunk-YX4HZXMZ.js";
import "./chunk-RTSLTBDF.js";
import {
  html_default
} from "./chunk-6LBJXPUY.js";
import "./chunk-H3AZEKOB.js";
import "./chunk-2I2TA7FM.js";
import "./chunk-PR4QN5HX.js";

// node_modules/@streamdown/code/node_modules/@shikijs/langs/dist/erb.mjs
var lang = Object.freeze(JSON.parse('{"displayName":"ERB","fileTypes":["erb","rhtml","html.erb"],"injections":{"text.html.erb - (meta.embedded.block.erb | meta.embedded.line.erb | comment)":{"patterns":[{"begin":"^(\\\\s*)(?=<%+#(?![^%]*%>))","beginCaptures":{"0":{"name":"punctuation.whitespace.comment.leading.erb"}},"end":"(?!\\\\G)(\\\\s*$\\\\n)?","endCaptures":{"0":{"name":"punctuation.whitespace.comment.trailing.erb"}},"patterns":[{"include":"#comment"}]},{"begin":"^(\\\\s*)(?=<%(?![^%]*%>))","beginCaptures":{"0":{"name":"punctuation.whitespace.embedded.leading.erb"}},"end":"(?!\\\\G)(\\\\s*$\\\\n)?","endCaptures":{"0":{"name":"punctuation.whitespace.embedded.trailing.erb"}},"patterns":[{"include":"#tags"}]},{"include":"#comment"},{"include":"#tags"}]}},"name":"erb","patterns":[{"include":"text.html.basic"}],"repository":{"comment":{"patterns":[{"begin":"<%+#","beginCaptures":{"0":{"name":"punctuation.definition.comment.begin.erb"}},"end":"%>","endCaptures":{"0":{"name":"punctuation.definition.comment.end.erb"}},"name":"comment.block.erb"}]},"tags":{"patterns":[{"begin":"<%+(?!>)[-=]?(?![^%]*%>)","beginCaptures":{"0":{"name":"punctuation.section.embedded.begin.erb"}},"contentName":"source.ruby","end":"(-?%)>","endCaptures":{"0":{"name":"punctuation.section.embedded.end.erb"},"1":{"name":"source.ruby"}},"name":"meta.embedded.block.erb","patterns":[{"captures":{"1":{"name":"punctuation.definition.comment.erb"}},"match":"(#).*?(?=-?%>)","name":"comment.line.number-sign.erb"},{"include":"source.ruby"}]},{"begin":"<%+(?!>)[-=]?","beginCaptures":{"0":{"name":"punctuation.section.embedded.begin.erb"}},"contentName":"source.ruby","end":"(-?%)>","endCaptures":{"0":{"name":"punctuation.section.embedded.end.erb"},"1":{"name":"source.ruby"}},"name":"meta.embedded.line.erb","patterns":[{"captures":{"1":{"name":"punctuation.definition.comment.erb"}},"match":"(#).*?(?=-?%>)","name":"comment.line.number-sign.erb"},{"include":"source.ruby"}]}]}},"scopeName":"text.html.erb","embeddedLangs":["html","ruby"]}'));
var erb_default = [
  ...html_default,
  ...ruby_default,
  lang
];
export {
  erb_default as default
};
//# sourceMappingURL=erb-SNLFCXCC.js.map

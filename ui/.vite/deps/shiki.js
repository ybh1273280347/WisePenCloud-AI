import {
  EncodedTokenMetadata,
  FontStyle,
  INITIAL,
  Registry,
  Theme,
  toHtml,
  toRegExp
} from "./chunk-OR7ABYWP.js";
import "./chunk-CDHXPRKO.js";
import "./chunk-GB4GYC7J.js";
import {
  __export
} from "./chunk-PR4QN5HX.js";

// node_modules/shiki/dist/chunk-BBjsoOtd.mjs
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __exportAll = (all, no_symbols) => {
  let target = {};
  for (var name in all) __defProp(target, name, {
    get: all[name],
    enumerable: true
  });
  if (!no_symbols) __defProp(target, Symbol.toStringTag, { value: "Module" });
  return target;
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") for (var keys = __getOwnPropNames(from), i = 0, n = keys.length, key; i < n; i++) {
    key = keys[i];
    if (!__hasOwnProp.call(to, key) && key !== except) __defProp(to, key, {
      get: ((k) => from[k]).bind(null, key),
      enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable
    });
  }
  return to;
};
var __reExport = (target, mod, secondTarget) => (__copyProps(target, mod, "default"), secondTarget && __copyProps(secondTarget, mod, "default"));

// node_modules/shiki/dist/langs-bundle-full-4noeO3oH.mjs
var bundledLanguagesInfo = [
  {
    "id": "abap",
    "name": "ABAP",
    "import": (() => import("./abap-B5V2GOQL.js"))
  },
  {
    "id": "actionscript-3",
    "name": "ActionScript",
    "import": (() => import("./actionscript-3-P7BKX4PD.js"))
  },
  {
    "id": "ada",
    "name": "Ada",
    "import": (() => import("./ada-7XTKFSXE.js"))
  },
  {
    "id": "angular-html",
    "name": "Angular HTML",
    "import": (() => import("./angular-html-XSGB4DUD.js"))
  },
  {
    "id": "angular-ts",
    "name": "Angular TypeScript",
    "import": (() => import("./angular-ts-TALYCY32.js"))
  },
  {
    "id": "apache",
    "name": "Apache Conf",
    "import": (() => import("./apache-6FPFH2H4.js"))
  },
  {
    "id": "apex",
    "name": "Apex",
    "import": (() => import("./apex-QTJTVXJC.js"))
  },
  {
    "id": "apl",
    "name": "APL",
    "import": (() => import("./apl-WDC6F26H.js"))
  },
  {
    "id": "applescript",
    "name": "AppleScript",
    "import": (() => import("./applescript-3Z74JXJY.js"))
  },
  {
    "id": "ara",
    "name": "Ara",
    "import": (() => import("./ara-DAURSYGM.js"))
  },
  {
    "id": "asciidoc",
    "name": "AsciiDoc",
    "aliases": ["adoc"],
    "import": (() => import("./asciidoc-WR3CPCN7.js"))
  },
  {
    "id": "asm",
    "name": "Assembly",
    "import": (() => import("./asm-VI2UWS5S.js"))
  },
  {
    "id": "astro",
    "name": "Astro",
    "import": (() => import("./astro-XZILMTVA.js"))
  },
  {
    "id": "awk",
    "name": "AWK",
    "import": (() => import("./awk-EG6VV5ZV.js"))
  },
  {
    "id": "ballerina",
    "name": "Ballerina",
    "import": (() => import("./ballerina-HZA42RGW.js"))
  },
  {
    "id": "bat",
    "name": "Batch File",
    "aliases": ["batch"],
    "import": (() => import("./bat-GGLOX2GV.js"))
  },
  {
    "id": "beancount",
    "name": "Beancount",
    "import": (() => import("./beancount-GIYVGDL5.js"))
  },
  {
    "id": "berry",
    "name": "Berry",
    "aliases": ["be"],
    "import": (() => import("./berry-3CDUJKPX.js"))
  },
  {
    "id": "bibtex",
    "name": "BibTeX",
    "import": (() => import("./bibtex-AIXOXZJE.js"))
  },
  {
    "id": "bicep",
    "name": "Bicep",
    "import": (() => import("./bicep-YAGLOBMW.js"))
  },
  {
    "id": "bird2",
    "name": "BIRD2 Configuration",
    "aliases": ["bird"],
    "import": (() => import("./bird2-ZTBRNNE6.js"))
  },
  {
    "id": "blade",
    "name": "Blade",
    "import": (() => import("./blade-MDZV7752.js"))
  },
  {
    "id": "bsl",
    "name": "1C (Enterprise)",
    "aliases": ["1c"],
    "import": (() => import("./bsl-OZGQOAOJ.js"))
  },
  {
    "id": "c",
    "name": "C",
    "import": (() => import("./c-YKJUTVJH.js"))
  },
  {
    "id": "c3",
    "name": "C3",
    "import": (() => import("./c3-PGIVU5NW.js"))
  },
  {
    "id": "cadence",
    "name": "Cadence",
    "aliases": ["cdc"],
    "import": (() => import("./cadence-IYAP45ZT.js"))
  },
  {
    "id": "cairo",
    "name": "Cairo",
    "import": (() => import("./cairo-HPLEEXEA.js"))
  },
  {
    "id": "clarity",
    "name": "Clarity",
    "import": (() => import("./clarity-XLEJSYBV.js"))
  },
  {
    "id": "clojure",
    "name": "Clojure",
    "aliases": ["clj"],
    "import": (() => import("./clojure-ZO2NIMVB.js"))
  },
  {
    "id": "cmake",
    "name": "CMake",
    "import": (() => import("./cmake-QS6M5QXY.js"))
  },
  {
    "id": "cobol",
    "name": "COBOL",
    "import": (() => import("./cobol-J6OUM2LX.js"))
  },
  {
    "id": "codeowners",
    "name": "CODEOWNERS",
    "import": (() => import("./codeowners-5VW24KH4.js"))
  },
  {
    "id": "codeql",
    "name": "CodeQL",
    "aliases": ["ql"],
    "import": (() => import("./codeql-SIBT76TM.js"))
  },
  {
    "id": "coffee",
    "name": "CoffeeScript",
    "aliases": ["coffeescript"],
    "import": (() => import("./coffee-BBLXXHF3.js"))
  },
  {
    "id": "common-lisp",
    "name": "Common Lisp",
    "aliases": ["lisp"],
    "import": (() => import("./common-lisp-GA5V3N2P.js"))
  },
  {
    "id": "coq",
    "name": "Coq",
    "import": (() => import("./coq-KK727ITJ.js"))
  },
  {
    "id": "cpp",
    "name": "C++",
    "aliases": ["c++"],
    "import": (() => import("./cpp-Z656BLPM.js"))
  },
  {
    "id": "crystal",
    "name": "Crystal",
    "import": (() => import("./crystal-2OQYSEXL.js"))
  },
  {
    "id": "csharp",
    "name": "C#",
    "aliases": ["c#", "cs"],
    "import": (() => import("./csharp-WEE2VTYH.js"))
  },
  {
    "id": "css",
    "name": "CSS",
    "import": (() => import("./css-MFFYNORM.js"))
  },
  {
    "id": "csv",
    "name": "CSV",
    "import": (() => import("./csv-FOUHFJRZ.js"))
  },
  {
    "id": "cue",
    "name": "CUE",
    "import": (() => import("./cue-B76MEU2H.js"))
  },
  {
    "id": "cypher",
    "name": "Cypher",
    "aliases": ["cql"],
    "import": (() => import("./cypher-VP6KIHQF.js"))
  },
  {
    "id": "d",
    "name": "D",
    "import": (() => import("./d-4MV2PAQ4.js"))
  },
  {
    "id": "dart",
    "name": "Dart",
    "import": (() => import("./dart-QNBN53MN.js"))
  },
  {
    "id": "dax",
    "name": "DAX",
    "import": (() => import("./dax-INRSNFCZ.js"))
  },
  {
    "id": "desktop",
    "name": "Desktop",
    "import": (() => import("./desktop-UEECW7PC.js"))
  },
  {
    "id": "diff",
    "name": "Diff",
    "import": (() => import("./diff-DSUCYA6J.js"))
  },
  {
    "id": "docker",
    "name": "Dockerfile",
    "aliases": ["dockerfile"],
    "import": (() => import("./docker-HCGZ7IXD.js"))
  },
  {
    "id": "dotenv",
    "name": "dotEnv",
    "import": (() => import("./dotenv-7TOMRUV5.js"))
  },
  {
    "id": "dream-maker",
    "name": "Dream Maker",
    "import": (() => import("./dream-maker-C5RWJRBN.js"))
  },
  {
    "id": "edge",
    "name": "Edge",
    "import": (() => import("./edge-QZ33MANE.js"))
  },
  {
    "id": "elixir",
    "name": "Elixir",
    "import": (() => import("./elixir-OKHVG7UH.js"))
  },
  {
    "id": "elm",
    "name": "Elm",
    "import": (() => import("./elm-D2PIA4EK.js"))
  },
  {
    "id": "emacs-lisp",
    "name": "Emacs Lisp",
    "aliases": ["elisp"],
    "import": (() => import("./emacs-lisp-GIYH44LF.js"))
  },
  {
    "id": "erb",
    "name": "ERB",
    "import": (() => import("./erb-P5KJYRQJ.js"))
  },
  {
    "id": "erlang",
    "name": "Erlang",
    "aliases": ["erl"],
    "import": (() => import("./erlang-5BCDN4OB.js"))
  },
  {
    "id": "fennel",
    "name": "Fennel",
    "import": (() => import("./fennel-TVIAUVZL.js"))
  },
  {
    "id": "fish",
    "name": "Fish",
    "import": (() => import("./fish-NP2DSOOY.js"))
  },
  {
    "id": "fluent",
    "name": "Fluent",
    "aliases": ["ftl"],
    "import": (() => import("./fluent-VZMIBB4B.js"))
  },
  {
    "id": "fortran-fixed-form",
    "name": "Fortran (Fixed Form)",
    "aliases": [
      "f",
      "for",
      "f77"
    ],
    "import": (() => import("./fortran-fixed-form-SHK2P7QG.js"))
  },
  {
    "id": "fortran-free-form",
    "name": "Fortran (Free Form)",
    "aliases": [
      "f90",
      "f95",
      "f03",
      "f08",
      "f18"
    ],
    "import": (() => import("./fortran-free-form-NEECEBL4.js"))
  },
  {
    "id": "fsharp",
    "name": "F#",
    "aliases": ["f#", "fs"],
    "import": (() => import("./fsharp-7HKPUAGF.js"))
  },
  {
    "id": "gdresource",
    "name": "GDResource",
    "aliases": ["tscn", "tres"],
    "import": (() => import("./gdresource-2G7P5DH2.js"))
  },
  {
    "id": "gdscript",
    "name": "GDScript",
    "aliases": ["gd"],
    "import": (() => import("./gdscript-EVSUAXAM.js"))
  },
  {
    "id": "gdshader",
    "name": "GDShader",
    "import": (() => import("./gdshader-VSL4ZSVS.js"))
  },
  {
    "id": "genie",
    "name": "Genie",
    "import": (() => import("./genie-GGEHV3VN.js"))
  },
  {
    "id": "gherkin",
    "name": "Gherkin",
    "import": (() => import("./gherkin-LIMAEIPA.js"))
  },
  {
    "id": "git-commit",
    "name": "Git Commit Message",
    "import": (() => import("./git-commit-WZSREYJI.js"))
  },
  {
    "id": "git-rebase",
    "name": "Git Rebase Message",
    "import": (() => import("./git-rebase-DGCAHBAO.js"))
  },
  {
    "id": "gleam",
    "name": "Gleam",
    "import": (() => import("./gleam-2L6FHAFF.js"))
  },
  {
    "id": "glimmer-js",
    "name": "Glimmer JS",
    "aliases": ["gjs"],
    "import": (() => import("./glimmer-js-4TADRFJC.js"))
  },
  {
    "id": "glimmer-ts",
    "name": "Glimmer TS",
    "aliases": ["gts"],
    "import": (() => import("./glimmer-ts-VV3BPFM4.js"))
  },
  {
    "id": "glsl",
    "name": "GLSL",
    "import": (() => import("./glsl-IOUSSHZI.js"))
  },
  {
    "id": "gn",
    "name": "GN",
    "import": (() => import("./gn-AYCKDWKP.js"))
  },
  {
    "id": "gnuplot",
    "name": "Gnuplot",
    "import": (() => import("./gnuplot-U4BTXDAF.js"))
  },
  {
    "id": "go",
    "name": "Go",
    "import": (() => import("./go-L6EXAYVY.js"))
  },
  {
    "id": "graphql",
    "name": "GraphQL",
    "aliases": ["gql"],
    "import": (() => import("./graphql-C3IFFOJN.js"))
  },
  {
    "id": "groovy",
    "name": "Groovy",
    "import": (() => import("./groovy-YTZHASHQ.js"))
  },
  {
    "id": "hack",
    "name": "Hack",
    "import": (() => import("./hack-CMLAQOHP.js"))
  },
  {
    "id": "haml",
    "name": "Ruby Haml",
    "import": (() => import("./haml-Y7KHLPUN.js"))
  },
  {
    "id": "handlebars",
    "name": "Handlebars",
    "aliases": ["hbs"],
    "import": (() => import("./handlebars-SFXJNL35.js"))
  },
  {
    "id": "haskell",
    "name": "Haskell",
    "aliases": ["hs"],
    "import": (() => import("./haskell-IUR2775W.js"))
  },
  {
    "id": "haxe",
    "name": "Haxe",
    "import": (() => import("./haxe-CAE64XYZ.js"))
  },
  {
    "id": "hcl",
    "name": "HashiCorp HCL",
    "import": (() => import("./hcl-UNO2YKYB.js"))
  },
  {
    "id": "hjson",
    "name": "Hjson",
    "import": (() => import("./hjson-EI5CXGID.js"))
  },
  {
    "id": "hlsl",
    "name": "HLSL",
    "import": (() => import("./hlsl-23TPT6BT.js"))
  },
  {
    "id": "html",
    "name": "HTML",
    "import": (() => import("./html-PWBVYPCH.js"))
  },
  {
    "id": "html-derivative",
    "name": "HTML (Derivative)",
    "import": (() => import("./html-derivative-OJXV7GOH.js"))
  },
  {
    "id": "http",
    "name": "HTTP",
    "import": (() => import("./http-I54YKVNS.js"))
  },
  {
    "id": "hurl",
    "name": "Hurl",
    "import": (() => import("./hurl-OUY5RQMH.js"))
  },
  {
    "id": "hxml",
    "name": "HXML",
    "import": (() => import("./hxml-7UKF2EPF.js"))
  },
  {
    "id": "hy",
    "name": "Hy",
    "import": (() => import("./hy-H67GWRFX.js"))
  },
  {
    "id": "imba",
    "name": "Imba",
    "import": (() => import("./imba-6RYB6PG3.js"))
  },
  {
    "id": "ini",
    "name": "INI",
    "aliases": ["properties"],
    "import": (() => import("./ini-EZUBEXBK.js"))
  },
  {
    "id": "java",
    "name": "Java",
    "import": (() => import("./java-YCHO66PD.js"))
  },
  {
    "id": "javascript",
    "name": "JavaScript",
    "aliases": [
      "js",
      "cjs",
      "mjs"
    ],
    "import": (() => import("./javascript-XJ3E4YLT.js"))
  },
  {
    "id": "jinja",
    "name": "Jinja",
    "import": (() => import("./jinja-DUNWDNO7.js"))
  },
  {
    "id": "jison",
    "name": "Jison",
    "import": (() => import("./jison-GCXDZD64.js"))
  },
  {
    "id": "json",
    "name": "JSON",
    "import": (() => import("./json-CQEPTFKG.js"))
  },
  {
    "id": "json5",
    "name": "JSON5",
    "import": (() => import("./json5-K5KHBAYL.js"))
  },
  {
    "id": "jsonc",
    "name": "JSON with Comments",
    "import": (() => import("./jsonc-4DNA7TIL.js"))
  },
  {
    "id": "jsonl",
    "name": "JSON Lines",
    "import": (() => import("./jsonl-VEUBAO6Z.js"))
  },
  {
    "id": "jsonnet",
    "name": "Jsonnet",
    "import": (() => import("./jsonnet-R7C4NUSK.js"))
  },
  {
    "id": "jssm",
    "name": "JSSM",
    "aliases": ["fsl"],
    "import": (() => import("./jssm-E243CDWO.js"))
  },
  {
    "id": "jsx",
    "name": "JSX",
    "import": (() => import("./jsx-HJXKVIWA.js"))
  },
  {
    "id": "julia",
    "name": "Julia",
    "aliases": ["jl"],
    "import": (() => import("./julia-KIJW74MN.js"))
  },
  {
    "id": "just",
    "name": "Just",
    "import": (() => import("./just-WUHRRPNH.js"))
  },
  {
    "id": "kdl",
    "name": "KDL",
    "import": (() => import("./kdl-H2OX6VW2.js"))
  },
  {
    "id": "kotlin",
    "name": "Kotlin",
    "aliases": ["kt", "kts"],
    "import": (() => import("./kotlin-TX633YT6.js"))
  },
  {
    "id": "kusto",
    "name": "Kusto",
    "aliases": ["kql"],
    "import": (() => import("./kusto-BJG6IHZ6.js"))
  },
  {
    "id": "latex",
    "name": "LaTeX",
    "import": (() => import("./latex-PCZ7AVU3.js"))
  },
  {
    "id": "lean",
    "name": "Lean 4",
    "aliases": ["lean4"],
    "import": (() => import("./lean-32Q6RS3V.js"))
  },
  {
    "id": "less",
    "name": "Less",
    "import": (() => import("./less-4KKMVWJ4.js"))
  },
  {
    "id": "liquid",
    "name": "Liquid",
    "import": (() => import("./liquid-XML7A7CF.js"))
  },
  {
    "id": "llvm",
    "name": "LLVM IR",
    "import": (() => import("./llvm-XF2J5BXI.js"))
  },
  {
    "id": "log",
    "name": "Log file",
    "import": (() => import("./log-JPBSBA6J.js"))
  },
  {
    "id": "logo",
    "name": "Logo",
    "import": (() => import("./logo-HEA7L366.js"))
  },
  {
    "id": "lua",
    "name": "Lua",
    "import": (() => import("./lua-DUXGJYYX.js"))
  },
  {
    "id": "luau",
    "name": "Luau",
    "import": (() => import("./luau-IEIVARNK.js"))
  },
  {
    "id": "make",
    "name": "Makefile",
    "aliases": ["makefile"],
    "import": (() => import("./make-FTH2OJBI.js"))
  },
  {
    "id": "markdown",
    "name": "Markdown",
    "aliases": ["md"],
    "import": (() => import("./markdown-B3LP4BS4.js"))
  },
  {
    "id": "marko",
    "name": "Marko",
    "import": (() => import("./marko-J2V256GC.js"))
  },
  {
    "id": "matlab",
    "name": "MATLAB",
    "import": (() => import("./matlab-HZYJIRBY.js"))
  },
  {
    "id": "mdc",
    "name": "MDC",
    "import": (() => import("./mdc-MTZ53J3H.js"))
  },
  {
    "id": "mdx",
    "name": "MDX",
    "import": (() => import("./mdx-SQBTS2ZL.js"))
  },
  {
    "id": "mermaid",
    "name": "Mermaid",
    "aliases": ["mmd"],
    "import": (() => import("./mermaid-THGB3GMR.js"))
  },
  {
    "id": "mipsasm",
    "name": "MIPS Assembly",
    "aliases": ["mips"],
    "import": (() => import("./mipsasm-TVHBX7ZX.js"))
  },
  {
    "id": "mojo",
    "name": "Mojo",
    "import": (() => import("./mojo-WK5NLX2W.js"))
  },
  {
    "id": "moonbit",
    "name": "MoonBit",
    "aliases": ["mbt", "mbti"],
    "import": (() => import("./moonbit-VOHCNEAM.js"))
  },
  {
    "id": "move",
    "name": "Move",
    "import": (() => import("./move-7BM74VGP.js"))
  },
  {
    "id": "narrat",
    "name": "Narrat Language",
    "aliases": ["nar"],
    "import": (() => import("./narrat-QFQD2QX4.js"))
  },
  {
    "id": "nextflow",
    "name": "Nextflow",
    "aliases": ["nf"],
    "import": (() => import("./nextflow-WSRQGQVE.js"))
  },
  {
    "id": "nextflow-groovy",
    "name": "Nextflow Groovy",
    "import": (() => import("./nextflow-groovy-RN4MBU5J.js"))
  },
  {
    "id": "nginx",
    "name": "Nginx",
    "import": (() => import("./nginx-VCU3H6YD.js"))
  },
  {
    "id": "nim",
    "name": "Nim",
    "import": (() => import("./nim-MD4ZP3SO.js"))
  },
  {
    "id": "nix",
    "name": "Nix",
    "import": (() => import("./nix-WCTTJ3HF.js"))
  },
  {
    "id": "nushell",
    "name": "nushell",
    "aliases": ["nu"],
    "import": (() => import("./nushell-24GFLRFW.js"))
  },
  {
    "id": "objective-c",
    "name": "Objective-C",
    "aliases": ["objc"],
    "import": (() => import("./objective-c-VHDMS3EP.js"))
  },
  {
    "id": "objective-cpp",
    "name": "Objective-C++",
    "import": (() => import("./objective-cpp-M5ORPGGA.js"))
  },
  {
    "id": "ocaml",
    "name": "OCaml",
    "import": (() => import("./ocaml-MF2GTJFI.js"))
  },
  {
    "id": "odin",
    "name": "Odin",
    "import": (() => import("./odin-3SJYUSKC.js"))
  },
  {
    "id": "openscad",
    "name": "OpenSCAD",
    "aliases": ["scad"],
    "import": (() => import("./openscad-XZLBMQM3.js"))
  },
  {
    "id": "pascal",
    "name": "Pascal",
    "import": (() => import("./pascal-5B5VWRVX.js"))
  },
  {
    "id": "perl",
    "name": "Perl",
    "import": (() => import("./perl-FY3HGT5Q.js"))
  },
  {
    "id": "php",
    "name": "PHP",
    "import": (() => import("./php-XBMCNPT7.js"))
  },
  {
    "id": "pkl",
    "name": "Pkl",
    "import": (() => import("./pkl-VI42MV4G.js"))
  },
  {
    "id": "plsql",
    "name": "PL/SQL",
    "import": (() => import("./plsql-5JIX7KJN.js"))
  },
  {
    "id": "po",
    "name": "Gettext PO",
    "aliases": ["pot", "potx"],
    "import": (() => import("./po-BSCIXOJW.js"))
  },
  {
    "id": "polar",
    "name": "Polar",
    "import": (() => import("./polar-HRR43TZD.js"))
  },
  {
    "id": "postcss",
    "name": "PostCSS",
    "import": (() => import("./postcss-JFV2VK2I.js"))
  },
  {
    "id": "powerquery",
    "name": "PowerQuery",
    "import": (() => import("./powerquery-B27MMMNW.js"))
  },
  {
    "id": "powershell",
    "name": "PowerShell",
    "aliases": ["ps", "ps1"],
    "import": (() => import("./powershell-YXHUMTOJ.js"))
  },
  {
    "id": "prisma",
    "name": "Prisma",
    "import": (() => import("./prisma-HAAV77HM.js"))
  },
  {
    "id": "prolog",
    "name": "Prolog",
    "import": (() => import("./prolog-3DOGLAGM.js"))
  },
  {
    "id": "proto",
    "name": "Protocol Buffer 3",
    "aliases": ["protobuf"],
    "import": (() => import("./proto-G5LQQZEU.js"))
  },
  {
    "id": "pug",
    "name": "Pug",
    "aliases": ["jade"],
    "import": (() => import("./pug-DFDXUKZA.js"))
  },
  {
    "id": "puppet",
    "name": "Puppet",
    "import": (() => import("./puppet-CHHAGW6E.js"))
  },
  {
    "id": "purescript",
    "name": "PureScript",
    "import": (() => import("./purescript-3GQTV474.js"))
  },
  {
    "id": "python",
    "name": "Python",
    "aliases": ["py"],
    "import": (() => import("./python-2LKZMLDY.js"))
  },
  {
    "id": "qml",
    "name": "QML",
    "import": (() => import("./qml-WVSMFWFR.js"))
  },
  {
    "id": "qmldir",
    "name": "QML Directory",
    "import": (() => import("./qmldir-PGPKRK74.js"))
  },
  {
    "id": "qss",
    "name": "Qt Style Sheets",
    "import": (() => import("./qss-SK4MYI5I.js"))
  },
  {
    "id": "r",
    "name": "R",
    "import": (() => import("./r-H66NXBKM.js"))
  },
  {
    "id": "racket",
    "name": "Racket",
    "import": (() => import("./racket-3AZB5GXP.js"))
  },
  {
    "id": "raku",
    "name": "Raku",
    "aliases": ["perl6"],
    "import": (() => import("./raku-RPGA5NGW.js"))
  },
  {
    "id": "razor",
    "name": "ASP.NET Razor",
    "import": (() => import("./razor-KPH2UCEA.js"))
  },
  {
    "id": "reg",
    "name": "Windows Registry Script",
    "import": (() => import("./reg-YKXNLDKJ.js"))
  },
  {
    "id": "regexp",
    "name": "RegExp",
    "aliases": ["regex"],
    "import": (() => import("./regexp-SBPFQWTB.js"))
  },
  {
    "id": "rel",
    "name": "Rel",
    "import": (() => import("./rel-RPNCFDF6.js"))
  },
  {
    "id": "riscv",
    "name": "RISC-V",
    "import": (() => import("./riscv-F67YLXSL.js"))
  },
  {
    "id": "ron",
    "name": "RON",
    "import": (() => import("./ron-GUIWDVZJ.js"))
  },
  {
    "id": "rosmsg",
    "name": "ROS Interface",
    "import": (() => import("./rosmsg-O4LVNB7L.js"))
  },
  {
    "id": "rst",
    "name": "reStructuredText",
    "import": (() => import("./rst-YKLFZIW2.js"))
  },
  {
    "id": "ruby",
    "name": "Ruby",
    "aliases": ["rb"],
    "import": (() => import("./ruby-DWD57X2M.js"))
  },
  {
    "id": "rust",
    "name": "Rust",
    "aliases": ["rs"],
    "import": (() => import("./rust-WS6ZPSQM.js"))
  },
  {
    "id": "sas",
    "name": "SAS",
    "import": (() => import("./sas-4KFCSCI7.js"))
  },
  {
    "id": "sass",
    "name": "Sass",
    "import": (() => import("./sass-YTPAFYVR.js"))
  },
  {
    "id": "scala",
    "name": "Scala",
    "import": (() => import("./scala-QD4VD4ZF.js"))
  },
  {
    "id": "scheme",
    "name": "Scheme",
    "import": (() => import("./scheme-O7T3X6DC.js"))
  },
  {
    "id": "scss",
    "name": "SCSS",
    "import": (() => import("./scss-RX2NMEM2.js"))
  },
  {
    "id": "sdbl",
    "name": "1C (Query)",
    "aliases": ["1c-query"],
    "import": (() => import("./sdbl-BOQ7KEIP.js"))
  },
  {
    "id": "shaderlab",
    "name": "ShaderLab",
    "aliases": ["shader"],
    "import": (() => import("./shaderlab-C422IL2O.js"))
  },
  {
    "id": "shellscript",
    "name": "Shell",
    "aliases": [
      "bash",
      "sh",
      "shell",
      "zsh"
    ],
    "import": (() => import("./shellscript-GORMQL5T.js"))
  },
  {
    "id": "shellsession",
    "name": "Shell Session",
    "aliases": ["console"],
    "import": (() => import("./shellsession-TY5TDCBJ.js"))
  },
  {
    "id": "smalltalk",
    "name": "Smalltalk",
    "import": (() => import("./smalltalk-QXA5W5PP.js"))
  },
  {
    "id": "solidity",
    "name": "Solidity",
    "import": (() => import("./solidity-NZ2THUWT.js"))
  },
  {
    "id": "soy",
    "name": "Closure Templates",
    "aliases": ["closure-templates"],
    "import": (() => import("./soy-IXS33S6G.js"))
  },
  {
    "id": "sparql",
    "name": "SPARQL",
    "import": (() => import("./sparql-QSL44JLS.js"))
  },
  {
    "id": "splunk",
    "name": "Splunk Query Language",
    "aliases": ["spl"],
    "import": (() => import("./splunk-CJHF4OEO.js"))
  },
  {
    "id": "sql",
    "name": "SQL",
    "import": (() => import("./sql-3VLOWNBM.js"))
  },
  {
    "id": "ssh-config",
    "name": "SSH Config",
    "import": (() => import("./ssh-config-STSTSSI4.js"))
  },
  {
    "id": "stata",
    "name": "Stata",
    "import": (() => import("./stata-WA6P6HKQ.js"))
  },
  {
    "id": "stylus",
    "name": "Stylus",
    "aliases": ["styl"],
    "import": (() => import("./stylus-3TF4EO5C.js"))
  },
  {
    "id": "surrealql",
    "name": "SurrealQL",
    "aliases": ["surql"],
    "import": (() => import("./surrealql-PIOSYXVT.js"))
  },
  {
    "id": "svelte",
    "name": "Svelte",
    "import": (() => import("./svelte-ITICC6KS.js"))
  },
  {
    "id": "swift",
    "name": "Swift",
    "import": (() => import("./swift-P4BBSZGS.js"))
  },
  {
    "id": "system-verilog",
    "name": "SystemVerilog",
    "import": (() => import("./system-verilog-PJLU67HT.js"))
  },
  {
    "id": "systemd",
    "name": "Systemd Units",
    "import": (() => import("./systemd-UENEE4ZX.js"))
  },
  {
    "id": "talonscript",
    "name": "TalonScript",
    "aliases": ["talon"],
    "import": (() => import("./talonscript-RKI2NVVQ.js"))
  },
  {
    "id": "tasl",
    "name": "Tasl",
    "import": (() => import("./tasl-KGPFHQ6M.js"))
  },
  {
    "id": "tcl",
    "name": "Tcl",
    "import": (() => import("./tcl-AEKETJNK.js"))
  },
  {
    "id": "templ",
    "name": "Templ",
    "import": (() => import("./templ-JLJZS3G4.js"))
  },
  {
    "id": "terraform",
    "name": "Terraform",
    "aliases": ["tf", "tfvars"],
    "import": (() => import("./terraform-JUENYBL7.js"))
  },
  {
    "id": "tex",
    "name": "TeX",
    "import": (() => import("./tex-V4XWO5SR.js"))
  },
  {
    "id": "toml",
    "name": "TOML",
    "import": (() => import("./toml-LJCY5MHK.js"))
  },
  {
    "id": "ts-tags",
    "name": "TypeScript with Tags",
    "aliases": ["lit"],
    "import": (() => import("./ts-tags-4T4SH45I.js"))
  },
  {
    "id": "tsv",
    "name": "TSV",
    "import": (() => import("./tsv-PVFLZFTF.js"))
  },
  {
    "id": "tsx",
    "name": "TSX",
    "import": (() => import("./tsx-J7XJXNRS.js"))
  },
  {
    "id": "turtle",
    "name": "Turtle",
    "import": (() => import("./turtle-SRC3NW4T.js"))
  },
  {
    "id": "twig",
    "name": "Twig",
    "import": (() => import("./twig-BAJ2NBQA.js"))
  },
  {
    "id": "typescript",
    "name": "TypeScript",
    "aliases": [
      "ts",
      "cts",
      "mts"
    ],
    "import": (() => import("./typescript-ARPP3SPE.js"))
  },
  {
    "id": "typespec",
    "name": "TypeSpec",
    "aliases": ["tsp"],
    "import": (() => import("./typespec-TBQ6WMZM.js"))
  },
  {
    "id": "typst",
    "name": "Typst",
    "aliases": ["typ"],
    "import": (() => import("./typst-LVJ3VMPR.js"))
  },
  {
    "id": "v",
    "name": "V",
    "import": (() => import("./v-G2SSGJIQ.js"))
  },
  {
    "id": "vala",
    "name": "Vala",
    "import": (() => import("./vala-AY3CCVXM.js"))
  },
  {
    "id": "vb",
    "name": "Visual Basic",
    "aliases": ["cmd"],
    "import": (() => import("./vb-QFQF4E7S.js"))
  },
  {
    "id": "verilog",
    "name": "Verilog",
    "import": (() => import("./verilog-GG7CVEEA.js"))
  },
  {
    "id": "vhdl",
    "name": "VHDL",
    "import": (() => import("./vhdl-BXAHXQVV.js"))
  },
  {
    "id": "viml",
    "name": "Vim Script",
    "aliases": ["vim", "vimscript"],
    "import": (() => import("./viml-WQVETWQM.js"))
  },
  {
    "id": "vue",
    "name": "Vue",
    "import": (() => import("./vue-BRZN2FWS.js"))
  },
  {
    "id": "vue-html",
    "name": "Vue HTML",
    "import": (() => import("./vue-html-B3QVXI2I.js"))
  },
  {
    "id": "vue-vine",
    "name": "Vue Vine",
    "import": (() => import("./vue-vine-VEYPXKPX.js"))
  },
  {
    "id": "vyper",
    "name": "Vyper",
    "aliases": ["vy"],
    "import": (() => import("./vyper-MUKQUGIM.js"))
  },
  {
    "id": "wasm",
    "name": "WebAssembly",
    "import": (() => import("./wasm-OUDL4TBR.js"))
  },
  {
    "id": "wenyan",
    "name": "Wenyan",
    "aliases": ["文言"],
    "import": (() => import("./wenyan-2TPP3LAW.js"))
  },
  {
    "id": "wgsl",
    "name": "WGSL",
    "import": (() => import("./wgsl-R6RNAJ7W.js"))
  },
  {
    "id": "wikitext",
    "name": "Wikitext",
    "aliases": ["mediawiki", "wiki"],
    "import": (() => import("./wikitext-LCVQHVGN.js"))
  },
  {
    "id": "wit",
    "name": "WebAssembly Interface Types",
    "import": (() => import("./wit-I5I5QS5Q.js"))
  },
  {
    "id": "wolfram",
    "name": "Wolfram",
    "aliases": ["wl"],
    "import": (() => import("./wolfram-W4DIQU5H.js"))
  },
  {
    "id": "xml",
    "name": "XML",
    "import": (() => import("./xml-675SFOVQ.js"))
  },
  {
    "id": "xsl",
    "name": "XSL",
    "import": (() => import("./xsl-5KIB4VBT.js"))
  },
  {
    "id": "yaml",
    "name": "YAML",
    "aliases": ["yml"],
    "import": (() => import("./yaml-SJOP2IYQ.js"))
  },
  {
    "id": "zenscript",
    "name": "ZenScript",
    "import": (() => import("./zenscript-N3WS4REV.js"))
  },
  {
    "id": "zig",
    "name": "Zig",
    "import": (() => import("./zig-Q55KXT77.js"))
  }
];
var bundledLanguagesBase = Object.fromEntries(bundledLanguagesInfo.map((i) => [i.id, i.import]));
var bundledLanguagesAlias = Object.fromEntries(bundledLanguagesInfo.flatMap((i) => i.aliases?.map((a) => [a, i.import]) || []));
var bundledLanguages = {
  ...bundledLanguagesBase,
  ...bundledLanguagesAlias
};

// node_modules/shiki/dist/themes.mjs
var bundledThemesInfo = [
  {
    "id": "andromeeda",
    "displayName": "Andromeeda",
    "type": "dark",
    "import": (() => import("./andromeeda-PKTNBVEQ.js"))
  },
  {
    "id": "aurora-x",
    "displayName": "Aurora X",
    "type": "dark",
    "import": (() => import("./aurora-x-YOSHQ74P.js"))
  },
  {
    "id": "ayu-dark",
    "displayName": "Ayu Dark",
    "type": "dark",
    "import": (() => import("./ayu-dark-NDVTBNRZ.js"))
  },
  {
    "id": "ayu-light",
    "displayName": "Ayu Light",
    "type": "light",
    "import": (() => import("./ayu-light-TUMQQCOT.js"))
  },
  {
    "id": "ayu-mirage",
    "displayName": "Ayu Mirage",
    "type": "dark",
    "import": (() => import("./ayu-mirage-WQX2UTTI.js"))
  },
  {
    "id": "catppuccin-frappe",
    "displayName": "Catppuccin Frappé",
    "type": "dark",
    "import": (() => import("./catppuccin-frappe-EBAPC5RY.js"))
  },
  {
    "id": "catppuccin-latte",
    "displayName": "Catppuccin Latte",
    "type": "light",
    "import": (() => import("./catppuccin-latte-BWWMY7EY.js"))
  },
  {
    "id": "catppuccin-macchiato",
    "displayName": "Catppuccin Macchiato",
    "type": "dark",
    "import": (() => import("./catppuccin-macchiato-QMMQFUKL.js"))
  },
  {
    "id": "catppuccin-mocha",
    "displayName": "Catppuccin Mocha",
    "type": "dark",
    "import": (() => import("./catppuccin-mocha-QCR2R2K5.js"))
  },
  {
    "id": "dark-plus",
    "displayName": "Dark Plus",
    "type": "dark",
    "import": (() => import("./dark-plus-7I7EMCOI.js"))
  },
  {
    "id": "dracula",
    "displayName": "Dracula Theme",
    "type": "dark",
    "import": (() => import("./dracula-UWOX2M3N.js"))
  },
  {
    "id": "dracula-soft",
    "displayName": "Dracula Theme Soft",
    "type": "dark",
    "import": (() => import("./dracula-soft-BQBBCZ3N.js"))
  },
  {
    "id": "everforest-dark",
    "displayName": "Everforest Dark",
    "type": "dark",
    "import": (() => import("./everforest-dark-LHPARSTD.js"))
  },
  {
    "id": "everforest-light",
    "displayName": "Everforest Light",
    "type": "light",
    "import": (() => import("./everforest-light-LQLRNRXE.js"))
  },
  {
    "id": "github-dark",
    "displayName": "GitHub Dark",
    "type": "dark",
    "import": (() => import("./github-dark-5QCW2VL7.js"))
  },
  {
    "id": "github-dark-default",
    "displayName": "GitHub Dark Default",
    "type": "dark",
    "import": (() => import("./github-dark-default-JMCXE6R5.js"))
  },
  {
    "id": "github-dark-dimmed",
    "displayName": "GitHub Dark Dimmed",
    "type": "dark",
    "import": (() => import("./github-dark-dimmed-5KE7BABK.js"))
  },
  {
    "id": "github-dark-high-contrast",
    "displayName": "GitHub Dark High Contrast",
    "type": "dark",
    "import": (() => import("./github-dark-high-contrast-73WDBDTS.js"))
  },
  {
    "id": "github-light",
    "displayName": "GitHub Light",
    "type": "light",
    "import": (() => import("./github-light-B642F3DD.js"))
  },
  {
    "id": "github-light-default",
    "displayName": "GitHub Light Default",
    "type": "light",
    "import": (() => import("./github-light-default-JQ5NIFTY.js"))
  },
  {
    "id": "github-light-high-contrast",
    "displayName": "GitHub Light High Contrast",
    "type": "light",
    "import": (() => import("./github-light-high-contrast-IPMD3MR6.js"))
  },
  {
    "id": "gruvbox-dark-hard",
    "displayName": "Gruvbox Dark Hard",
    "type": "dark",
    "import": (() => import("./gruvbox-dark-hard-V5NZCWYO.js"))
  },
  {
    "id": "gruvbox-dark-medium",
    "displayName": "Gruvbox Dark Medium",
    "type": "dark",
    "import": (() => import("./gruvbox-dark-medium-VTVGCBSO.js"))
  },
  {
    "id": "gruvbox-dark-soft",
    "displayName": "Gruvbox Dark Soft",
    "type": "dark",
    "import": (() => import("./gruvbox-dark-soft-NBT45MU7.js"))
  },
  {
    "id": "gruvbox-light-hard",
    "displayName": "Gruvbox Light Hard",
    "type": "light",
    "import": (() => import("./gruvbox-light-hard-N6Q45WR6.js"))
  },
  {
    "id": "gruvbox-light-medium",
    "displayName": "Gruvbox Light Medium",
    "type": "light",
    "import": (() => import("./gruvbox-light-medium-NM2QWS2C.js"))
  },
  {
    "id": "gruvbox-light-soft",
    "displayName": "Gruvbox Light Soft",
    "type": "light",
    "import": (() => import("./gruvbox-light-soft-MHHTGYU3.js"))
  },
  {
    "id": "horizon",
    "displayName": "Horizon",
    "type": "dark",
    "import": (() => import("./horizon-SZDYIK2U.js"))
  },
  {
    "id": "horizon-bright",
    "displayName": "Horizon Bright",
    "type": "light",
    "import": (() => import("./horizon-bright-4NH5FB24.js"))
  },
  {
    "id": "houston",
    "displayName": "Houston",
    "type": "dark",
    "import": (() => import("./houston-EFYF2EZS.js"))
  },
  {
    "id": "kanagawa-dragon",
    "displayName": "Kanagawa Dragon",
    "type": "dark",
    "import": (() => import("./kanagawa-dragon-DXCGJO5O.js"))
  },
  {
    "id": "kanagawa-lotus",
    "displayName": "Kanagawa Lotus",
    "type": "light",
    "import": (() => import("./kanagawa-lotus-ZMK4Z4GB.js"))
  },
  {
    "id": "kanagawa-wave",
    "displayName": "Kanagawa Wave",
    "type": "dark",
    "import": (() => import("./kanagawa-wave-ITXOPKSM.js"))
  },
  {
    "id": "laserwave",
    "displayName": "LaserWave",
    "type": "dark",
    "import": (() => import("./laserwave-K7UJZX2C.js"))
  },
  {
    "id": "light-plus",
    "displayName": "Light Plus",
    "type": "light",
    "import": (() => import("./light-plus-3STZRL2L.js"))
  },
  {
    "id": "material-theme",
    "displayName": "Material Theme",
    "type": "dark",
    "import": (() => import("./material-theme-CKV6EPN4.js"))
  },
  {
    "id": "material-theme-darker",
    "displayName": "Material Theme Darker",
    "type": "dark",
    "import": (() => import("./material-theme-darker-FGUZ2MVG.js"))
  },
  {
    "id": "material-theme-lighter",
    "displayName": "Material Theme Lighter",
    "type": "light",
    "import": (() => import("./material-theme-lighter-CEFS4O5F.js"))
  },
  {
    "id": "material-theme-ocean",
    "displayName": "Material Theme Ocean",
    "type": "dark",
    "import": (() => import("./material-theme-ocean-LJWNLTPJ.js"))
  },
  {
    "id": "material-theme-palenight",
    "displayName": "Material Theme Palenight",
    "type": "dark",
    "import": (() => import("./material-theme-palenight-5WNDME27.js"))
  },
  {
    "id": "min-dark",
    "displayName": "Min Dark",
    "type": "dark",
    "import": (() => import("./min-dark-ROJEZI5C.js"))
  },
  {
    "id": "min-light",
    "displayName": "Min Light",
    "type": "light",
    "import": (() => import("./min-light-JMFNY3SZ.js"))
  },
  {
    "id": "monokai",
    "displayName": "Monokai",
    "type": "dark",
    "import": (() => import("./monokai-WYX7GIFY.js"))
  },
  {
    "id": "night-owl",
    "displayName": "Night Owl",
    "type": "dark",
    "import": (() => import("./night-owl-A6NW3GHJ.js"))
  },
  {
    "id": "night-owl-light",
    "displayName": "Night Owl Light",
    "type": "light",
    "import": (() => import("./night-owl-light-IXHZ5ZEB.js"))
  },
  {
    "id": "nord",
    "displayName": "Nord",
    "type": "dark",
    "import": (() => import("./nord-ZD6U4RCH.js"))
  },
  {
    "id": "one-dark-pro",
    "displayName": "One Dark Pro",
    "type": "dark",
    "import": (() => import("./one-dark-pro-SAAZTZK4.js"))
  },
  {
    "id": "one-light",
    "displayName": "One Light",
    "type": "light",
    "import": (() => import("./one-light-XAAHPWDU.js"))
  },
  {
    "id": "plastic",
    "displayName": "Plastic",
    "type": "dark",
    "import": (() => import("./plastic-NNBF62EZ.js"))
  },
  {
    "id": "poimandres",
    "displayName": "Poimandres",
    "type": "dark",
    "import": (() => import("./poimandres-5VXNPD7F.js"))
  },
  {
    "id": "red",
    "displayName": "Red",
    "type": "dark",
    "import": (() => import("./red-7XSQ5JMB.js"))
  },
  {
    "id": "rose-pine",
    "displayName": "Rosé Pine",
    "type": "dark",
    "import": (() => import("./rose-pine-Q6XXORNE.js"))
  },
  {
    "id": "rose-pine-dawn",
    "displayName": "Rosé Pine Dawn",
    "type": "light",
    "import": (() => import("./rose-pine-dawn-W5OJ3UIN.js"))
  },
  {
    "id": "rose-pine-moon",
    "displayName": "Rosé Pine Moon",
    "type": "dark",
    "import": (() => import("./rose-pine-moon-AMTFKWUB.js"))
  },
  {
    "id": "slack-dark",
    "displayName": "Slack Dark",
    "type": "dark",
    "import": (() => import("./slack-dark-YFDSUXNS.js"))
  },
  {
    "id": "slack-ochin",
    "displayName": "Slack Ochin",
    "type": "light",
    "import": (() => import("./slack-ochin-TOJKNFGR.js"))
  },
  {
    "id": "snazzy-light",
    "displayName": "Snazzy Light",
    "type": "light",
    "import": (() => import("./snazzy-light-UTBQWCWO.js"))
  },
  {
    "id": "solarized-dark",
    "displayName": "Solarized Dark",
    "type": "dark",
    "import": (() => import("./solarized-dark-H332KCAV.js"))
  },
  {
    "id": "solarized-light",
    "displayName": "Solarized Light",
    "type": "light",
    "import": (() => import("./solarized-light-7T25DPJT.js"))
  },
  {
    "id": "synthwave-84",
    "displayName": "Synthwave '84",
    "type": "dark",
    "import": (() => import("./synthwave-84-FG4QWYK7.js"))
  },
  {
    "id": "tokyo-night",
    "displayName": "Tokyo Night",
    "type": "dark",
    "import": (() => import("./tokyo-night-XHS5IA5R.js"))
  },
  {
    "id": "vesper",
    "displayName": "Vesper",
    "type": "dark",
    "import": (() => import("./vesper-T2BC7MUP.js"))
  },
  {
    "id": "vitesse-black",
    "displayName": "Vitesse Black",
    "type": "dark",
    "import": (() => import("./vitesse-black-LVTIUMYL.js"))
  },
  {
    "id": "vitesse-dark",
    "displayName": "Vitesse Dark",
    "type": "dark",
    "import": (() => import("./vitesse-dark-LNSSI4J6.js"))
  },
  {
    "id": "vitesse-light",
    "displayName": "Vitesse Light",
    "type": "light",
    "import": (() => import("./vitesse-light-JTT2NL7N.js"))
  }
];
var bundledThemes = Object.fromEntries(bundledThemesInfo.map((i) => [i.id, i.import]));

// node_modules/@shikijs/engine-oniguruma/dist/index.mjs
var dist_exports = {};
__export(dist_exports, {
  createOnigurumaEngine: () => createOnigurumaEngine,
  getDefaultWasmLoader: () => getDefaultWasmLoader,
  loadWasm: () => loadWasm,
  setDefaultWasmLoader: () => setDefaultWasmLoader
});
var ShikiError = class extends Error {
  constructor(message) {
    super(message);
    this.name = "ShikiError";
  }
};
function getHeapMax() {
  return 2147483648;
}
function _emscripten_get_now() {
  return typeof performance !== "undefined" ? performance.now() : Date.now();
}
var alignUp = (x, multiple) => x + (multiple - x % multiple) % multiple;
async function main(init) {
  let wasmMemory;
  let buffer;
  const binding = {};
  function updateGlobalBufferAndViews(buf) {
    buffer = buf;
    binding.HEAPU8 = new Uint8Array(buf);
    binding.HEAPU32 = new Uint32Array(buf);
  }
  function _emscripten_memcpy_big(dest, src, num) {
    binding.HEAPU8.copyWithin(dest, src, src + num);
  }
  function emscripten_realloc_buffer(size) {
    try {
      wasmMemory.grow(size - buffer.byteLength + 65535 >>> 16);
      updateGlobalBufferAndViews(wasmMemory.buffer);
      return 1;
    } catch {
    }
  }
  function _emscripten_resize_heap(requestedSize) {
    const oldSize = binding.HEAPU8.length;
    requestedSize = requestedSize >>> 0;
    const maxHeapSize = getHeapMax();
    if (requestedSize > maxHeapSize)
      return false;
    for (let cutDown = 1; cutDown <= 4; cutDown *= 2) {
      let overGrownHeapSize = oldSize * (1 + 0.2 / cutDown);
      overGrownHeapSize = Math.min(overGrownHeapSize, requestedSize + 100663296);
      const newSize = Math.min(maxHeapSize, alignUp(Math.max(requestedSize, overGrownHeapSize), 65536));
      const replacement = emscripten_realloc_buffer(newSize);
      if (replacement)
        return true;
    }
    return false;
  }
  const UTF8Decoder = typeof TextDecoder != "undefined" ? new TextDecoder("utf8") : void 0;
  function UTF8ArrayToString(heapOrArray, idx, maxBytesToRead = 1024) {
    const endIdx = idx + maxBytesToRead;
    let endPtr = idx;
    while (heapOrArray[endPtr] && !(endPtr >= endIdx)) ++endPtr;
    if (endPtr - idx > 16 && heapOrArray.buffer && UTF8Decoder) {
      return UTF8Decoder.decode(heapOrArray.subarray(idx, endPtr));
    }
    let str = "";
    while (idx < endPtr) {
      let u0 = heapOrArray[idx++];
      if (!(u0 & 128)) {
        str += String.fromCharCode(u0);
        continue;
      }
      const u1 = heapOrArray[idx++] & 63;
      if ((u0 & 224) === 192) {
        str += String.fromCharCode((u0 & 31) << 6 | u1);
        continue;
      }
      const u2 = heapOrArray[idx++] & 63;
      if ((u0 & 240) === 224) {
        u0 = (u0 & 15) << 12 | u1 << 6 | u2;
      } else {
        u0 = (u0 & 7) << 18 | u1 << 12 | u2 << 6 | heapOrArray[idx++] & 63;
      }
      if (u0 < 65536) {
        str += String.fromCharCode(u0);
      } else {
        const ch = u0 - 65536;
        str += String.fromCharCode(55296 | ch >> 10, 56320 | ch & 1023);
      }
    }
    return str;
  }
  function UTF8ToString(ptr, maxBytesToRead) {
    return ptr ? UTF8ArrayToString(binding.HEAPU8, ptr, maxBytesToRead) : "";
  }
  const asmLibraryArg = {
    emscripten_get_now: _emscripten_get_now,
    emscripten_memcpy_big: _emscripten_memcpy_big,
    emscripten_resize_heap: _emscripten_resize_heap,
    fd_write: () => 0
  };
  async function createWasm() {
    const info = {
      env: asmLibraryArg,
      wasi_snapshot_preview1: asmLibraryArg
    };
    const exports = await init(info);
    wasmMemory = exports.memory;
    updateGlobalBufferAndViews(wasmMemory.buffer);
    Object.assign(binding, exports);
    binding.UTF8ToString = UTF8ToString;
  }
  await createWasm();
  return binding;
}
var __defProp2 = Object.defineProperty;
var __defNormalProp = (obj, key, value) => key in obj ? __defProp2(obj, key, { enumerable: true, configurable: true, writable: true, value }) : obj[key] = value;
var __publicField = (obj, key, value) => __defNormalProp(obj, typeof key !== "symbol" ? key + "" : key, value);
var onigBinding = null;
function throwLastOnigError(onigBinding2) {
  throw new ShikiError(onigBinding2.UTF8ToString(onigBinding2.getLastOnigError()));
}
var UtfString = class _UtfString {
  constructor(str) {
    __publicField(this, "utf16Length");
    __publicField(this, "utf8Length");
    __publicField(this, "utf16Value");
    __publicField(this, "utf8Value");
    __publicField(this, "utf16OffsetToUtf8");
    __publicField(this, "utf8OffsetToUtf16");
    const utf16Length = str.length;
    const utf8Length = _UtfString._utf8ByteLength(str);
    const computeIndicesMapping = utf8Length !== utf16Length;
    const utf16OffsetToUtf8 = computeIndicesMapping ? new Uint32Array(utf16Length + 1) : null;
    if (computeIndicesMapping)
      utf16OffsetToUtf8[utf16Length] = utf8Length;
    const utf8OffsetToUtf16 = computeIndicesMapping ? new Uint32Array(utf8Length + 1) : null;
    if (computeIndicesMapping)
      utf8OffsetToUtf16[utf8Length] = utf16Length;
    const utf8Value = new Uint8Array(utf8Length);
    let i8 = 0;
    for (let i16 = 0; i16 < utf16Length; i16++) {
      const charCode = str.charCodeAt(i16);
      let codePoint = charCode;
      let wasSurrogatePair = false;
      if (charCode >= 55296 && charCode <= 56319) {
        if (i16 + 1 < utf16Length) {
          const nextCharCode = str.charCodeAt(i16 + 1);
          if (nextCharCode >= 56320 && nextCharCode <= 57343) {
            codePoint = (charCode - 55296 << 10) + 65536 | nextCharCode - 56320;
            wasSurrogatePair = true;
          }
        }
      }
      if (computeIndicesMapping) {
        utf16OffsetToUtf8[i16] = i8;
        if (wasSurrogatePair)
          utf16OffsetToUtf8[i16 + 1] = i8;
        if (codePoint <= 127) {
          utf8OffsetToUtf16[i8 + 0] = i16;
        } else if (codePoint <= 2047) {
          utf8OffsetToUtf16[i8 + 0] = i16;
          utf8OffsetToUtf16[i8 + 1] = i16;
        } else if (codePoint <= 65535) {
          utf8OffsetToUtf16[i8 + 0] = i16;
          utf8OffsetToUtf16[i8 + 1] = i16;
          utf8OffsetToUtf16[i8 + 2] = i16;
        } else {
          utf8OffsetToUtf16[i8 + 0] = i16;
          utf8OffsetToUtf16[i8 + 1] = i16;
          utf8OffsetToUtf16[i8 + 2] = i16;
          utf8OffsetToUtf16[i8 + 3] = i16;
        }
      }
      if (codePoint <= 127) {
        utf8Value[i8++] = codePoint;
      } else if (codePoint <= 2047) {
        utf8Value[i8++] = 192 | (codePoint & 1984) >>> 6;
        utf8Value[i8++] = 128 | (codePoint & 63) >>> 0;
      } else if (codePoint <= 65535) {
        utf8Value[i8++] = 224 | (codePoint & 61440) >>> 12;
        utf8Value[i8++] = 128 | (codePoint & 4032) >>> 6;
        utf8Value[i8++] = 128 | (codePoint & 63) >>> 0;
      } else {
        utf8Value[i8++] = 240 | (codePoint & 1835008) >>> 18;
        utf8Value[i8++] = 128 | (codePoint & 258048) >>> 12;
        utf8Value[i8++] = 128 | (codePoint & 4032) >>> 6;
        utf8Value[i8++] = 128 | (codePoint & 63) >>> 0;
      }
      if (wasSurrogatePair)
        i16++;
    }
    this.utf16Length = utf16Length;
    this.utf8Length = utf8Length;
    this.utf16Value = str;
    this.utf8Value = utf8Value;
    this.utf16OffsetToUtf8 = utf16OffsetToUtf8;
    this.utf8OffsetToUtf16 = utf8OffsetToUtf16;
  }
  static _utf8ByteLength(str) {
    let result = 0;
    for (let i = 0, len = str.length; i < len; i++) {
      const charCode = str.charCodeAt(i);
      let codepoint = charCode;
      let wasSurrogatePair = false;
      if (charCode >= 55296 && charCode <= 56319) {
        if (i + 1 < len) {
          const nextCharCode = str.charCodeAt(i + 1);
          if (nextCharCode >= 56320 && nextCharCode <= 57343) {
            codepoint = (charCode - 55296 << 10) + 65536 | nextCharCode - 56320;
            wasSurrogatePair = true;
          }
        }
      }
      if (codepoint <= 127)
        result += 1;
      else if (codepoint <= 2047)
        result += 2;
      else if (codepoint <= 65535)
        result += 3;
      else
        result += 4;
      if (wasSurrogatePair)
        i++;
    }
    return result;
  }
  createString(onigBinding2) {
    const result = onigBinding2.omalloc(this.utf8Length);
    onigBinding2.HEAPU8.set(this.utf8Value, result);
    return result;
  }
};
var _OnigString = class _OnigString2 {
  constructor(str) {
    __publicField(this, "id", ++_OnigString2.LAST_ID);
    __publicField(this, "_onigBinding");
    __publicField(this, "content");
    __publicField(this, "utf16Length");
    __publicField(this, "utf8Length");
    __publicField(this, "utf16OffsetToUtf8");
    __publicField(this, "utf8OffsetToUtf16");
    __publicField(this, "ptr");
    if (!onigBinding)
      throw new ShikiError("Must invoke loadWasm first.");
    this._onigBinding = onigBinding;
    this.content = str;
    const utfString = new UtfString(str);
    this.utf16Length = utfString.utf16Length;
    this.utf8Length = utfString.utf8Length;
    this.utf16OffsetToUtf8 = utfString.utf16OffsetToUtf8;
    this.utf8OffsetToUtf16 = utfString.utf8OffsetToUtf16;
    if (this.utf8Length < 1e4 && !_OnigString2._sharedPtrInUse) {
      if (!_OnigString2._sharedPtr)
        _OnigString2._sharedPtr = onigBinding.omalloc(1e4);
      _OnigString2._sharedPtrInUse = true;
      onigBinding.HEAPU8.set(utfString.utf8Value, _OnigString2._sharedPtr);
      this.ptr = _OnigString2._sharedPtr;
    } else {
      this.ptr = utfString.createString(onigBinding);
    }
  }
  convertUtf8OffsetToUtf16(utf8Offset) {
    if (this.utf8OffsetToUtf16) {
      if (utf8Offset < 0)
        return 0;
      if (utf8Offset > this.utf8Length)
        return this.utf16Length;
      return this.utf8OffsetToUtf16[utf8Offset];
    }
    return utf8Offset;
  }
  convertUtf16OffsetToUtf8(utf16Offset) {
    if (this.utf16OffsetToUtf8) {
      if (utf16Offset < 0)
        return 0;
      if (utf16Offset > this.utf16Length)
        return this.utf8Length;
      return this.utf16OffsetToUtf8[utf16Offset];
    }
    return utf16Offset;
  }
  dispose() {
    if (this.ptr === _OnigString2._sharedPtr)
      _OnigString2._sharedPtrInUse = false;
    else
      this._onigBinding.ofree(this.ptr);
  }
};
__publicField(_OnigString, "LAST_ID", 0);
__publicField(_OnigString, "_sharedPtr", 0);
__publicField(_OnigString, "_sharedPtrInUse", false);
var OnigString = _OnigString;
var OnigScanner = class {
  constructor(patterns) {
    __publicField(this, "_onigBinding");
    __publicField(this, "_ptr");
    if (!onigBinding)
      throw new ShikiError("Must invoke loadWasm first.");
    const strPtrsArr = [];
    const strLenArr = [];
    for (let i = 0, len = patterns.length; i < len; i++) {
      const utfString = new UtfString(patterns[i]);
      strPtrsArr[i] = utfString.createString(onigBinding);
      strLenArr[i] = utfString.utf8Length;
    }
    const strPtrsPtr = onigBinding.omalloc(4 * patterns.length);
    onigBinding.HEAPU32.set(strPtrsArr, strPtrsPtr / 4);
    const strLenPtr = onigBinding.omalloc(4 * patterns.length);
    onigBinding.HEAPU32.set(strLenArr, strLenPtr / 4);
    const scannerPtr = onigBinding.createOnigScanner(strPtrsPtr, strLenPtr, patterns.length);
    for (let i = 0, len = patterns.length; i < len; i++)
      onigBinding.ofree(strPtrsArr[i]);
    onigBinding.ofree(strLenPtr);
    onigBinding.ofree(strPtrsPtr);
    if (scannerPtr === 0)
      throwLastOnigError(onigBinding);
    this._onigBinding = onigBinding;
    this._ptr = scannerPtr;
  }
  dispose() {
    this._onigBinding.freeOnigScanner(this._ptr);
  }
  findNextMatchSync(string, startPosition, arg) {
    let options = 0;
    if (typeof arg === "number") {
      options = arg;
    }
    if (typeof string === "string") {
      string = new OnigString(string);
      const result = this._findNextMatchSync(string, startPosition, false, options);
      string.dispose();
      return result;
    }
    return this._findNextMatchSync(string, startPosition, false, options);
  }
  _findNextMatchSync(string, startPosition, debugCall, options) {
    const onigBinding2 = this._onigBinding;
    const resultPtr = onigBinding2.findNextOnigScannerMatch(this._ptr, string.id, string.ptr, string.utf8Length, string.convertUtf16OffsetToUtf8(startPosition), options);
    if (resultPtr === 0) {
      return null;
    }
    const HEAPU32 = onigBinding2.HEAPU32;
    let offset = resultPtr / 4;
    const index = HEAPU32[offset++];
    const count = HEAPU32[offset++];
    const captureIndices = [];
    for (let i = 0; i < count; i++) {
      const beg = string.convertUtf8OffsetToUtf16(HEAPU32[offset++]);
      const end = string.convertUtf8OffsetToUtf16(HEAPU32[offset++]);
      captureIndices[i] = {
        start: beg,
        end,
        length: end - beg
      };
    }
    return {
      index,
      captureIndices
    };
  }
};
function isInstantiatorOptionsObject(dataOrOptions) {
  return typeof dataOrOptions.instantiator === "function";
}
function isInstantiatorModule(dataOrOptions) {
  return typeof dataOrOptions.default === "function";
}
function isDataOptionsObject(dataOrOptions) {
  return typeof dataOrOptions.data !== "undefined";
}
function isResponse(dataOrOptions) {
  return typeof Response !== "undefined" && dataOrOptions instanceof Response;
}
function isArrayBuffer(data) {
  return typeof ArrayBuffer !== "undefined" && (data instanceof ArrayBuffer || ArrayBuffer.isView(data)) || typeof Buffer !== "undefined" && Buffer.isBuffer?.(data) || typeof SharedArrayBuffer !== "undefined" && data instanceof SharedArrayBuffer || typeof Uint32Array !== "undefined" && data instanceof Uint32Array;
}
var initPromise;
function loadWasm(options) {
  if (initPromise)
    return initPromise;
  async function _load() {
    onigBinding = await main(async (info) => {
      let instance = options;
      instance = await instance;
      if (typeof instance === "function")
        instance = await instance(info);
      if (typeof instance === "function")
        instance = await instance(info);
      if (isInstantiatorOptionsObject(instance)) {
        instance = await instance.instantiator(info);
      } else if (isInstantiatorModule(instance)) {
        instance = await instance.default(info);
      } else {
        if (isDataOptionsObject(instance))
          instance = instance.data;
        if (isResponse(instance)) {
          if (typeof WebAssembly.instantiateStreaming === "function")
            instance = await _makeResponseStreamingLoader(instance)(info);
          else
            instance = await _makeResponseNonStreamingLoader(instance)(info);
        } else if (isArrayBuffer(instance)) {
          instance = await _makeArrayBufferLoader(instance)(info);
        } else if (instance instanceof WebAssembly.Module) {
          instance = await _makeArrayBufferLoader(instance)(info);
        } else if ("default" in instance && instance.default instanceof WebAssembly.Module) {
          instance = await _makeArrayBufferLoader(instance.default)(info);
        }
      }
      if ("instance" in instance)
        instance = instance.instance;
      if ("exports" in instance)
        instance = instance.exports;
      return instance;
    });
  }
  initPromise = _load();
  return initPromise;
}
function _makeArrayBufferLoader(data) {
  return (importObject) => WebAssembly.instantiate(data, importObject);
}
function _makeResponseStreamingLoader(data) {
  return (importObject) => WebAssembly.instantiateStreaming(data, importObject);
}
function _makeResponseNonStreamingLoader(data) {
  return async (importObject) => {
    const arrayBuffer = await data.arrayBuffer();
    return WebAssembly.instantiate(arrayBuffer, importObject);
  };
}
var _defaultWasmLoader;
function setDefaultWasmLoader(_loader) {
  _defaultWasmLoader = _loader;
}
function getDefaultWasmLoader() {
  return _defaultWasmLoader;
}
async function createOnigurumaEngine(options) {
  if (options)
    await loadWasm(options);
  return {
    createScanner(patterns) {
      return new OnigScanner(patterns.map((p) => typeof p === "string" ? p : p.source));
    },
    createString(s) {
      return new OnigString(s);
    }
  };
}

// node_modules/shiki/dist/engine-oniguruma.mjs
var engine_oniguruma_exports = __exportAll({});
__reExport(engine_oniguruma_exports, dist_exports);

// node_modules/@shikijs/types/dist/index.mjs
var ShikiError2 = class extends Error {
  constructor(message) {
    super(message);
    this.name = "ShikiError";
  }
};

// node_modules/@shikijs/primitive/dist/index.mjs
function resolveColorReplacements(theme, options) {
  const replacements = typeof theme === "string" ? {} : { ...theme.colorReplacements };
  const themeName = typeof theme === "string" ? theme : theme.name;
  for (const [key, value] of Object.entries(options?.colorReplacements || {})) if (typeof value === "string") replacements[key] = value;
  else if (key === themeName) Object.assign(replacements, value);
  return replacements;
}
function applyColorReplacements(color, replacements) {
  if (!color) return color;
  return replacements?.[color?.toLowerCase()] || color;
}
function toArray(x) {
  return Array.isArray(x) ? x : [x];
}
async function normalizeGetter(p) {
  return Promise.resolve(typeof p === "function" ? p() : p).then((r) => r.default || r);
}
function isPlainLang(lang) {
  return !lang || [
    "plaintext",
    "txt",
    "text",
    "plain"
  ].includes(lang);
}
function isSpecialLang(lang) {
  return lang === "ansi" || isPlainLang(lang);
}
function isNoneTheme(theme) {
  return theme === "none";
}
function isSpecialTheme(theme) {
  return isNoneTheme(theme);
}
var RE_NEWLINE = /(\r?\n)/g;
function splitLines(code, preserveEnding = false) {
  if (code.length === 0) return [["", 0]];
  const parts = code.split(RE_NEWLINE);
  let index = 0;
  const lines = [];
  for (let i = 0; i < parts.length; i += 2) {
    const line = preserveEnding ? parts[i] + (parts[i + 1] || "") : parts[i];
    lines.push([line, index]);
    index += parts[i].length;
    index += parts[i + 1]?.length || 0;
  }
  return lines;
}
var VSCODE_FALLBACK_EDITOR_FG = {
  light: "#333333",
  dark: "#bbbbbb"
};
var VSCODE_FALLBACK_EDITOR_BG = {
  light: "#fffffe",
  dark: "#1e1e1e"
};
var RESOLVED_KEY = "__shiki_resolved";
function normalizeTheme(rawTheme) {
  if (rawTheme?.[RESOLVED_KEY]) return rawTheme;
  const theme = { ...rawTheme };
  if (theme.tokenColors && !theme.settings) {
    theme.settings = theme.tokenColors;
    delete theme.tokenColors;
  }
  theme.type ||= "dark";
  theme.colorReplacements = { ...theme.colorReplacements };
  theme.settings ||= [];
  let { bg, fg } = theme;
  if (!bg || !fg) {
    const globalSetting = theme.settings ? theme.settings.find((s) => !s.name && !s.scope) : void 0;
    if (globalSetting?.settings?.foreground) fg = globalSetting.settings.foreground;
    if (globalSetting?.settings?.background) bg = globalSetting.settings.background;
    if (!fg && theme?.colors?.["editor.foreground"]) fg = theme.colors["editor.foreground"];
    if (!bg && theme?.colors?.["editor.background"]) bg = theme.colors["editor.background"];
    if (!fg) fg = theme.type === "light" ? VSCODE_FALLBACK_EDITOR_FG.light : VSCODE_FALLBACK_EDITOR_FG.dark;
    if (!bg) bg = theme.type === "light" ? VSCODE_FALLBACK_EDITOR_BG.light : VSCODE_FALLBACK_EDITOR_BG.dark;
    theme.fg = fg;
    theme.bg = bg;
  }
  if (!(theme.settings[0] && theme.settings[0].settings && !theme.settings[0].scope)) theme.settings.unshift({ settings: {
    foreground: theme.fg,
    background: theme.bg
  } });
  let replacementCount = 0;
  const replacementMap = /* @__PURE__ */ new Map();
  function getReplacementColor(value) {
    if (replacementMap.has(value)) return replacementMap.get(value);
    replacementCount += 1;
    const hex = `#${replacementCount.toString(16).padStart(8, "0").toLowerCase()}`;
    if (theme.colorReplacements?.[`#${hex}`]) return getReplacementColor(value);
    replacementMap.set(value, hex);
    return hex;
  }
  theme.settings = theme.settings.map((setting) => {
    const replaceFg = setting.settings?.foreground && !setting.settings.foreground.startsWith("#");
    const replaceBg = setting.settings?.background && !setting.settings.background.startsWith("#");
    if (!replaceFg && !replaceBg) return setting;
    const clone = {
      ...setting,
      settings: { ...setting.settings }
    };
    if (replaceFg) {
      const replacement = getReplacementColor(setting.settings.foreground);
      theme.colorReplacements[replacement] = setting.settings.foreground;
      clone.settings.foreground = replacement;
    }
    if (replaceBg) {
      const replacement = getReplacementColor(setting.settings.background);
      theme.colorReplacements[replacement] = setting.settings.background;
      clone.settings.background = replacement;
    }
    return clone;
  });
  for (const key of Object.keys(theme.colors || {})) if (key === "editor.foreground" || key === "editor.background" || key.startsWith("terminal.ansi")) {
    if (!theme.colors[key]?.startsWith("#")) {
      const replacement = getReplacementColor(theme.colors[key]);
      theme.colorReplacements[replacement] = theme.colors[key];
      theme.colors[key] = replacement;
    }
  }
  Object.defineProperty(theme, RESOLVED_KEY, {
    enumerable: false,
    writable: false,
    value: true
  });
  return theme;
}
async function resolveLangs(langs) {
  return [...new Set((await Promise.all(langs.filter((l) => !isSpecialLang(l)).map(async (lang) => await normalizeGetter(lang).then((r) => Array.isArray(r) ? r : [r])))).flat())];
}
async function resolveThemes(themes) {
  return (await Promise.all(themes.map(async (theme) => isSpecialTheme(theme) ? null : normalizeTheme(await normalizeGetter(theme))))).filter((i) => !!i);
}
function resolveLangAlias(name, alias) {
  if (!alias) return name;
  if (alias[name]) {
    const resolved = /* @__PURE__ */ new Set([name]);
    while (alias[name]) {
      name = alias[name];
      if (resolved.has(name)) throw new ShikiError2(`Circular alias \`${[...resolved].join(" -> ")} -> ${name}\``);
      resolved.add(name);
    }
  }
  return name;
}
var Registry2 = class extends Registry {
  _resolver;
  _themes;
  _langs;
  _alias;
  _resolvedThemes = /* @__PURE__ */ new Map();
  _resolvedGrammars = /* @__PURE__ */ new Map();
  _langMap = /* @__PURE__ */ new Map();
  _langGraph = /* @__PURE__ */ new Map();
  _textmateThemeCache = /* @__PURE__ */ new WeakMap();
  _loadedThemesCache = null;
  _loadedLanguagesCache = null;
  constructor(_resolver, _themes, _langs, _alias = {}) {
    super(_resolver);
    this._resolver = _resolver;
    this._themes = _themes;
    this._langs = _langs;
    this._alias = _alias;
    this._themes.map((t) => this.loadTheme(t));
    this.loadLanguages(this._langs);
  }
  getTheme(theme) {
    if (typeof theme === "string") return this._resolvedThemes.get(theme);
    else return this.loadTheme(theme);
  }
  loadTheme(theme) {
    const _theme = normalizeTheme(theme);
    if (_theme.name) {
      this._resolvedThemes.set(_theme.name, _theme);
      this._loadedThemesCache = null;
    }
    return _theme;
  }
  getLoadedThemes() {
    if (!this._loadedThemesCache) this._loadedThemesCache = [...this._resolvedThemes.keys()];
    return this._loadedThemesCache;
  }
  setTheme(theme) {
    let textmateTheme = this._textmateThemeCache.get(theme);
    if (!textmateTheme) {
      textmateTheme = Theme.createFromRawTheme(theme);
      this._textmateThemeCache.set(theme, textmateTheme);
    }
    this._syncRegistry.setTheme(textmateTheme);
  }
  getGrammar(name) {
    name = resolveLangAlias(name, this._alias);
    return this._resolvedGrammars.get(name);
  }
  loadLanguage(lang) {
    if (this.getGrammar(lang.name)) return;
    const embeddedLazilyBy = new Set([...this._langMap.values()].filter((i) => i.embeddedLangsLazy?.includes(lang.name)));
    this._resolver.addLanguage(lang);
    const grammarConfig = {
      balancedBracketSelectors: lang.balancedBracketSelectors || ["*"],
      unbalancedBracketSelectors: lang.unbalancedBracketSelectors || []
    };
    this._syncRegistry._rawGrammars.set(lang.scopeName, lang);
    const g = this.loadGrammarWithConfiguration(lang.scopeName, 1, grammarConfig);
    g.name = lang.name;
    this._resolvedGrammars.set(lang.name, g);
    if (lang.aliases) lang.aliases.forEach((alias) => {
      this._alias[alias] = lang.name;
    });
    this._loadedLanguagesCache = null;
    if (embeddedLazilyBy.size) for (const e of embeddedLazilyBy) {
      this._resolvedGrammars.delete(e.name);
      this._loadedLanguagesCache = null;
      this._syncRegistry?._injectionGrammars?.delete(e.scopeName);
      this._syncRegistry?._grammars?.delete(e.scopeName);
      this.loadLanguage(this._langMap.get(e.name));
    }
  }
  dispose() {
    super.dispose();
    this._resolvedThemes.clear();
    this._resolvedGrammars.clear();
    this._langMap.clear();
    this._langGraph.clear();
    this._loadedThemesCache = null;
  }
  loadLanguages(langs) {
    for (const lang of langs) this.resolveEmbeddedLanguages(lang);
    const langsGraphArray = [...this._langGraph.entries()];
    const missingLangs = langsGraphArray.filter(([_, lang]) => !lang);
    if (missingLangs.length) {
      const dependents = langsGraphArray.filter(([_, lang]) => {
        if (!lang) return false;
        return (lang.embeddedLanguages || lang.embeddedLangs)?.some((l) => missingLangs.map(([name]) => name).includes(l));
      }).filter((lang) => !missingLangs.includes(lang));
      throw new ShikiError2(`Missing languages ${missingLangs.map(([name]) => `\`${name}\``).join(", ")}, required by ${dependents.map(([name]) => `\`${name}\``).join(", ")}`);
    }
    for (const [_, lang] of langsGraphArray) this._resolver.addLanguage(lang);
    for (const [_, lang] of langsGraphArray) this.loadLanguage(lang);
  }
  getLoadedLanguages() {
    if (!this._loadedLanguagesCache) this._loadedLanguagesCache = [.../* @__PURE__ */ new Set([...this._resolvedGrammars.keys(), ...Object.keys(this._alias)])];
    return this._loadedLanguagesCache;
  }
  resolveEmbeddedLanguages(lang) {
    this._langMap.set(lang.name, lang);
    this._langGraph.set(lang.name, lang);
    const embedded = lang.embeddedLanguages ?? lang.embeddedLangs;
    if (embedded) for (const embeddedLang of embedded) this._langGraph.set(embeddedLang, this._langMap.get(embeddedLang));
  }
};
var Resolver = class {
  _langs = /* @__PURE__ */ new Map();
  _scopeToLang = /* @__PURE__ */ new Map();
  _injections = /* @__PURE__ */ new Map();
  _onigLib;
  constructor(engine, langs) {
    this._onigLib = {
      createOnigScanner: (patterns) => engine.createScanner(patterns),
      createOnigString: (s) => engine.createString(s)
    };
    langs.forEach((i) => this.addLanguage(i));
  }
  get onigLib() {
    return this._onigLib;
  }
  getLangRegistration(langIdOrAlias) {
    return this._langs.get(langIdOrAlias);
  }
  loadGrammar(scopeName) {
    return this._scopeToLang.get(scopeName);
  }
  addLanguage(l) {
    this._langs.set(l.name, l);
    if (l.aliases) l.aliases.forEach((a) => {
      this._langs.set(a, l);
    });
    this._scopeToLang.set(l.scopeName, l);
    if (l.injectTo) l.injectTo.forEach((i) => {
      if (!this._injections.get(i)) this._injections.set(i, []);
      this._injections.get(i).push(l.scopeName);
    });
  }
  getInjections(scopeName) {
    const scopeParts = scopeName.split(".");
    let injections = [];
    for (let i = 1; i <= scopeParts.length; i++) {
      const subScopeName = scopeParts.slice(0, i).join(".");
      injections = [...injections, ...this._injections.get(subScopeName) || []];
    }
    return injections;
  }
};
var instancesCount = 0;
function createShikiPrimitive(options) {
  instancesCount += 1;
  if (options.warnings !== false && instancesCount >= 10 && instancesCount % 10 === 0) console.warn(`[Shiki] ${instancesCount} instances have been created. Shiki is supposed to be used as a singleton, consider refactoring your code to cache your highlighter instance; Or call \`highlighter.dispose()\` to release unused instances.`);
  let isDisposed = false;
  if (!options.engine) throw new ShikiError2("`engine` option is required for synchronous mode");
  const langs = (options.langs || []).flat(1);
  const themes = (options.themes || []).flat(1).map(normalizeTheme);
  const _registry = new Registry2(new Resolver(options.engine, langs), themes, langs, options.langAlias);
  let _lastTheme;
  function resolveLangAlias$1(name) {
    return resolveLangAlias(name, options.langAlias);
  }
  function getLanguage(name) {
    ensureNotDisposed();
    const _lang = _registry.getGrammar(typeof name === "string" ? name : name.name);
    if (!_lang) throw new ShikiError2(`Language \`${name}\` not found, you may need to load it first`);
    return _lang;
  }
  function getTheme(name) {
    if (name === "none") return {
      bg: "",
      fg: "",
      name: "none",
      settings: [],
      type: "dark"
    };
    ensureNotDisposed();
    const _theme = _registry.getTheme(name);
    if (!_theme) throw new ShikiError2(`Theme \`${name}\` not found, you may need to load it first`);
    return _theme;
  }
  function setTheme(name) {
    ensureNotDisposed();
    const theme = getTheme(name);
    if (_lastTheme !== name) {
      _registry.setTheme(theme);
      _lastTheme = name;
    }
    return {
      theme,
      colorMap: _registry.getColorMap()
    };
  }
  function getLoadedThemes() {
    ensureNotDisposed();
    return _registry.getLoadedThemes();
  }
  function getLoadedLanguages() {
    ensureNotDisposed();
    return _registry.getLoadedLanguages();
  }
  function loadLanguageSync(...langs2) {
    ensureNotDisposed();
    _registry.loadLanguages(langs2.flat(1));
  }
  async function loadLanguage(...langs2) {
    return loadLanguageSync(await resolveLangs(langs2));
  }
  function loadThemeSync(...themes2) {
    ensureNotDisposed();
    for (const theme of themes2.flat(1)) _registry.loadTheme(theme);
  }
  async function loadTheme(...themes2) {
    ensureNotDisposed();
    return loadThemeSync(await resolveThemes(themes2));
  }
  function ensureNotDisposed() {
    if (isDisposed) throw new ShikiError2("Shiki instance has been disposed");
  }
  function dispose() {
    if (isDisposed) return;
    isDisposed = true;
    _registry.dispose();
    instancesCount -= 1;
  }
  return {
    setTheme,
    getTheme,
    getLanguage,
    getLoadedThemes,
    getLoadedLanguages,
    resolveLangAlias: resolveLangAlias$1,
    loadLanguage,
    loadLanguageSync,
    loadTheme,
    loadThemeSync,
    dispose,
    [Symbol.dispose]: dispose
  };
}
var createShikiInternalSync = createShikiPrimitive;
async function createShikiPrimitiveAsync(options) {
  if (!options.engine) console.warn("`engine` option is required. Use `createOnigurumaEngine` or `createJavaScriptRegexEngine` to create an engine.");
  const [themes, langs, engine] = await Promise.all([
    resolveThemes(options.themes || []),
    resolveLangs(options.langs || []),
    options.engine
  ]);
  return createShikiPrimitive({
    ...options,
    themes,
    langs,
    engine
  });
}
var createShikiInternal = createShikiPrimitiveAsync;
var _grammarStateMap = /* @__PURE__ */ new WeakMap();
function setLastGrammarStateToMap(keys, state) {
  _grammarStateMap.set(keys, state);
}
function getLastGrammarStateFromMap(keys) {
  return _grammarStateMap.get(keys);
}
var GrammarState = class GrammarState2 {
  /**
  * Theme to Stack mapping
  */
  _stacks = {};
  lang;
  get themes() {
    return Object.keys(this._stacks);
  }
  get theme() {
    return this.themes[0];
  }
  get _stack() {
    return this._stacks[this.theme];
  }
  /**
  * Static method to create a initial grammar state.
  */
  static initial(lang, themes) {
    return new GrammarState2(Object.fromEntries(toArray(themes).map((theme) => [theme, INITIAL])), lang);
  }
  constructor(...args) {
    if (args.length === 2) {
      const [stacksMap, lang] = args;
      this.lang = lang;
      this._stacks = stacksMap;
    } else {
      const [stack, lang, theme] = args;
      this.lang = lang;
      this._stacks = { [theme]: stack };
    }
  }
  /**
  * Get the internal stack object.
  * @internal
  */
  getInternalStack(theme = this.theme) {
    return this._stacks[theme];
  }
  getScopes(theme = this.theme) {
    return getScopes(this._stacks[theme]);
  }
  toJSON() {
    return {
      lang: this.lang,
      theme: this.theme,
      themes: this.themes,
      scopes: this.getScopes()
    };
  }
};
function getScopes(stack) {
  const scopes = [];
  const visited = /* @__PURE__ */ new Set();
  function pushScope(stack2) {
    if (visited.has(stack2)) return;
    visited.add(stack2);
    const name = stack2?.nameScopesList?.scopeName;
    if (name) scopes.push(name);
    if (stack2.parent) pushScope(stack2.parent);
  }
  pushScope(stack);
  return scopes;
}
function getGrammarStack(state, theme) {
  if (!(state instanceof GrammarState)) throw new ShikiError2("Invalid grammar state");
  return state.getInternalStack(theme);
}
var RE_COMMA = /,/;
var RE_SPACE = / /;
function codeToTokensBase(primitive, code, options = {}) {
  const { theme: themeName = primitive.getLoadedThemes()[0] } = options;
  if (isPlainLang(primitive.resolveLangAlias(options.lang || "text")) || isNoneTheme(themeName)) return splitLines(code).map((line) => [{
    content: line[0],
    offset: line[1]
  }]);
  const { theme, colorMap } = primitive.setTheme(themeName);
  const _grammar = primitive.getLanguage(options.lang || "text");
  if (options.grammarState) {
    if (options.grammarState.lang !== _grammar.name) throw new ShikiError2(`Grammar state language "${options.grammarState.lang}" does not match highlight language "${_grammar.name}"`);
    if (!options.grammarState.themes.includes(theme.name)) throw new ShikiError2(`Grammar state themes "${options.grammarState.themes}" do not contain highlight theme "${theme.name}"`);
  }
  return tokenizeWithTheme(code, _grammar, theme, colorMap, options);
}
function getLastGrammarState(...args) {
  if (args.length === 2) return getLastGrammarStateFromMap(args[1]);
  const [primitive, code, options = {}] = args;
  const { lang = "text", theme: themeName = primitive.getLoadedThemes()[0] } = options;
  if (isPlainLang(lang) || isNoneTheme(themeName)) throw new ShikiError2("Plain language does not have grammar state");
  if (lang === "ansi") throw new ShikiError2("ANSI language does not have grammar state");
  const { theme, colorMap } = primitive.setTheme(themeName);
  const _grammar = primitive.getLanguage(lang);
  return new GrammarState(_tokenizeWithTheme(code, _grammar, theme, colorMap, options).stateStack, _grammar.name, theme.name);
}
function tokenizeWithTheme(code, grammar, theme, colorMap, options) {
  const result = _tokenizeWithTheme(code, grammar, theme, colorMap, options);
  const grammarState = new GrammarState(result.stateStack, grammar.name, theme.name);
  setLastGrammarStateToMap(result.tokens, grammarState);
  return result.tokens;
}
function _tokenizeWithTheme(code, grammar, theme, colorMap, options) {
  const colorReplacements = resolveColorReplacements(theme, options);
  const { tokenizeMaxLineLength = 0, tokenizeTimeLimit = 500 } = options;
  const lines = splitLines(code);
  let stateStack = options.grammarState ? getGrammarStack(options.grammarState, theme.name) ?? INITIAL : options.grammarContextCode != null ? _tokenizeWithTheme(options.grammarContextCode, grammar, theme, colorMap, {
    ...options,
    grammarState: void 0,
    grammarContextCode: void 0
  }).stateStack : INITIAL;
  let actual = [];
  const final = [];
  for (let i = 0, len = lines.length; i < len; i++) {
    const [line, lineOffset] = lines[i];
    if (line === "") {
      actual = [];
      final.push([]);
      continue;
    }
    if (tokenizeMaxLineLength > 0 && line.length >= tokenizeMaxLineLength) {
      actual = [];
      final.push([{
        content: line,
        offset: lineOffset,
        color: "",
        fontStyle: 0
      }]);
      continue;
    }
    let resultWithScopes;
    let tokensWithScopes;
    let tokensWithScopesIndex;
    if (options.includeExplanation) {
      resultWithScopes = grammar.tokenizeLine(line, stateStack, tokenizeTimeLimit);
      tokensWithScopes = resultWithScopes.tokens;
      tokensWithScopesIndex = 0;
    }
    const result = grammar.tokenizeLine2(line, stateStack, tokenizeTimeLimit);
    const tokensLength = result.tokens.length / 2;
    for (let j = 0; j < tokensLength; j++) {
      const startIndex = result.tokens[2 * j];
      const nextStartIndex = j + 1 < tokensLength ? result.tokens[2 * j + 2] : line.length;
      if (startIndex === nextStartIndex) continue;
      const metadata = result.tokens[2 * j + 1];
      const color = applyColorReplacements(colorMap[EncodedTokenMetadata.getForeground(metadata)], colorReplacements);
      const fontStyle = EncodedTokenMetadata.getFontStyle(metadata);
      const token = {
        content: line.substring(startIndex, nextStartIndex),
        offset: lineOffset + startIndex,
        color,
        fontStyle
      };
      if (options.includeExplanation) {
        const themeSettingsSelectors = [];
        if (options.includeExplanation !== "scopeName") for (const setting of theme.settings) {
          let selectors;
          switch (typeof setting.scope) {
            case "string":
              selectors = setting.scope.split(RE_COMMA).map((scope) => scope.trim());
              break;
            case "object":
              selectors = setting.scope;
              break;
            default:
              continue;
          }
          themeSettingsSelectors.push({
            settings: setting,
            selectors: selectors.map((selector) => selector.split(RE_SPACE))
          });
        }
        token.explanation = [];
        let offset = 0;
        while (startIndex + offset < nextStartIndex) {
          const tokenWithScopes = tokensWithScopes[tokensWithScopesIndex];
          const tokenWithScopesText = line.substring(tokenWithScopes.startIndex, tokenWithScopes.endIndex);
          offset += tokenWithScopesText.length;
          token.explanation.push({
            content: tokenWithScopesText,
            scopes: options.includeExplanation === "scopeName" ? explainThemeScopesNameOnly(tokenWithScopes.scopes) : explainThemeScopesFull(themeSettingsSelectors, tokenWithScopes.scopes)
          });
          tokensWithScopesIndex += 1;
        }
      }
      actual.push(token);
    }
    final.push(actual);
    actual = [];
    stateStack = result.ruleStack;
  }
  return {
    tokens: final,
    stateStack
  };
}
function explainThemeScopesNameOnly(scopes) {
  return scopes.map((scope) => ({ scopeName: scope }));
}
function explainThemeScopesFull(themeSelectors, scopes) {
  const result = [];
  for (let i = 0, len = scopes.length; i < len; i++) {
    const scope = scopes[i];
    result[i] = {
      scopeName: scope,
      themeMatches: explainThemeScope(themeSelectors, scope, scopes.slice(0, i))
    };
  }
  return result;
}
function matchesOne(selector, scope) {
  return selector === scope || scope.substring(0, selector.length) === selector && scope[selector.length] === ".";
}
function matches(selectors, scope, parentScopes) {
  if (!matchesOne(selectors.at(-1), scope)) return false;
  let selectorParentIndex = selectors.length - 2;
  let parentIndex = parentScopes.length - 1;
  while (selectorParentIndex >= 0 && parentIndex >= 0) {
    if (matchesOne(selectors[selectorParentIndex], parentScopes[parentIndex])) selectorParentIndex -= 1;
    parentIndex -= 1;
  }
  if (selectorParentIndex === -1) return true;
  return false;
}
function explainThemeScope(themeSettingsSelectors, scope, parentScopes) {
  const result = [];
  for (const { selectors, settings } of themeSettingsSelectors) for (const selectorPieces of selectors) if (matches(selectorPieces, scope, parentScopes)) {
    result.push(settings);
    break;
  }
  return result;
}
function codeToTokensWithThemes(primitive, code, options, codeToTokensBaseFn = codeToTokensBase) {
  const themes = Object.entries(options.themes).filter((i) => i[1]).map((i) => ({
    color: i[0],
    theme: i[1]
  }));
  const themedTokens = themes.map((t) => {
    const tokens2 = codeToTokensBaseFn(primitive, code, {
      ...options,
      theme: t.theme
    });
    return {
      tokens: tokens2,
      state: getLastGrammarStateFromMap(tokens2),
      theme: typeof t.theme === "string" ? t.theme : t.theme.name
    };
  });
  const tokens = alignThemesTokenization(...themedTokens.map((i) => i.tokens));
  const mergedTokens = tokens[0].map((line, lineIdx) => line.map((_token, tokenIdx) => {
    const mergedToken = {
      content: _token.content,
      variants: {},
      offset: _token.offset
    };
    if ("includeExplanation" in options && options.includeExplanation) mergedToken.explanation = _token.explanation;
    tokens.forEach((t, themeIdx) => {
      const { content: _, explanation: __, offset: ___, ...styles } = t[lineIdx][tokenIdx];
      mergedToken.variants[themes[themeIdx].color] = styles;
    });
    return mergedToken;
  }));
  const mergedGrammarState = themedTokens[0].state ? new GrammarState(Object.fromEntries(themedTokens.map((s) => [s.theme, s.state?.getInternalStack(s.theme)])), themedTokens[0].state.lang) : void 0;
  if (mergedGrammarState) setLastGrammarStateToMap(mergedTokens, mergedGrammarState);
  return mergedTokens;
}
function alignThemesTokenization(...themes) {
  const outThemes = themes.map(() => []);
  const count = themes.length;
  for (let i = 0; i < themes[0].length; i++) {
    const lines = themes.map((t) => t[i]);
    const outLines = outThemes.map(() => []);
    outThemes.forEach((t, i2) => t.push(outLines[i2]));
    const indexes = lines.map(() => 0);
    const current = lines.map((l) => l[0]);
    while (current.every((t) => t)) {
      const minLength = Math.min(...current.map((t) => t.content.length));
      for (let n = 0; n < count; n++) {
        const token = current[n];
        if (token.content.length === minLength) {
          outLines[n].push(token);
          indexes[n] += 1;
          current[n] = lines[n][indexes[n]];
        } else {
          outLines[n].push({
            ...token,
            content: token.content.slice(0, minLength)
          });
          current[n] = {
            ...token,
            content: token.content.slice(minLength),
            offset: token.offset + minLength
          };
        }
      }
    }
  }
  return outThemes;
}

// node_modules/@shikijs/core/dist/index.mjs
var RE_WHITESPACE = /\s+/g;
function addClassToHast(node, className) {
  if (!className) return node;
  node.properties ||= {};
  node.properties.class ||= [];
  if (typeof node.properties.class === "string") node.properties.class = node.properties.class.split(RE_WHITESPACE);
  if (!Array.isArray(node.properties.class)) node.properties.class = [];
  const targets = Array.isArray(className) ? className : className.split(RE_WHITESPACE);
  for (const c of targets) if (c && !node.properties.class.includes(c)) node.properties.class.push(c);
  return node;
}
var RE_LANG_ATTR = /:?lang=["']([^"']+)["']/g;
var RE_CODE_FENCE = /(?:```|~~~)([\w-]+)/g;
var RE_LATEX_BEGIN = /\\begin\{([\w-]+)\}/g;
var RE_SCRIPT_LANG = /<script\s+(?:type|lang)=["']([^"']+)["']/gi;
function createPositionConverter(code) {
  const lines = splitLines(code, true).map(([line]) => line);
  function indexToPos(index) {
    if (index === code.length) return {
      line: lines.length - 1,
      character: lines.at(-1).length
    };
    let character = index;
    let line = 0;
    for (const lineText of lines) {
      if (character < lineText.length) break;
      character -= lineText.length;
      line++;
    }
    return {
      line,
      character
    };
  }
  function posToIndex(line, character) {
    let index = 0;
    for (let i = 0; i < line; i++) index += lines[i].length;
    index += character;
    return index;
  }
  return {
    lines,
    indexToPos,
    posToIndex
  };
}
function guessEmbeddedLanguages(code, _lang, highlighter) {
  const langs = /* @__PURE__ */ new Set();
  for (const match of code.matchAll(RE_LANG_ATTR)) {
    const lang = match[1].toLowerCase().trim();
    if (lang) langs.add(lang);
  }
  for (const match of code.matchAll(RE_CODE_FENCE)) {
    const lang = match[1].toLowerCase().trim();
    if (lang) langs.add(lang);
  }
  for (const match of code.matchAll(RE_LATEX_BEGIN)) {
    const lang = match[1].toLowerCase().trim();
    if (lang) langs.add(lang);
  }
  for (const match of code.matchAll(RE_SCRIPT_LANG)) {
    const fullType = match[1].toLowerCase().trim();
    const lang = fullType.includes("/") ? fullType.split("/").pop() : fullType;
    if (lang) langs.add(lang);
  }
  if (!highlighter) return [...langs];
  const bundle = highlighter.getBundledLanguages();
  return [...langs].filter((l) => l && bundle[l]);
}
var COLOR_KEYS = ["color", "background-color"];
function splitToken(token, offsets) {
  let lastOffset = 0;
  const tokens = [];
  for (const offset of offsets) {
    if (offset > lastOffset) tokens.push({
      ...token,
      content: token.content.slice(lastOffset, offset),
      offset: token.offset + lastOffset
    });
    lastOffset = offset;
  }
  if (lastOffset < token.content.length) tokens.push({
    ...token,
    content: token.content.slice(lastOffset),
    offset: token.offset + lastOffset
  });
  return tokens;
}
function splitTokens(tokens, breakpoints) {
  const sorted = [...breakpoints instanceof Set ? breakpoints : new Set(breakpoints)].sort((a, b) => a - b);
  if (!sorted.length) return tokens;
  return tokens.map((line) => {
    return line.flatMap((token) => {
      const breakpointsInToken = sorted.filter((i) => token.offset < i && i < token.offset + token.content.length).map((i) => i - token.offset).sort((a, b) => a - b);
      if (!breakpointsInToken.length) return token;
      return splitToken(token, breakpointsInToken);
    });
  });
}
function flatTokenVariants(merged, variantsOrder, cssVariablePrefix, defaultColor, colorsRendering = "css-vars") {
  const token = {
    content: merged.content,
    explanation: merged.explanation,
    offset: merged.offset
  };
  const styles = variantsOrder.map((t) => getTokenStyleObject(merged.variants[t]));
  const styleKeys = new Set(styles.flatMap((t) => Object.keys(t)));
  const mergedStyles = {};
  const varKey = (idx, key) => {
    const keyName = key === "color" ? "" : key === "background-color" ? "-bg" : `-${key}`;
    return cssVariablePrefix + variantsOrder[idx] + (key === "color" ? "" : keyName);
  };
  styles.forEach((cur, idx) => {
    for (const key of styleKeys) {
      const value = cur[key] || "inherit";
      if (idx === 0 && defaultColor && COLOR_KEYS.includes(key)) if (defaultColor === "light-dark()" && styles.length > 1) {
        const lightIndex = variantsOrder.findIndex((t) => t === "light");
        const darkIndex = variantsOrder.findIndex((t) => t === "dark");
        if (lightIndex === -1 || darkIndex === -1) throw new ShikiError2('When using `defaultColor: "light-dark()"`, you must provide both `light` and `dark` themes');
        mergedStyles[key] = `light-dark(${styles[lightIndex][key] || "inherit"}, ${styles[darkIndex][key] || "inherit"})`;
        if (colorsRendering === "css-vars") mergedStyles[varKey(idx, key)] = value;
      } else mergedStyles[key] = value;
      else if (colorsRendering === "css-vars") mergedStyles[varKey(idx, key)] = value;
    }
  });
  token.htmlStyle = mergedStyles;
  return token;
}
function getTokenStyleObject(token) {
  const styles = {};
  if (token.color) styles.color = token.color;
  if (token.bgColor) styles["background-color"] = token.bgColor;
  if (token.fontStyle) {
    if (token.fontStyle & FontStyle.Italic) styles["font-style"] = "italic";
    if (token.fontStyle & FontStyle.Bold) styles["font-weight"] = "bold";
    const decorations2 = [];
    if (token.fontStyle & FontStyle.Underline) decorations2.push("underline");
    if (token.fontStyle & FontStyle.Strikethrough) decorations2.push("line-through");
    if (decorations2.length) styles["text-decoration"] = decorations2.join(" ");
  }
  return styles;
}
function stringifyTokenStyle(token) {
  if (typeof token === "string") return token;
  return Object.entries(token).map(([key, value]) => `${key}:${value}`).join(";");
}
function transformerDecorations() {
  const map = /* @__PURE__ */ new WeakMap();
  function getContext(shiki) {
    if (!map.has(shiki.meta)) {
      let normalizePosition = function(p) {
        if (typeof p === "number") {
          if (p < 0 || p > shiki.source.length) throw new ShikiError2(`Invalid decoration offset: ${p}. Code length: ${shiki.source.length}`);
          return {
            ...converter.indexToPos(p),
            offset: p
          };
        } else {
          const line = converter.lines[p.line];
          if (line === void 0) throw new ShikiError2(`Invalid decoration position ${JSON.stringify(p)}. Lines length: ${converter.lines.length}`);
          let character = p.character;
          if (character < 0) character = line.length + character;
          if (character < 0 || character > line.length) throw new ShikiError2(`Invalid decoration position ${JSON.stringify(p)}. Line ${p.line} length: ${line.length}`);
          return {
            ...p,
            character,
            offset: converter.posToIndex(p.line, character)
          };
        }
      };
      const converter = createPositionConverter(shiki.source);
      const decorations2 = (shiki.options.decorations || []).map((d) => ({
        ...d,
        start: normalizePosition(d.start),
        end: normalizePosition(d.end)
      }));
      verifyIntersections(decorations2);
      map.set(shiki.meta, {
        decorations: decorations2,
        converter,
        source: shiki.source
      });
    }
    return map.get(shiki.meta);
  }
  return {
    name: "shiki:decorations",
    tokens(tokens) {
      if (!this.options.decorations?.length) return;
      return splitTokens(tokens, getContext(this).decorations.flatMap((d) => [d.start.offset, d.end.offset]));
    },
    code(codeEl) {
      if (!this.options.decorations?.length) return;
      const ctx = getContext(this);
      const lines = [...codeEl.children].filter((i) => i.type === "element" && i.tagName === "span");
      if (lines.length !== ctx.converter.lines.length) throw new ShikiError2(`Number of lines in code element (${lines.length}) does not match the number of lines in the source (${ctx.converter.lines.length}). Failed to apply decorations.`);
      function applyLineSection(line, start, end, decoration) {
        const lineEl = lines[line];
        let text = "";
        let startIndex = -1;
        let endIndex = -1;
        if (start === 0) startIndex = 0;
        if (end === 0) endIndex = 0;
        if (end === Number.POSITIVE_INFINITY) endIndex = lineEl.children.length;
        if (startIndex === -1 || endIndex === -1) for (let i = 0; i < lineEl.children.length; i++) {
          text += stringify(lineEl.children[i]);
          if (startIndex === -1 && text.length === start) startIndex = i + 1;
          if (endIndex === -1 && text.length === end) endIndex = i + 1;
        }
        if (startIndex === -1) throw new ShikiError2(`Failed to find start index for decoration ${JSON.stringify(decoration.start)}`);
        if (endIndex === -1) throw new ShikiError2(`Failed to find end index for decoration ${JSON.stringify(decoration.end)}`);
        const children = lineEl.children.slice(startIndex, endIndex);
        if (!decoration.alwaysWrap && children.length === lineEl.children.length) applyDecoration(lineEl, decoration, "line");
        else if (!decoration.alwaysWrap && children.length === 1 && children[0].type === "element") applyDecoration(children[0], decoration, "token");
        else {
          const wrapper = {
            type: "element",
            tagName: "span",
            properties: {},
            children
          };
          applyDecoration(wrapper, decoration, "wrapper");
          lineEl.children.splice(startIndex, children.length, wrapper);
        }
      }
      function applyLine(line, decoration) {
        lines[line] = applyDecoration(lines[line], decoration, "line");
      }
      function applyDecoration(el, decoration, type) {
        const properties = decoration.properties || {};
        const transform = decoration.transform || ((i) => i);
        el.tagName = decoration.tagName || "span";
        el.properties = {
          ...el.properties,
          ...properties,
          class: el.properties.class
        };
        if (decoration.properties?.class) addClassToHast(el, decoration.properties.class);
        el = transform(el, type) || el;
        return el;
      }
      const lineApplies = [];
      const sorted = ctx.decorations.sort((a, b) => b.start.offset - a.start.offset || a.end.offset - b.end.offset);
      for (const decoration of sorted) {
        const { start, end } = decoration;
        if (start.line === end.line) applyLineSection(start.line, start.character, end.character, decoration);
        else if (start.line < end.line) {
          applyLineSection(start.line, start.character, Number.POSITIVE_INFINITY, decoration);
          for (let i = start.line + 1; i < end.line; i++) lineApplies.unshift(() => applyLine(i, decoration));
          applyLineSection(end.line, 0, end.character, decoration);
        }
      }
      lineApplies.forEach((i) => i());
    }
  };
}
function verifyIntersections(items) {
  for (let i = 0; i < items.length; i++) {
    const foo = items[i];
    if (foo.start.offset > foo.end.offset) throw new ShikiError2(`Invalid decoration range: ${JSON.stringify(foo.start)} - ${JSON.stringify(foo.end)}`);
    for (let j = i + 1; j < items.length; j++) {
      const bar = items[j];
      const isFooHasBarStart = foo.start.offset <= bar.start.offset && bar.start.offset < foo.end.offset;
      const isFooHasBarEnd = foo.start.offset < bar.end.offset && bar.end.offset <= foo.end.offset;
      const isBarHasFooStart = bar.start.offset <= foo.start.offset && foo.start.offset < bar.end.offset;
      const isBarHasFooEnd = bar.start.offset < foo.end.offset && foo.end.offset <= bar.end.offset;
      if (isFooHasBarStart || isFooHasBarEnd || isBarHasFooStart || isBarHasFooEnd) {
        if (isFooHasBarStart && isFooHasBarEnd) continue;
        if (isBarHasFooStart && isBarHasFooEnd) continue;
        if (isBarHasFooStart && foo.start.offset === foo.end.offset) continue;
        if (isFooHasBarEnd && bar.start.offset === bar.end.offset) continue;
        throw new ShikiError2(`Decorations ${JSON.stringify(foo.start)} and ${JSON.stringify(bar.start)} intersect.`);
      }
    }
  }
}
function stringify(el) {
  if (el.type === "text") return el.value;
  if (el.type === "element") return el.children.map(stringify).join("");
  return "";
}
var builtInTransformers = [transformerDecorations()];
function getTransformers(options) {
  const transformers = sortTransformersByEnforcement(options.transformers || []);
  return [
    ...transformers.pre,
    ...transformers.normal,
    ...transformers.post,
    ...builtInTransformers
  ];
}
function sortTransformersByEnforcement(transformers) {
  const pre = [];
  const post = [];
  const normal = [];
  for (const transformer of transformers) switch (transformer.enforce) {
    case "pre":
      pre.push(transformer);
      break;
    case "post":
      post.push(transformer);
      break;
    default:
      normal.push(transformer);
  }
  return {
    pre,
    post,
    normal
  };
}
var namedColors = [
  "black",
  "red",
  "green",
  "yellow",
  "blue",
  "magenta",
  "cyan",
  "white",
  "brightBlack",
  "brightRed",
  "brightGreen",
  "brightYellow",
  "brightBlue",
  "brightMagenta",
  "brightCyan",
  "brightWhite"
];
var decorations = {
  1: "bold",
  2: "dim",
  3: "italic",
  4: "underline",
  7: "reverse",
  8: "hidden",
  9: "strikethrough"
};
function findSequence(value, position) {
  const nextEscape = value.indexOf("\x1B", position);
  if (nextEscape !== -1) {
    if (value[nextEscape + 1] === "[") {
      const nextClose = value.indexOf("m", nextEscape);
      if (nextClose !== -1) return {
        sequence: value.substring(nextEscape + 2, nextClose).split(";"),
        startPosition: nextEscape,
        position: nextClose + 1
      };
    }
  }
  return { position: value.length };
}
function parseColor(sequence) {
  const colorMode = sequence.shift();
  if (colorMode === "2") {
    const rgb = sequence.splice(0, 3).map((x) => Number.parseInt(x));
    if (rgb.length !== 3 || rgb.some((x) => Number.isNaN(x))) return;
    return {
      type: "rgb",
      rgb
    };
  } else if (colorMode === "5") {
    const index = sequence.shift();
    if (index) return {
      type: "table",
      index: Number(index)
    };
  }
}
function parseSequence(sequence) {
  const commands = [];
  while (sequence.length > 0) {
    const code = sequence.shift();
    if (!code) continue;
    const codeInt = Number.parseInt(code);
    if (Number.isNaN(codeInt)) continue;
    if (codeInt === 0) commands.push({ type: "resetAll" });
    else if (codeInt <= 9) {
      if (decorations[codeInt]) commands.push({
        type: "setDecoration",
        value: decorations[codeInt]
      });
    } else if (codeInt <= 29) {
      const decoration = decorations[codeInt - 20];
      if (decoration) {
        commands.push({
          type: "resetDecoration",
          value: decoration
        });
        if (decoration === "dim") commands.push({
          type: "resetDecoration",
          value: "bold"
        });
      }
    } else if (codeInt <= 37) commands.push({
      type: "setForegroundColor",
      value: {
        type: "named",
        name: namedColors[codeInt - 30]
      }
    });
    else if (codeInt === 38) {
      const color = parseColor(sequence);
      if (color) commands.push({
        type: "setForegroundColor",
        value: color
      });
    } else if (codeInt === 39) commands.push({ type: "resetForegroundColor" });
    else if (codeInt <= 47) commands.push({
      type: "setBackgroundColor",
      value: {
        type: "named",
        name: namedColors[codeInt - 40]
      }
    });
    else if (codeInt === 48) {
      const color = parseColor(sequence);
      if (color) commands.push({
        type: "setBackgroundColor",
        value: color
      });
    } else if (codeInt === 49) commands.push({ type: "resetBackgroundColor" });
    else if (codeInt === 53) commands.push({
      type: "setDecoration",
      value: "overline"
    });
    else if (codeInt === 55) commands.push({
      type: "resetDecoration",
      value: "overline"
    });
    else if (codeInt >= 90 && codeInt <= 97) commands.push({
      type: "setForegroundColor",
      value: {
        type: "named",
        name: namedColors[codeInt - 90 + 8]
      }
    });
    else if (codeInt >= 100 && codeInt <= 107) commands.push({
      type: "setBackgroundColor",
      value: {
        type: "named",
        name: namedColors[codeInt - 100 + 8]
      }
    });
  }
  return commands;
}
function createAnsiSequenceParser() {
  let foreground = null;
  let background = null;
  let decorations2 = /* @__PURE__ */ new Set();
  return { parse(value) {
    const tokens = [];
    let position = 0;
    do {
      const findResult = findSequence(value, position);
      const text = findResult.sequence ? value.substring(position, findResult.startPosition) : value.substring(position);
      if (text.length > 0) tokens.push({
        value: text,
        foreground,
        background,
        decorations: new Set(decorations2)
      });
      if (findResult.sequence) {
        const commands = parseSequence(findResult.sequence);
        for (const styleToken of commands) if (styleToken.type === "resetAll") {
          foreground = null;
          background = null;
          decorations2.clear();
        } else if (styleToken.type === "resetForegroundColor") foreground = null;
        else if (styleToken.type === "resetBackgroundColor") background = null;
        else if (styleToken.type === "resetDecoration") decorations2.delete(styleToken.value);
        for (const styleToken of commands) if (styleToken.type === "setForegroundColor") foreground = styleToken.value;
        else if (styleToken.type === "setBackgroundColor") background = styleToken.value;
        else if (styleToken.type === "setDecoration") decorations2.add(styleToken.value);
      }
      position = findResult.position;
    } while (position < value.length);
    return tokens;
  } };
}
var defaultNamedColorsMap = {
  black: "#000000",
  red: "#bb0000",
  green: "#00bb00",
  yellow: "#bbbb00",
  blue: "#0000bb",
  magenta: "#ff00ff",
  cyan: "#00bbbb",
  white: "#eeeeee",
  brightBlack: "#555555",
  brightRed: "#ff5555",
  brightGreen: "#00ff00",
  brightYellow: "#ffff55",
  brightBlue: "#5555ff",
  brightMagenta: "#ff55ff",
  brightCyan: "#55ffff",
  brightWhite: "#ffffff"
};
function createColorPalette(namedColorsMap = defaultNamedColorsMap) {
  function namedColor(name) {
    return namedColorsMap[name];
  }
  function rgbColor(rgb) {
    return `#${rgb.map((x) => Math.max(0, Math.min(x, 255)).toString(16).padStart(2, "0")).join("")}`;
  }
  let colorTable;
  function getColorTable() {
    if (colorTable) return colorTable;
    colorTable = [];
    for (let i = 0; i < namedColors.length; i++) colorTable.push(namedColor(namedColors[i]));
    let levels = [
      0,
      95,
      135,
      175,
      215,
      255
    ];
    for (let r = 0; r < 6; r++) for (let g = 0; g < 6; g++) for (let b = 0; b < 6; b++) colorTable.push(rgbColor([
      levels[r],
      levels[g],
      levels[b]
    ]));
    let level = 8;
    for (let i = 0; i < 24; i++, level += 10) colorTable.push(rgbColor([
      level,
      level,
      level
    ]));
    return colorTable;
  }
  function tableColor(index) {
    return getColorTable()[index];
  }
  function value(color) {
    switch (color.type) {
      case "named":
        return namedColor(color.name);
      case "rgb":
        return rgbColor(color.rgb);
      case "table":
        return tableColor(color.index);
    }
  }
  return { value };
}
var RE_HEX_COLOR = /#([0-9a-f]{3,8})/i;
var RE_CSS_VAR_ANSI = /var\((--[\w-]+-ansi-[\w-]+)\)/;
var defaultAnsiColors = {
  black: "#000000",
  red: "#cd3131",
  green: "#0DBC79",
  yellow: "#E5E510",
  blue: "#2472C8",
  magenta: "#BC3FBC",
  cyan: "#11A8CD",
  white: "#E5E5E5",
  brightBlack: "#666666",
  brightRed: "#F14C4C",
  brightGreen: "#23D18B",
  brightYellow: "#F5F543",
  brightBlue: "#3B8EEA",
  brightMagenta: "#D670D6",
  brightCyan: "#29B8DB",
  brightWhite: "#FFFFFF"
};
function tokenizeAnsiWithTheme(theme, fileContents, options) {
  const colorReplacements = resolveColorReplacements(theme, options);
  const lines = splitLines(fileContents);
  const colorPalette = createColorPalette(Object.fromEntries(namedColors.map((name) => {
    const key = `terminal.ansi${name[0].toUpperCase()}${name.substring(1)}`;
    return [name, theme.colors?.[key] || defaultAnsiColors[name]];
  })));
  const parser = createAnsiSequenceParser();
  return lines.map((line) => parser.parse(line[0]).map((token) => {
    let color;
    let bgColor;
    if (token.decorations.has("reverse")) {
      color = token.background ? colorPalette.value(token.background) : theme.bg;
      bgColor = token.foreground ? colorPalette.value(token.foreground) : theme.fg;
    } else {
      color = token.foreground ? colorPalette.value(token.foreground) : theme.fg;
      bgColor = token.background ? colorPalette.value(token.background) : void 0;
    }
    color = applyColorReplacements(color, colorReplacements);
    bgColor = applyColorReplacements(bgColor, colorReplacements);
    if (token.decorations.has("dim")) color = dimColor(color);
    let fontStyle = FontStyle.None;
    if (token.decorations.has("bold")) fontStyle |= FontStyle.Bold;
    if (token.decorations.has("italic")) fontStyle |= FontStyle.Italic;
    if (token.decorations.has("underline")) fontStyle |= FontStyle.Underline;
    if (token.decorations.has("strikethrough")) fontStyle |= FontStyle.Strikethrough;
    return {
      content: token.value,
      offset: line[1],
      color,
      bgColor,
      fontStyle
    };
  }));
}
function dimColor(color) {
  const hexMatch = color.match(RE_HEX_COLOR);
  if (hexMatch) {
    const hex = hexMatch[1];
    if (hex.length === 8) {
      const alpha = Math.round(Number.parseInt(hex.slice(6, 8), 16) / 2).toString(16).padStart(2, "0");
      return `#${hex.slice(0, 6)}${alpha}`;
    } else if (hex.length === 6) return `#${hex}80`;
    else if (hex.length === 4) {
      const r = hex[0];
      const g = hex[1];
      const b = hex[2];
      const a = hex[3];
      return `#${r}${r}${g}${g}${b}${b}${Math.round(Number.parseInt(`${a}${a}`, 16) / 2).toString(16).padStart(2, "0")}`;
    } else if (hex.length === 3) {
      const r = hex[0];
      const g = hex[1];
      const b = hex[2];
      return `#${r}${r}${g}${g}${b}${b}80`;
    }
  }
  const cssVarMatch = color.match(RE_CSS_VAR_ANSI);
  if (cssVarMatch) return `var(${cssVarMatch[1]}-dim)`;
  return color;
}
function codeToTokensBase2(primitive, code, options = {}) {
  const lang = primitive.resolveLangAlias(options.lang || "text");
  const { theme: themeName = primitive.getLoadedThemes()[0] } = options;
  if (!isPlainLang(lang) && !isNoneTheme(themeName) && lang === "ansi") {
    const { theme } = primitive.setTheme(themeName);
    return tokenizeAnsiWithTheme(theme, code, options);
  }
  return codeToTokensBase(primitive, code, options);
}
function codeToTokens(primitive, code, options) {
  let bg;
  let fg;
  let tokens;
  let themeName;
  let rootStyle;
  let grammarState;
  if ("themes" in options) {
    const { defaultColor = "light", cssVariablePrefix = "--shiki-", colorsRendering = "css-vars" } = options;
    const themes = Object.entries(options.themes).filter((i) => i[1]).map((i) => ({
      color: i[0],
      theme: i[1]
    })).sort((a, b) => a.color === defaultColor ? -1 : b.color === defaultColor ? 1 : 0);
    if (themes.length === 0) throw new ShikiError2("`themes` option must not be empty");
    const themeTokens = codeToTokensWithThemes(primitive, code, options, codeToTokensBase2);
    grammarState = getLastGrammarStateFromMap(themeTokens);
    if (defaultColor && "light-dark()" !== defaultColor && !themes.some((t) => t.color === defaultColor)) throw new ShikiError2(`\`themes\` option must contain the defaultColor key \`${defaultColor}\``);
    const themeRegs = themes.map((t) => primitive.getTheme(t.theme));
    const themesOrder = themes.map((t) => t.color);
    tokens = themeTokens.map((line) => line.map((token) => flatTokenVariants(token, themesOrder, cssVariablePrefix, defaultColor, colorsRendering)));
    if (grammarState) setLastGrammarStateToMap(tokens, grammarState);
    const themeColorReplacements = themes.map((t) => resolveColorReplacements(t.theme, options));
    fg = mapThemeColors(themes, themeRegs, themeColorReplacements, cssVariablePrefix, defaultColor, "fg", colorsRendering);
    bg = mapThemeColors(themes, themeRegs, themeColorReplacements, cssVariablePrefix, defaultColor, "bg", colorsRendering);
    themeName = `shiki-themes ${themeRegs.map((t) => t.name).join(" ")}`;
    rootStyle = defaultColor ? void 0 : [fg, bg].join(";");
  } else if ("theme" in options) {
    const colorReplacements = resolveColorReplacements(options.theme, options);
    tokens = codeToTokensBase2(primitive, code, options);
    const _theme = primitive.getTheme(options.theme);
    bg = applyColorReplacements(_theme.bg, colorReplacements);
    fg = applyColorReplacements(_theme.fg, colorReplacements);
    themeName = _theme.name;
    grammarState = getLastGrammarStateFromMap(tokens);
  } else throw new ShikiError2("Invalid options, either `theme` or `themes` must be provided");
  return {
    tokens,
    fg,
    bg,
    themeName,
    rootStyle,
    grammarState
  };
}
function mapThemeColors(themes, themeRegs, themeColorReplacements, cssVariablePrefix, defaultColor, property, colorsRendering) {
  return themes.map((t, idx) => {
    const value = applyColorReplacements(themeRegs[idx][property], themeColorReplacements[idx]) || "inherit";
    const cssVar = `${cssVariablePrefix + t.color}${property === "bg" ? "-bg" : ""}:${value}`;
    if (idx === 0 && defaultColor) {
      if (defaultColor === "light-dark()" && themes.length > 1) {
        const lightIndex = themes.findIndex((t2) => t2.color === "light");
        const darkIndex = themes.findIndex((t2) => t2.color === "dark");
        if (lightIndex === -1 || darkIndex === -1) throw new ShikiError2('When using `defaultColor: "light-dark()"`, you must provide both `light` and `dark` themes');
        return `light-dark(${applyColorReplacements(themeRegs[lightIndex][property], themeColorReplacements[lightIndex]) || "inherit"}, ${applyColorReplacements(themeRegs[darkIndex][property], themeColorReplacements[darkIndex]) || "inherit"});${cssVar}`;
      }
      return value;
    }
    if (colorsRendering === "css-vars") return cssVar;
    return null;
  }).filter((i) => !!i).join(";");
}
var RE_WHITESPACE_ONLY = /^\s+$/;
var RE_LEADING_TRAILING_WHITESPACE = /^(\s*)(.*?)(\s*)$/;
function codeToHast(primitive, code, options, transformerContext = {
  meta: {},
  options,
  codeToHast: (_code, _options) => codeToHast(primitive, _code, _options),
  codeToTokens: (_code, _options) => codeToTokens(primitive, _code, _options)
}) {
  let input = code;
  for (const transformer of getTransformers(options)) input = transformer.preprocess?.call(transformerContext, input, options) || input;
  let { tokens, fg, bg, themeName, rootStyle, grammarState } = codeToTokens(primitive, input, options);
  const { mergeWhitespaces = true, mergeSameStyleTokens = false } = options;
  if (mergeWhitespaces === true) tokens = mergeWhitespaceTokens(tokens);
  else if (mergeWhitespaces === "never") tokens = splitWhitespaceTokens(tokens);
  if (mergeSameStyleTokens) tokens = mergeAdjacentStyledTokens(tokens);
  const contextSource = {
    ...transformerContext,
    get source() {
      return input;
    }
  };
  for (const transformer of getTransformers(options)) tokens = transformer.tokens?.call(contextSource, tokens) || tokens;
  return tokensToHast(tokens, {
    ...options,
    fg,
    bg,
    themeName,
    rootStyle: options.rootStyle === false ? false : options.rootStyle ?? rootStyle
  }, contextSource, grammarState);
}
function tokensToHast(tokens, options, transformerContext, grammarState = getLastGrammarStateFromMap(tokens)) {
  const transformers = getTransformers(options);
  const lines = [];
  const root = {
    type: "root",
    children: []
  };
  const { structure = "classic", tabindex = "0" } = options;
  const properties = { class: `shiki ${options.themeName || ""}` };
  if (options.rootStyle !== false) if (options.rootStyle != null) properties.style = options.rootStyle;
  else properties.style = `background-color:${options.bg};color:${options.fg}`;
  if (tabindex !== false && tabindex != null) properties.tabindex = tabindex.toString();
  for (const [key, value] of Object.entries(options.meta || {})) if (!key.startsWith("_")) properties[key] = value;
  let preNode = {
    type: "element",
    tagName: "pre",
    properties,
    children: [],
    data: options.data
  };
  let codeNode = {
    type: "element",
    tagName: "code",
    properties: {},
    children: lines
  };
  const lineNodes = [];
  const context = {
    ...transformerContext,
    structure,
    addClassToHast,
    get source() {
      return transformerContext.source;
    },
    get tokens() {
      return tokens;
    },
    get options() {
      return options;
    },
    get root() {
      return root;
    },
    get pre() {
      return preNode;
    },
    get code() {
      return codeNode;
    },
    get lines() {
      return lineNodes;
    }
  };
  tokens.forEach((line, idx) => {
    if (idx) {
      if (structure === "inline") root.children.push({
        type: "element",
        tagName: "br",
        properties: {},
        children: []
      });
      else if (structure === "classic") lines.push({
        type: "text",
        value: "\n"
      });
    }
    let lineNode = {
      type: "element",
      tagName: "span",
      properties: { class: "line" },
      children: []
    };
    let col = 0;
    for (const token of line) {
      let tokenNode = {
        type: "element",
        tagName: "span",
        properties: { ...token.htmlAttrs },
        children: [{
          type: "text",
          value: token.content
        }]
      };
      const style = stringifyTokenStyle(token.htmlStyle || getTokenStyleObject(token));
      if (style) tokenNode.properties.style = style;
      for (const transformer of transformers) tokenNode = transformer?.span?.call(context, tokenNode, idx + 1, col, lineNode, token) || tokenNode;
      if (structure === "inline") root.children.push(tokenNode);
      else if (structure === "classic") lineNode.children.push(tokenNode);
      col += token.content.length;
    }
    if (structure === "classic") {
      for (const transformer of transformers) lineNode = transformer?.line?.call(context, lineNode, idx + 1) || lineNode;
      lineNodes.push(lineNode);
      lines.push(lineNode);
    } else if (structure === "inline") lineNodes.push(lineNode);
  });
  if (structure === "classic") {
    for (const transformer of transformers) codeNode = transformer?.code?.call(context, codeNode) || codeNode;
    preNode.children.push(codeNode);
    for (const transformer of transformers) preNode = transformer?.pre?.call(context, preNode) || preNode;
    root.children.push(preNode);
  } else if (structure === "inline") {
    const syntheticLines = [];
    let currentLine = {
      type: "element",
      tagName: "span",
      properties: { class: "line" },
      children: []
    };
    for (const child of root.children) if (child.type === "element" && child.tagName === "br") {
      syntheticLines.push(currentLine);
      currentLine = {
        type: "element",
        tagName: "span",
        properties: { class: "line" },
        children: []
      };
    } else if (child.type === "element" || child.type === "text") currentLine.children.push(child);
    syntheticLines.push(currentLine);
    let transformedCode = {
      type: "element",
      tagName: "code",
      properties: {},
      children: syntheticLines
    };
    for (const transformer of transformers) transformedCode = transformer?.code?.call(context, transformedCode) || transformedCode;
    root.children = [];
    for (let i = 0; i < transformedCode.children.length; i++) {
      if (i > 0) root.children.push({
        type: "element",
        tagName: "br",
        properties: {},
        children: []
      });
      const line = transformedCode.children[i];
      if (line.type === "element") root.children.push(...line.children);
    }
  }
  let result = root;
  for (const transformer of transformers) result = transformer?.root?.call(context, result) || result;
  if (grammarState) setLastGrammarStateToMap(result, grammarState);
  return result;
}
function mergeWhitespaceTokens(tokens) {
  return tokens.map((line) => {
    const newLine = [];
    let carryOnContent = "";
    let firstOffset;
    line.forEach((token, idx) => {
      const couldMerge = !(token.fontStyle && (token.fontStyle & FontStyle.Underline || token.fontStyle & FontStyle.Strikethrough));
      if (couldMerge && RE_WHITESPACE_ONLY.test(token.content) && line[idx + 1]) {
        if (firstOffset === void 0) firstOffset = token.offset;
        carryOnContent += token.content;
      } else if (carryOnContent) {
        if (couldMerge) newLine.push({
          ...token,
          offset: firstOffset,
          content: carryOnContent + token.content
        });
        else newLine.push({
          content: carryOnContent,
          offset: firstOffset
        }, token);
        firstOffset = void 0;
        carryOnContent = "";
      } else newLine.push(token);
    });
    return newLine;
  });
}
function splitWhitespaceTokens(tokens) {
  return tokens.map((line) => {
    return line.flatMap((token) => {
      if (RE_WHITESPACE_ONLY.test(token.content)) return token;
      const match = token.content.match(RE_LEADING_TRAILING_WHITESPACE);
      if (!match) return token;
      const [, leading, content, trailing] = match;
      if (!leading && !trailing) return token;
      const expanded = [{
        ...token,
        offset: token.offset + leading.length,
        content
      }];
      if (leading) expanded.unshift({
        content: leading,
        offset: token.offset
      });
      if (trailing) expanded.push({
        content: trailing,
        offset: token.offset + leading.length + content.length
      });
      return expanded;
    });
  });
}
function mergeAdjacentStyledTokens(tokens) {
  return tokens.map((line) => {
    const newLine = [];
    for (const token of line) {
      if (newLine.length === 0) {
        newLine.push({ ...token });
        continue;
      }
      const prevToken = newLine.at(-1);
      const prevStyle = stringifyTokenStyle(prevToken.htmlStyle || getTokenStyleObject(prevToken));
      const currentStyle = stringifyTokenStyle(token.htmlStyle || getTokenStyleObject(token));
      const isPrevDecorated = prevToken.fontStyle && (prevToken.fontStyle & FontStyle.Underline || prevToken.fontStyle & FontStyle.Strikethrough);
      const isDecorated = token.fontStyle && (token.fontStyle & FontStyle.Underline || token.fontStyle & FontStyle.Strikethrough);
      if (!isPrevDecorated && !isDecorated && prevStyle === currentStyle) prevToken.content += token.content;
      else newLine.push({ ...token });
    }
    return newLine;
  });
}
var hastToHtml = toHtml;
function codeToHtml(primitive, code, options) {
  const context = {
    meta: {},
    options,
    codeToHast: (_code, _options) => codeToHast(primitive, _code, _options),
    codeToTokens: (_code, _options) => codeToTokens(primitive, _code, _options)
  };
  let result = hastToHtml(codeToHast(primitive, code, options, context));
  for (const transformer of getTransformers(options)) result = transformer.postprocess?.call(context, result, options) || result;
  return result;
}
async function createHighlighterCore(options) {
  const primitive = await createShikiPrimitiveAsync(options);
  return {
    getLastGrammarState: (...args) => getLastGrammarState(primitive, ...args),
    codeToTokensBase: (code, options2) => codeToTokensBase2(primitive, code, options2),
    codeToTokensWithThemes: (code, options2) => codeToTokensWithThemes(primitive, code, options2),
    codeToTokens: (code, options2) => codeToTokens(primitive, code, options2),
    codeToHast: (code, options2) => codeToHast(primitive, code, options2),
    codeToHtml: (code, options2) => codeToHtml(primitive, code, options2),
    getBundledLanguages: () => ({}),
    getBundledThemes: () => ({}),
    ...primitive,
    getInternalContext: () => primitive
  };
}
function createHighlighterCoreSync(options) {
  const internal = createShikiPrimitive(options);
  return {
    getLastGrammarState: (...args) => getLastGrammarState(internal, ...args),
    codeToTokensBase: (code, options2) => codeToTokensBase2(internal, code, options2),
    codeToTokensWithThemes: (code, options2) => codeToTokensWithThemes(internal, code, options2),
    codeToTokens: (code, options2) => codeToTokens(internal, code, options2),
    codeToHast: (code, options2) => codeToHast(internal, code, options2),
    codeToHtml: (code, options2) => codeToHtml(internal, code, options2),
    getBundledLanguages: () => ({}),
    getBundledThemes: () => ({}),
    ...internal,
    getInternalContext: () => internal
  };
}
function makeSingletonHighlighterCore(createHighlighter2) {
  let _shiki;
  async function getSingletonHighlighterCore2(options) {
    if (!_shiki) {
      _shiki = createHighlighter2({
        ...options,
        themes: options.themes || [],
        langs: options.langs || []
      });
      return _shiki;
    } else {
      const s = await _shiki;
      await Promise.all([s.loadTheme(...options.themes || []), s.loadLanguage(...options.langs || [])]);
      return s;
    }
  }
  return getSingletonHighlighterCore2;
}
var getSingletonHighlighterCore = makeSingletonHighlighterCore(createHighlighterCore);
function createBundledHighlighter(options) {
  const bundledLanguages2 = options.langs;
  const bundledThemes2 = options.themes;
  const engine = options.engine;
  async function createHighlighter2(options2) {
    function resolveLang(lang) {
      if (typeof lang === "string") {
        lang = options2.langAlias?.[lang] || lang;
        if (isSpecialLang(lang)) return [];
        const bundle = bundledLanguages2[lang];
        if (!bundle) throw new ShikiError2(`Language \`${lang}\` is not included in this bundle. You may want to load it from external source.`);
        return bundle;
      }
      return lang;
    }
    function resolveTheme(theme) {
      if (isSpecialTheme(theme)) return "none";
      if (typeof theme === "string") {
        const bundle = bundledThemes2[theme];
        if (!bundle) throw new ShikiError2(`Theme \`${theme}\` is not included in this bundle. You may want to load it from external source.`);
        return bundle;
      }
      return theme;
    }
    const _themes = (options2.themes ?? []).map((i) => resolveTheme(i));
    const langs = (options2.langs ?? []).map((i) => resolveLang(i));
    const core = await createHighlighterCore({
      engine: options2.engine ?? engine(),
      ...options2,
      themes: _themes,
      langs
    });
    return {
      ...core,
      loadLanguage(...langs2) {
        return core.loadLanguage(...langs2.map(resolveLang));
      },
      loadTheme(...themes) {
        return core.loadTheme(...themes.map(resolveTheme));
      },
      getBundledLanguages() {
        return bundledLanguages2;
      },
      getBundledThemes() {
        return bundledThemes2;
      }
    };
  }
  return createHighlighter2;
}
function makeSingletonHighlighter(createHighlighter2) {
  let _shiki;
  async function getSingletonHighlighter2(options = {}) {
    if (!_shiki) {
      _shiki = createHighlighter2({
        ...options,
        themes: [],
        langs: []
      });
      const s = await _shiki;
      await Promise.all([s.loadTheme(...options.themes || []), s.loadLanguage(...options.langs || [])]);
      return s;
    } else {
      const s = await _shiki;
      await Promise.all([s.loadTheme(...options.themes || []), s.loadLanguage(...options.langs || [])]);
      return s;
    }
  }
  return getSingletonHighlighter2;
}
function createSingletonShorthands(createHighlighter2, config) {
  const getSingletonHighlighter2 = makeSingletonHighlighter(createHighlighter2);
  async function get(code, options) {
    const shiki = await getSingletonHighlighter2({
      langs: [options.lang],
      themes: "theme" in options ? [options.theme] : Object.values(options.themes)
    });
    const langs = await config?.guessEmbeddedLanguages?.(code, options.lang, shiki);
    if (langs) await shiki.loadLanguage(...langs);
    return shiki;
  }
  return {
    getSingletonHighlighter(options) {
      return getSingletonHighlighter2(options);
    },
    async codeToHtml(code, options) {
      return (await get(code, options)).codeToHtml(code, options);
    },
    async codeToHast(code, options) {
      return (await get(code, options)).codeToHast(code, options);
    },
    async codeToTokens(code, options) {
      return (await get(code, options)).codeToTokens(code, options);
    },
    async codeToTokensBase(code, options) {
      return (await get(code, options)).codeToTokensBase(code, options);
    },
    async codeToTokensWithThemes(code, options) {
      return (await get(code, options)).codeToTokensWithThemes(code, options);
    },
    async getLastGrammarState(code, options) {
      return (await getSingletonHighlighter2({
        langs: [options.lang],
        themes: [options.theme]
      })).getLastGrammarState(code, options);
    }
  };
}
function createCssVariablesTheme(options = {}) {
  const { name = "css-variables", variablePrefix = "--shiki-", fontStyle = true } = options;
  const variable = (name2) => {
    if (options.variableDefaults?.[name2]) return `var(${variablePrefix}${name2}, ${options.variableDefaults[name2]})`;
    return `var(${variablePrefix}${name2})`;
  };
  const theme = {
    name,
    type: "dark",
    colors: {
      "editor.foreground": variable("foreground"),
      "editor.background": variable("background"),
      "terminal.ansiBlack": variable("ansi-black"),
      "terminal.ansiRed": variable("ansi-red"),
      "terminal.ansiGreen": variable("ansi-green"),
      "terminal.ansiYellow": variable("ansi-yellow"),
      "terminal.ansiBlue": variable("ansi-blue"),
      "terminal.ansiMagenta": variable("ansi-magenta"),
      "terminal.ansiCyan": variable("ansi-cyan"),
      "terminal.ansiWhite": variable("ansi-white"),
      "terminal.ansiBrightBlack": variable("ansi-bright-black"),
      "terminal.ansiBrightRed": variable("ansi-bright-red"),
      "terminal.ansiBrightGreen": variable("ansi-bright-green"),
      "terminal.ansiBrightYellow": variable("ansi-bright-yellow"),
      "terminal.ansiBrightBlue": variable("ansi-bright-blue"),
      "terminal.ansiBrightMagenta": variable("ansi-bright-magenta"),
      "terminal.ansiBrightCyan": variable("ansi-bright-cyan"),
      "terminal.ansiBrightWhite": variable("ansi-bright-white")
    },
    tokenColors: [
      {
        scope: [
          "keyword.operator.accessor",
          "meta.group.braces.round.function.arguments",
          "meta.template.expression",
          "markup.fenced_code meta.embedded.block"
        ],
        settings: { foreground: variable("foreground") }
      },
      {
        scope: "emphasis",
        settings: { fontStyle: "italic" }
      },
      {
        scope: [
          "strong",
          "markup.heading.markdown",
          "markup.bold.markdown"
        ],
        settings: { fontStyle: "bold" }
      },
      {
        scope: ["markup.italic.markdown"],
        settings: { fontStyle: "italic" }
      },
      {
        scope: "meta.link.inline.markdown",
        settings: {
          fontStyle: "underline",
          foreground: variable("token-link")
        }
      },
      {
        scope: [
          "string",
          "markup.fenced_code",
          "markup.inline"
        ],
        settings: { foreground: variable("token-string") }
      },
      {
        scope: ["comment", "string.quoted.docstring.multi"],
        settings: { foreground: variable("token-comment") }
      },
      {
        scope: [
          "constant.numeric",
          "constant.language",
          "constant.other.placeholder",
          "constant.character.format.placeholder",
          "variable.language.this",
          "variable.other.object",
          "variable.other.class",
          "variable.other.constant",
          "meta.property-name",
          "meta.property-value",
          "support"
        ],
        settings: { foreground: variable("token-constant") }
      },
      {
        scope: [
          "keyword",
          "storage.modifier",
          "storage.type",
          "storage.control.clojure",
          "entity.name.function.clojure",
          "entity.name.tag.yaml",
          "support.function.node",
          "support.type.property-name.json",
          "punctuation.separator.key-value",
          "punctuation.definition.template-expression"
        ],
        settings: { foreground: variable("token-keyword") }
      },
      {
        scope: "variable.parameter.function",
        settings: { foreground: variable("token-parameter") }
      },
      {
        scope: [
          "support.function",
          "entity.name.type",
          "entity.other.inherited-class",
          "meta.function-call",
          "meta.instance.constructor",
          "entity.other.attribute-name",
          "entity.name.function",
          "constant.keyword.clojure"
        ],
        settings: { foreground: variable("token-function") }
      },
      {
        scope: [
          "entity.name.tag",
          "string.quoted",
          "string.regexp",
          "string.interpolated",
          "string.template",
          "string.unquoted.plain.out.yaml",
          "keyword.other.template"
        ],
        settings: { foreground: variable("token-string-expression") }
      },
      {
        scope: [
          "punctuation.definition.arguments",
          "punctuation.definition.dict",
          "punctuation.separator",
          "meta.function-call.arguments"
        ],
        settings: { foreground: variable("token-punctuation") }
      },
      {
        scope: ["markup.underline.link", "punctuation.definition.metadata.markdown"],
        settings: { foreground: variable("token-link") }
      },
      {
        scope: ["beginning.punctuation.definition.list.markdown"],
        settings: { foreground: variable("token-string") }
      },
      {
        scope: [
          "punctuation.definition.string.begin.markdown",
          "punctuation.definition.string.end.markdown",
          "string.other.link.title.markdown",
          "string.other.link.description.markdown"
        ],
        settings: { foreground: variable("token-keyword") }
      },
      {
        scope: [
          "markup.inserted",
          "meta.diff.header.to-file",
          "punctuation.definition.inserted"
        ],
        settings: { foreground: variable("token-inserted") }
      },
      {
        scope: [
          "markup.deleted",
          "meta.diff.header.from-file",
          "punctuation.definition.deleted"
        ],
        settings: { foreground: variable("token-deleted") }
      },
      {
        scope: ["markup.changed", "punctuation.definition.changed"],
        settings: { foreground: variable("token-changed") }
      }
    ]
  };
  if (!fontStyle) theme.tokenColors = theme.tokenColors?.map((tokenColor) => {
    if (tokenColor.settings?.fontStyle) delete tokenColor.settings.fontStyle;
    return tokenColor;
  });
  return theme;
}

// node_modules/shiki/dist/bundle-full.mjs
var bundle_full_exports = __exportAll({
  bundledLanguages: () => bundledLanguages,
  bundledLanguagesAlias: () => bundledLanguagesAlias,
  bundledLanguagesBase: () => bundledLanguagesBase,
  bundledLanguagesInfo: () => bundledLanguagesInfo,
  bundledThemes: () => bundledThemes,
  bundledThemesInfo: () => bundledThemesInfo,
  codeToHast: () => codeToHast2,
  codeToHtml: () => codeToHtml2,
  codeToTokens: () => codeToTokens2,
  codeToTokensBase: () => codeToTokensBase3,
  codeToTokensWithThemes: () => codeToTokensWithThemes2,
  createHighlighter: () => createHighlighter,
  getLastGrammarState: () => getLastGrammarState2,
  getSingletonHighlighter: () => getSingletonHighlighter
});
var createHighlighter = createBundledHighlighter({
  langs: bundledLanguages,
  themes: bundledThemes,
  engine: () => (0, engine_oniguruma_exports.createOnigurumaEngine)(import("./wasm-W2KKAPZO.js"))
});
var { codeToHtml: codeToHtml2, codeToHast: codeToHast2, codeToTokens: codeToTokens2, codeToTokensBase: codeToTokensBase3, codeToTokensWithThemes: codeToTokensWithThemes2, getSingletonHighlighter, getLastGrammarState: getLastGrammarState2 } = createSingletonShorthands(createHighlighter, { guessEmbeddedLanguages });

// node_modules/@shikijs/engine-javascript/dist/scanner-DX8LRFGE.mjs
var MAX = 4294967295;
var JavaScriptScanner = class {
  patterns;
  options;
  regexps;
  constructor(patterns, options = {}) {
    this.patterns = patterns;
    this.options = options;
    const { forgiving = false, cache, regexConstructor } = options;
    if (!regexConstructor) throw new Error("Option `regexConstructor` is not provided");
    this.regexps = patterns.map((p) => {
      if (typeof p !== "string") return p;
      const cached = cache?.get(p);
      if (cached) {
        if (cached instanceof RegExp) return cached;
        if (forgiving) return null;
        throw cached;
      }
      try {
        const regex = regexConstructor(p);
        cache?.set(p, regex);
        return regex;
      } catch (e) {
        cache?.set(p, e);
        if (forgiving) return null;
        throw e;
      }
    });
  }
  findNextMatchSync(string, startPosition, _options) {
    const str = typeof string === "string" ? string : string.content;
    const pending = [];
    function toResult(index, match, offset = 0) {
      return {
        index,
        captureIndices: match.indices.map((indice) => {
          if (indice == null) return {
            start: MAX,
            end: MAX,
            length: 0
          };
          return {
            start: indice[0] + offset,
            end: indice[1] + offset,
            length: indice[1] - indice[0]
          };
        })
      };
    }
    for (let i = 0; i < this.regexps.length; i++) {
      const regexp = this.regexps[i];
      if (!regexp) continue;
      try {
        regexp.lastIndex = startPosition;
        const match = regexp.exec(str);
        if (!match) continue;
        if (match.index === startPosition) return toResult(i, match, 0);
        pending.push([
          i,
          match,
          0
        ]);
      } catch (e) {
        if (this.options.forgiving) continue;
        throw e;
      }
    }
    if (pending.length) {
      const minIndex = Math.min(...pending.map((m) => m[1].index));
      for (const [i, match, offset] of pending) if (match.index === minIndex) return toResult(i, match, offset);
    }
    return null;
  }
};

// node_modules/@shikijs/engine-javascript/dist/engine-compile.mjs
function defaultJavaScriptRegexConstructor(pattern, options) {
  return toRegExp(pattern, {
    global: true,
    hasIndices: true,
    lazyCompileLength: 3e3,
    rules: {
      allowOrphanBackrefs: true,
      asciiWordBoundaries: true,
      captureGroup: true,
      recursionLimit: 5,
      singleline: true
    },
    ...options
  });
}
function createJavaScriptRegexEngine(options = {}) {
  const _options = {
    target: "auto",
    cache: /* @__PURE__ */ new Map(),
    ...options
  };
  _options.regexConstructor ||= (pattern) => defaultJavaScriptRegexConstructor(pattern, { target: _options.target });
  return {
    createScanner(patterns) {
      return new JavaScriptScanner(patterns, _options);
    },
    createString(s) {
      return { content: s };
    }
  };
}

// node_modules/shiki/dist/index.mjs
__reExport(__exportAll({
  bundledLanguages: () => bundledLanguages,
  bundledLanguagesAlias: () => bundledLanguagesAlias,
  bundledLanguagesBase: () => bundledLanguagesBase,
  bundledLanguagesInfo: () => bundledLanguagesInfo,
  bundledThemes: () => bundledThemes,
  bundledThemesInfo: () => bundledThemesInfo,
  codeToHast: () => codeToHast2,
  codeToHtml: () => codeToHtml2,
  codeToTokens: () => codeToTokens2,
  codeToTokensBase: () => codeToTokensBase3,
  codeToTokensWithThemes: () => codeToTokensWithThemes2,
  createHighlighter: () => createHighlighter,
  createJavaScriptRegexEngine: () => createJavaScriptRegexEngine,
  createOnigurumaEngine: () => createOnigurumaEngine,
  defaultJavaScriptRegexConstructor: () => defaultJavaScriptRegexConstructor,
  getLastGrammarState: () => getLastGrammarState2,
  getSingletonHighlighter: () => getSingletonHighlighter,
  loadWasm: () => loadWasm
}), bundle_full_exports);
export {
  ShikiError2 as ShikiError,
  addClassToHast,
  applyColorReplacements,
  bundledLanguages,
  bundledLanguagesAlias,
  bundledLanguagesBase,
  bundledLanguagesInfo,
  bundledThemes,
  bundledThemesInfo,
  codeToHast2 as codeToHast,
  codeToHtml2 as codeToHtml,
  codeToTokens2 as codeToTokens,
  codeToTokensBase3 as codeToTokensBase,
  codeToTokensWithThemes2 as codeToTokensWithThemes,
  createBundledHighlighter,
  createCssVariablesTheme,
  createHighlighter,
  createHighlighterCore,
  createHighlighterCoreSync,
  createJavaScriptRegexEngine,
  createOnigurumaEngine,
  createPositionConverter,
  createShikiInternal,
  createShikiInternalSync,
  createShikiPrimitive,
  createShikiPrimitiveAsync,
  createSingletonShorthands,
  defaultJavaScriptRegexConstructor,
  flatTokenVariants,
  getLastGrammarState2 as getLastGrammarState,
  getSingletonHighlighter,
  getSingletonHighlighterCore,
  getTokenStyleObject,
  guessEmbeddedLanguages,
  hastToHtml,
  isNoneTheme,
  isPlainLang,
  isSpecialLang,
  isSpecialTheme,
  loadWasm,
  makeSingletonHighlighter,
  makeSingletonHighlighterCore,
  normalizeGetter,
  normalizeTheme,
  resolveColorReplacements,
  splitLines,
  splitToken,
  splitTokens,
  stringifyTokenStyle,
  toArray,
  tokenizeAnsiWithTheme,
  tokenizeWithTheme,
  tokensToHast,
  transformerDecorations
};
//# sourceMappingURL=shiki.js.map

const __vite__mapDeps=(i,m=__vite__mapDeps,d=(m.f||(m.f=["_astro/mermaid.core.DLVphVaw.js","_astro/preload-helper.1rgS-KFG.js"])))=>i.map(i=>d[i]);
import{_ as L}from"./preload-helper.1rgS-KFG.js";const C={},y=new Set,u=new WeakSet;let m=!0,w,p=!1;function S(e){p||(p=!0,m??=!1,w??="hover",A(),T(),P(),_())}function A(){for(const e of["touchstart","mousedown"])document.addEventListener(e,r=>{c(r.target,"tap")&&l(r.target.href,{ignoreSlowConnection:!0})},{passive:!0})}function T(){let e;document.body.addEventListener("focusin",t=>{c(t.target,"hover")&&r(t)},{passive:!0}),document.body.addEventListener("focusout",a,{passive:!0}),f(()=>{for(const t of document.getElementsByTagName("a"))u.has(t)||c(t,"hover")&&(u.add(t),t.addEventListener("mouseenter",r,{passive:!0}),t.addEventListener("mouseleave",a,{passive:!0}))});function r(t){const n=t.target.href;e&&clearTimeout(e),e=setTimeout(()=>{l(n)},80)}function a(){e&&(clearTimeout(e),e=0)}}function P(){let e;f(()=>{for(const r of document.getElementsByTagName("a"))u.has(r)||c(r,"viewport")&&(u.add(r),e??=O(),e.observe(r))})}function O(){const e=new WeakMap;return new IntersectionObserver((r,a)=>{for(const t of r){const n=t.target,o=e.get(n);t.isIntersecting?(o&&clearTimeout(o),e.set(n,setTimeout(()=>{a.unobserve(n),e.delete(n),l(n.href)},300))):o&&(clearTimeout(o),e.delete(n))}})}function _(){f(()=>{for(const e of document.getElementsByTagName("a"))c(e,"load")&&l(e.href)})}function l(e,r){e=e.replace(/#.*/,"");const a=r?.ignoreSlowConnection??!1;if(I(e,a))if(y.add(e),document.createElement("link").relList?.supports?.("prefetch")&&r?.with!=="fetch"){const t=document.createElement("link");t.rel="prefetch",t.setAttribute("href",e),document.head.append(t)}else{const t=new Headers;for(const[n,o]of Object.entries(C))t.set(n,o);fetch(e,{priority:"low",headers:t})}}function I(e,r){if(!navigator.onLine||!r&&x())return!1;try{const a=new URL(e,location.href);return location.origin===a.origin&&(location.pathname!==a.pathname||location.search!==a.search)&&!y.has(e)}catch{}return!1}function c(e,r){if(e?.tagName!=="A")return!1;const a=e.dataset.astroPrefetch;return a==="false"?!1:r==="tap"&&(a!=null||m)&&x()?!0:a==null&&m||a===""?r===w:a===r}function x(){if("connection"in navigator){const e=navigator.connection;return e.saveData||/2g/.test(e.effectiveType)}return!1}function f(e){e();let r=!1;document.addEventListener("astro:page-load",()=>{if(!r){r=!0;return}e()})}const b=()=>{},k=(...e)=>console.error("[astro-mermaid]",...e),M=()=>document.querySelectorAll("pre.mermaid").length>0;let d=null;async function B(){return d||(d=L(()=>import("./mermaid.core.DLVphVaw.js").then(e=>e.cc),__vite__mapDeps([0,1])).then(async({default:e})=>{const r=[];if(r&&r.length>0){const a=r.map(t=>t.icons?{name:t.name,icons:t.icons}:{name:t.name,loader:()=>fetch(t.url).then(n=>n.json())});await e.registerIconPacks(a)}return e}).catch(e=>{throw k("Failed to load mermaid:",e),d=null,e}),d)}const v={startOnLoad:!1,theme:"default",flowchart:{useMaxWidth:!1},sequence:{useMaxWidth:!1},gantt:{useMaxWidth:!1},journey:{useMaxWidth:!1},class:{useMaxWidth:!1},state:{useMaxWidth:!1},er:{useMaxWidth:!1},pie:{useMaxWidth:!1},requirement:{useMaxWidth:!1},mindmap:{useMaxWidth:!1},timeline:{useMaxWidth:!1},gitGraph:{useMaxWidth:!1},c4:{useMaxWidth:!1},sankey:{useMaxWidth:!1},xyChart:{useMaxWidth:!1},block:{useMaxWidth:!1},quadrantChart:{useMaxWidth:!1},architecture:{useMaxWidth:!1}};async function E(){const e=document.querySelectorAll("pre.mermaid");if(b("Found",e.length),e.length===0)return;const r=await B();let a=v.theme;r.initialize({...v,theme:a,gitGraph:{mainBranchName:"main",showCommitLabel:!0,showBranches:!0,rotateCommitLabel:!0}});for(const t of e){if(t.hasAttribute("data-processed"))continue;t.hasAttribute("data-diagram")||t.setAttribute("data-diagram",t.textContent||"");const n=t.getAttribute("data-diagram")||"",o="mermaid-"+Math.random().toString(36).slice(2,11);try{const s=document.getElementById(o);s&&s.remove();const{svg:i}=await r.render(o,n);t.innerHTML=i,t.setAttribute("data-processed","true"),b("Successfully rendered diagram:",o)}catch(s){k("Mermaid rendering error for diagram:",o,s);const i=document.createElement("div");i.style.cssText="color: red; padding: 1rem; border: 1px solid red; border-radius: 0.5rem;";const h=document.createElement("strong");h.textContent="Error rendering diagram:";const g=document.createElement("span");g.textContent=" "+(s.message||"Unknown error"),i.appendChild(h),i.appendChild(g),t.textContent="",t.appendChild(i),t.setAttribute("data-processed","true")}}}M()&&E();document.addEventListener("astro:after-swap",()=>{M()&&E()});const W=document.createElement("style");W.textContent=`
            /* Prevent layout shifts by setting minimum height */
            pre.mermaid {
              display: flex;
              justify-content: center;
              align-items: center;
              margin: 2rem 0;
              padding: 1rem;
              background-color: transparent;
              border: none;
              overflow: auto;
              min-height: 200px; /* Prevent layout shift */
              position: relative;
            }
            
            /* Loading state with skeleton loader */
            pre.mermaid:not([data-processed]) {
              background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
              background-size: 200% 100%;
              animation: shimmer 1.5s infinite;
            }
            
            /* Dark mode skeleton loader */
            [data-theme="dark"] pre.mermaid:not([data-processed]) {
              background: linear-gradient(90deg, #2a2a2a 25%, #3a3a3a 50%, #2a2a2a 75%);
              background-size: 200% 100%;
            }
            
            @keyframes shimmer {
              0% {
                background-position: -200% 0;
              }
              100% {
                background-position: 200% 0;
              }
            }
            
            /* Show processed diagrams with smooth transition */
            pre.mermaid[data-processed] {
              animation: none;
              background: transparent;
              min-height: auto; /* Allow natural height after render */
            }
            
            /* Ensure responsive sizing for mermaid SVGs */
            pre.mermaid svg {
              max-width: 100%;
              height: auto;
            }
            
            /* Optional: Add subtle background for better visibility */
            @media (prefers-color-scheme: dark) {
              pre.mermaid[data-processed] {
                background-color: rgba(255, 255, 255, 0.02);
                border-radius: 0.5rem;
              }
            }
            
            @media (prefers-color-scheme: light) {
              pre.mermaid[data-processed] {
                background-color: rgba(0, 0, 0, 0.02);
                border-radius: 0.5rem;
              }
            }
            
            /* Respect user's color scheme preference */
            [data-theme="dark"] pre.mermaid[data-processed] {
              background-color: rgba(255, 255, 255, 0.02);
              border-radius: 0.5rem;
            }
            
            [data-theme="light"] pre.mermaid[data-processed] {
              background-color: rgba(0, 0, 0, 0.02);
              border-radius: 0.5rem;
            }
          `;document.head.appendChild(W);S();

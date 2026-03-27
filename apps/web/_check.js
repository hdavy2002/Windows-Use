const path = require('path');
const fs = require('fs');
const nm = path.join(__dirname, 'node_modules');
console.log('node_modules exists:', fs.existsSync(nm));
try { console.log('tailwindcss:', require.resolve('tailwindcss')); } catch(e) { console.log('tailwindcss: NOT FOUND'); }
try { console.log('@tailwindcss/postcss:', require.resolve('@tailwindcss/postcss')); } catch(e) { console.log('@tailwindcss/postcss: NOT FOUND'); }
console.log('@tailwindcss dir:', fs.existsSync(path.join(nm, '@tailwindcss')));
const dirs = fs.readdirSync(nm).filter(d => d.startsWith('@t'));
console.log('@t* dirs:', dirs);

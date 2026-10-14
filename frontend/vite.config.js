import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({plugins:[react()], base:'/wiavoice/', server:{proxy:{'/wiavoice/api':{target:'http://127.0.0.1:1015',rewrite:p=>p.replace('/wiavoice','')}}}});

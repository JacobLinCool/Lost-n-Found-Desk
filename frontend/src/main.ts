import { mount } from 'svelte';
import App from './App.svelte';
import './styles/tokens.css';
import './styles/base.css';
import './styles/components.css';

const target = document.getElementById('app');
if (!target) throw new Error('Mount target #app not found');

const app = mount(App, { target });

export default app;

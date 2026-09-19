// Every screen is rendered in the browser from the static bundle. Declared at the root as well
// as in (app): the root error page (an address outside the app) has no other layout, and a
// server build (vite preview, adapter-node) drops the server component of a layout whose pages
// all opt out of SSR, so without this an unknown URL answers 500 instead of the 404 screen.
export const ssr = false;
export const prerender = false;
